/** 查询流程 UI 走查：v1 端点全部 stub（不依赖 LLM），验证界面与操作流程。
 *  P2-55：补 401/429/网络错误 stub 用例；顺带覆盖 P1-21/P1-24/P2-52/P2-54 的界面接线。 */
import { expect, test, type Page } from "@playwright/test";

const envelope = (data: unknown, requestId = "req_e2e", message = "ok") => ({
  version: "v1", code: "OK", message, data, requestId,
});

async function stubOverview(page: Page, datasets: Array<{ id: string; name: string }> = []) {
  await page.route("**/api/v1/health", (route) => route.fulfill({
    json: envelope({ status: "ok", database_ready: true, llm_configured: true }),
  }));
  await page.route("**/api/v1/schema**", (route) => route.fulfill({
    json: envelope({ table_name: "orders", columns: [{ name: "category", type: "TEXT" }] }),
  }));
  await page.route("**/api/v1/quality**", (route) => route.fulfill({
    json: envelope({ table_name: "orders", total_rows: 100, total_columns: 2, missing_values: {}, duplicates: 0, column_types: {} }),
  }));
  await page.route("**/api/v1/datasets", (route) => route.fulfill({
    json: envelope(datasets.map((d) => ({ ...d, table_name: d.id, rows: 5, created_at: "t" }))),
  }));
}

