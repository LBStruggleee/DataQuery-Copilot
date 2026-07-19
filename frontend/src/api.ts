import type { ApiState, HealthStatus, QualityInfo, QueryResponse, SchemaInfo } from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`${path} 请求失败 (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function loadWorkspaceOverview(): Promise<Omit<ApiState, "loading" | "error">> {
  const [health, schema, quality] = await Promise.all([
    getJson<HealthStatus>("/api/health"),
    getJson<SchemaInfo>("/api/schema"),
    getJson<QualityInfo>("/api/quality"),
  ]);
  return { health, schema, quality };
}

export async function runQuery(question: string, signal?: AbortSignal): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE_URL}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, clean_result: true, max_retries: 2 }),
    signal,
  });
  const payload = await response.json().catch(() => null) as { detail?: string } | QueryResponse | null;
  if (!response.ok) {
    const message = payload && "detail" in payload && payload.detail ? payload.detail : "查询服务暂时不可用";
    throw new Error(message);
  }
  return payload as QueryResponse;
}
