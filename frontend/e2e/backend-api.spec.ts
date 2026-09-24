/** 后端 API 真实链路（需要 E2E_API_KEY，由 scripts/e2e_up.ps1 注入）。 */
import { expect, test } from "@playwright/test";

const API = "http://127.0.0.1:8001";
const key = process.env.E2E_API_KEY ?? "";
const auth = () => ({ "X-API-Key": key });

test("无 Key 返回 401 AUTH_REQUIRED 信封", async ({ request }) => {
  const r = await request.get(`${API}/api/v1/health`);
  expect(r.status()).toBe(401);
  const body = await r.json();
  expect(body.code).toBe("AUTH_REQUIRED");
  expect(body.data).toBeNull();
  expect(body.request_id).toMatch(/^req_/);
});

test("带 Key 健康检查 200 且库就绪", async ({ request }) => {
  test.skip(!key, "E2E_API_KEY not set (run scripts/e2e_up.ps1)");
  const r = await request.get(`${API}/api/v1/health`, { headers: auth() });
  expect(r.status()).toBe(200);
  expect((await r.json()).data.database_ready).toBe(true);
});

test("空白问题 422 INVALID_QUESTION", async ({ request }) => {
  test.skip(!key, "E2E_API_KEY not set (run scripts/e2e_up.ps1)");
  const r = await request.post(`${API}/api/v1/query`, { headers: auth(), data: { question: "   " } });
  expect(r.status()).toBe(422);
  expect((await r.json()).code).toBe("INVALID_QUESTION");
});

test("上传 CSV → 列表可见 → 作用域 schema → 未知数据集 404", async ({ request }) => {
  test.skip(!key, "E2E_API_KEY not set (run scripts/e2e_up.ps1)");
  const csv = "category,amount\nA,1\nB,2\n";
  const up = await request.post(`${API}/api/v1/datasets`, {
    headers: auth(),
    multipart: { file: { name: "e2e.csv", mimeType: "text/csv", buffer: Buffer.from(csv) } },
  });
  expect(up.ok()).toBeTruthy();
  const id = (await up.json()).data.id as string;

  const list = await request.get(`${API}/api/v1/datasets`, { headers: auth() });
  expect(((await list.json()).data as Array<{ id: string }>).map((d) => d.id)).toContain(id);

  const schema = await request.get(`${API}/api/v1/schema?dataset=${id}`, { headers: auth() });
  expect(((await schema.json()).data.table_name as string)).toContain("ds_");

  const missing = await request.post(`${API}/api/v1/query`, {
    headers: auth(),
    data: { question: "有效问题", dataset: "nope" },
  });
  expect(missing.status()).toBe(404);
  expect((await missing.json()).code).toBe("TABLE_NOT_FOUND");
});
