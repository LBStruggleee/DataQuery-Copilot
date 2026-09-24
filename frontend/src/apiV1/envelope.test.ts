/** 前端契约测试：v1 信封解析、错误码分支、分页参数（样本形状对标后端 api/models.py）。 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { V1ApiError, buildQueryBody, fetchEnvelope, listDatasetsLive, uploadDatasetLive } from "./client";

describe("datasets", () => {
  it("解出数据集列表", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      version: "v1", code: "OK", message: "ok",
      data: [{ id: "a1", name: "s.csv", table_name: "ds_s_a1", rows: 5, created_at: "t" }],
      request_id: "req_z",
    })));
    const result = await listDatasetsLive();
    expect(result.data).toHaveLength(1);
    expect(result.data[0].table_name).toBe("ds_s_a1");
  });

  it("上传时用 multipart 并附带 Key", async () => {
    vi.stubGlobal("localStorage", { getItem: () => "dqc_up", setItem: () => {}, removeItem: () => {} });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      version: "v1", code: "OK", message: "ok",
      data: { id: "b2", name: "u.csv", table_name: "ds_u_b2", rows: 3, created_at: "t" },
      request_id: "req_w",
    }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["a,b\n1,2\n"], "u.csv", { type: "text/csv" });
    const result = await uploadDatasetLive(file);
    expect(result.data.id).toBe("b2");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/v1/datasets");
    expect((init.headers as Record<string, string>)["X-API-Key"]).toBe("dqc_up");
    expect(init.body).toBeInstanceOf(FormData);
  });
});

afterEach(() => vi.unstubAllGlobals());

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

describe("fetchEnvelope", () => {
  it("成功时解出 data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      version: "v1", code: "OK", message: "ok", data: { a: 1 }, request_id: "req_x",
    })));
    const result = await fetchEnvelope<{ a: number }>("/health");
    expect(result.data).toEqual({ a: 1 });
    expect(result.requestId).toBe("req_x");
  });

  it("错误信封按码抛出", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      version: "v1", code: "SQL_REJECTED", message: "仅允许 SELECT", data: null, request_id: "req_y",
    }, 422)));
    const error = await fetchEnvelope("/query").catch((e) => e);
    expect(error).toBeInstanceOf(V1ApiError);
    expect((error as V1ApiError).code).toBe("SQL_REJECTED");
    expect((error as V1ApiError).requestId).toBe("req_y");
  });

  it("畸形载荷抛 UNKNOWN", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ hello: 1 })));
    const error = await fetchEnvelope("/query").catch((e) => e);
    expect((error as V1ApiError).code).toBe("UNKNOWN");
  });

  it("网络失败原样抛出 TypeError（供 App 回退 mock）", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    const error = await fetchEnvelope("/query").catch((e) => e);
    expect(error).toBeInstanceOf(TypeError);
  });
});

describe("buildQueryBody", () => {
  it("钳制分页参数", () => {
    expect(buildQueryBody("q", 0, 999)).toEqual({ question: "q", clean_result: true, max_retries: 2, page: 1, page_size: 50 });
  });

  it("默认数据集时省略 dataset 字段", () => {
    expect(buildQueryBody("q", 1, 10)).not.toHaveProperty("dataset");
    expect(buildQueryBody("q", 1, 10, "abc123")).toMatchObject({ dataset: "abc123" });
  });
});

describe("api key", () => {
  it("localStorage 有 Key 时附带 X-API-Key 请求头", async () => {
    vi.stubGlobal("localStorage", { getItem: () => "dqc_test", setItem: () => {}, removeItem: () => {} });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      version: "v1", code: "OK", message: "ok", data: { a: 1 }, request_id: "req_x",
    }));
    vi.stubGlobal("fetch", fetchMock);
    await fetchEnvelope("/health");
    expect(fetchMock.mock.calls[0][1].headers["X-API-Key"]).toBe("dqc_test");
  });
});
