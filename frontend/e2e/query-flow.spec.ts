/** 查询流程 UI 走查：v1 端点全部 stub（不依赖 LLM），验证界面与操作流程。 */
import { expect, test, type Page } from "@playwright/test";

async function stubOverview(page: Page) {
  await page.route("**/api/v1/health", (route) => route.fulfill({
    json: { version: "v1", code: "OK", message: "ok", data: { status: "ok", database_ready: true, llm_configured: true }, request_id: "req_e2e" },
  }));
  await page.route("**/api/v1/schema**", (route) => route.fulfill({
    json: { version: "v1", code: "OK", message: "ok", data: { table_name: "orders", columns: [{ name: "category", type: "TEXT" }] }, request_id: "req_e2e" },
  }));
  await page.route("**/api/v1/quality**", (route) => route.fulfill({
    json: { version: "v1", code: "OK", message: "ok", data: { table_name: "orders", total_rows: 100, total_columns: 2, missing_values: {}, duplicates: 0, column_types: {} }, request_id: "req_e2e" },
  }));
  await page.route("**/api/v1/datasets", (route) => route.fulfill({
    json: { version: "v1", code: "OK", message: "ok", data: [], request_id: "req_e2e" },
  }));
}

async function stubQuery(page: Page) {
  await page.route("**/api/v1/query", (route) => {
    const body = route.request().postDataJSON() as { question: string; page?: number };
    if (/删/.test(body.question)) {
      return route.fulfill({
        status: 422,
        json: { version: "v1", code: "SQL_REJECTED", message: "SQL 安全校验未通过", data: null, request_id: "req_e2e1" },
      });
    }
    const pageNum = body.page ?? 1;
    const rows = Array.from({ length: 10 }, (_, i) => ({ category: `类${(pageNum - 1) * 10 + i}`, total_sales: 100 + i }));
    const truncated = /超大/.test(body.question);
    return route.fulfill({
      json: {
        version: "v1", code: "OK", message: truncated ? "结果超过 100 行上限，仅返回前 100 行" : "ok",
        data: {
          question: body.question, sql: "SELECT 1", columns: ["category", "total_sales"], rows,
          row_count: 25, page: pageNum, page_size: 10, total_pages: 3, truncated,
          chart_hint: "bar", execution_time: 0.01, valid: true, retries: 0, from_cache: false,
        },
        request_id: "req_e2e2",
      },
    });
  });
}

async function runQuestion(page: Page, question: string) {
  await page.getByLabel("自然语言查询问题").fill(question);
  await page.getByRole("button", { name: "运行查询" }).click();
}

test("查询成功并翻页", async ({ page }) => {
  await stubOverview(page);
  await stubQuery(page);
  await page.goto("/");

  await runQuestion(page, "各品类销售统计");
  await expect(page.getByRole("cell", { name: "类0" })).toBeVisible();
  await page.getByRole("button", { name: "下一页" }).click();
  await expect(page.getByRole("cell", { name: "类10" })).toBeVisible();
  await expect(page.getByText("第 2 / 3 页")).toBeVisible();
});

test("安全拒绝展示错误码", async ({ page }) => {
  await stubOverview(page);
  await stubQuery(page);
  await page.goto("/");

  await runQuestion(page, "删掉订单表");
  await expect(page.getByText("SQL_REJECTED")).toBeVisible();
  await expect(page.getByText("SQL 安全校验未通过")).toBeVisible();
});

test("截断提示展示", async ({ page }) => {
  await stubOverview(page);
  await stubQuery(page);
  await page.goto("/");

  await runQuestion(page, "超大结果集导出");
  await expect(page.getByText("RESULT_TRUNCATED")).toBeVisible();
});