/** 所有概览端点统一返回指定状态码（401/429 等）。 */
async function stubOverviewStatus(page: Page, status: number, code: string, message: string) {
  for (const path of ["health", "schema**", "quality**", "datasets"]) {
    await page.route(`**/api/v1/${path}`, (route) => route.fulfill({
      status,
      json: { version: "v1", code, message, data: null, request_id: "req_err" },
    }));
  }
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

test("查询成功并翻页，Inspector 展示真实 request_id（P1-24）", async ({ page }) => {
  await stubOverview(page);
  await stubQuery(page);
  await page.goto("/");

  await runQuestion(page, "各品类销售统计");
  await expect(page.getByRole("cell", { name: "类0" })).toBeVisible();
  await page.getByRole("button", { name: "下一页" }).click();
  await expect(page.getByRole("cell", { name: "类10" })).toBeVisible();
  await expect(page.getByText("第 2 / 3 页")).toBeVisible();
  // P1-24：查询 ID 展示后端信封里的 request_id，而非伪造 qry_ 哈希
  await expect(page.getByText("req_e2e2")).toBeVisible();
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

test("SQL 返回重复列名时结果表仍正常渲染（P2-54）", async ({ page }) => {
  await stubOverview(page);
  await page.route("**/api/v1/query", (route) => route.fulfill({
    json: envelope({
      question: "联表查询", sql: "SELECT 1", columns: ["category", "category", "total_sales"],
      rows: [{ category: "类A", total_sales: 7 }], row_count: 1, page: 1, page_size: 10, total_pages: 1,
      truncated: false, chart_hint: "table", execution_time: 0.01, valid: true, retries: 0, from_cache: false,
    }, "req_dup"),
  }));
  await page.goto("/");

  await runQuestion(page, "联表查询");
  const dataRow = page.getByRole("row").filter({ hasText: "类A" });
  await expect(dataRow.getByRole("cell")).toHaveCount(3);
});

test("401 时提示重新粘贴并聚焦密钥输入框（P1-22/P1-25）", async ({ page }) => {
  await stubOverviewStatus(page, 401, "AUTH_REQUIRED", "无效或已吊销的 API Key");
  await page.goto("/");

  await expect(page.getByText("Key 无效或已吊销（401），请重新粘贴管理员签发的 Key。")).toBeVisible();
  await expect(page.getByLabel("API 访问密钥")).toBeFocused();
  await expect(page.getByText("Key 无效", { exact: true })).toBeVisible();
});

test("429 时展示稍后重试引导（P1-22/P2-55）", async ({ page }) => {
  await stubOverview(page);
  await page.route("**/api/v1/query", (route) => route.fulfill({
    status: 429,
    json: { version: "v1", code: "RATE_LIMITED", message: "请求过于频繁，请稍后重试", data: null, request_id: "req_429" },
  }));
  await page.goto("/");

  await runQuestion(page, "各品类销售统计");
  await expect(page.getByText("RATE_LIMITED")).toBeVisible();
  await expect(page.getByText("请求过于频繁或今日配额已用尽，请稍后重试。")).toBeVisible();
});

test("网络错误单独提示（P1-22/P2-55）", async ({ page }) => {
  for (const path of ["health", "schema**", "quality**", "datasets"]) {
    await page.route(`**/api/v1/${path}`, (route) => route.abort("connectionrefused"));
  }
  await page.goto("/");

  await expect(page.getByText("网络错误", { exact: true })).toBeVisible();
  await expect(page.getByText("网络错误，请检查连接")).toBeVisible();
});

test("切换数据集取消在途查询，旧结果被清除且迟到响应不再覆盖（P2-52）", async ({ page }) => {
  await stubOverview(page, [{ id: "ds_upload", name: "上传数据集" }]);
  await page.route("**/api/v1/query", async (route) => {
    // 挂起 20s 模拟慢查询：切换数据集后该响应不应再进入界面
    await new Promise((resolve) => setTimeout(resolve, 20_000));
    await route.fulfill({ json: envelope({
      question: "缓慢查询", sql: "SELECT 1", columns: ["category", "total_sales"],
      rows: [{ category: "类0", total_sales: 1 }], row_count: 1, page: 1, page_size: 10, total_pages: 1,
      truncated: false, chart_hint: "table", execution_time: 0.01, valid: true, retries: 0, from_cache: false,
    }, "req_late") });
  });
  await page.goto("/");

  await runQuestion(page, "缓慢查询");
  await expect(page.getByRole("button", { name: /查询中/ })).toBeVisible();
  await page.getByLabel("切换数据集").selectOption("ds_upload");
  await expect(page.getByText("还没有查询")).toBeVisible();
  await expect(page.getByRole("cell", { name: "类0" })).toHaveCount(0);
  await expect(page.getByText("req_late")).toHaveCount(0);
});

test("快速切换数据集，慢的旧概览响应不会覆盖新数据集（P1-21）", async ({ page }) => {
  await page.route("**/api/v1/health", (route) => route.fulfill({
    json: envelope({ status: "ok", database_ready: true, llm_configured: true }),
  }));
  await page.route("**/api/v1/quality**", (route) => route.fulfill({
    json: envelope({ table_name: "orders", total_rows: 100, total_columns: 2, missing_values: {}, duplicates: 0, column_types: {} }),
  }));
  await page.route("**/api/v1/datasets", (route) => route.fulfill({
    json: envelope([
      { id: "ds_slow", name: "慢数据集", table_name: "ds_slow", rows: 5, created_at: "t1" },
      { id: "ds_fast", name: "快数据集", table_name: "ds_fast", rows: 5, created_at: "t2" },
    ]),
  }));
  await page.route("**/api/v1/schema**", async (route) => {
    const ds = new URL(route.request().url()).searchParams.get("dataset");
    if (ds === "ds_slow") {
      await new Promise((resolve) => setTimeout(resolve, 600));
      await route.fulfill({ json: envelope({ table_name: "ds_slow_late", columns: [] }, "req_slow") });
      return;
    }
    await route.fulfill({ json: envelope({ table_name: ds === "ds_fast" ? "ds_fast_now" : "orders", columns: [] }, "req_fast") });
  });
  await page.goto("/");
  await expect(page.getByText("orders")).toBeVisible();

  await page.getByLabel("切换数据集").selectOption("ds_slow");
  await page.getByLabel("切换数据集").selectOption("ds_fast");
  await expect(page.getByText("ds_fast_now")).toBeVisible();

  // 越过慢响应的返回时间点：被取消的旧请求不得把 ds_slow_late 写回界面
  await page.waitForTimeout(800);
  await expect(page.getByText("ds_slow_late")).toHaveCount(0);
  await expect(page.getByText("ds_fast_now")).toBeVisible();
});
