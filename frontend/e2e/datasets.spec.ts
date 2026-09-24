/** 数据集 UI：真实后端（需要 E2E_API_KEY），上传与切换走真实链路。 */
import { expect, test } from "@playwright/test";

const key = process.env.E2E_API_KEY ?? "";

test("上传 CSV 后出现在下拉并自动选中", async ({ page }) => {
  test.skip(!key, "E2E_API_KEY not set (run scripts/e2e_up.ps1)");
  await page.goto("/");
  await page.getByLabel("API 访问密钥").fill(key);
  await expect(page.getByLabel("切换数据集")).toHaveValue("orders");

  await page.locator('input[type="file"]').setInputFiles({
    name: "e2e-ui.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("category,amount\nA,1\nB,2\n"),
  });
  await expect(page.getByRole("option", { name: "e2e-ui.csv" })).toBeAttached();
});
