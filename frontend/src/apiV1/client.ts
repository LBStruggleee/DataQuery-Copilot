/** v1 真实客户端：统一解信封、按码抛错、分页参数钳制。 */
import type { HealthStatus, QualityInfo, SchemaInfo } from "../types";
import type { ApiEnvelope, ErrorCode, V1QueryData } from "./types";

const V1_BASE = `${(import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "")}/api/v1`;

export class V1ApiError extends Error {
  code: ErrorCode | "UNKNOWN";
  status: number;
  requestId: string | null;

  constructor(code: ErrorCode | "UNKNOWN", message: string, status: number, requestId: string | null) {
    super(message);
    this.name = "V1ApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}

export async function fetchEnvelope<T>(path: string, init?: RequestInit): Promise<{ data: T; requestId: string }> {
  const response = await fetch(`${V1_BASE}${path}`, init);
  const payload = (await response.json().catch(() => null)) as ApiEnvelope<T> | null;
  if (!payload || payload.version !== "v1" || typeof payload.code !== "string") {
    throw new V1ApiError("UNKNOWN", "v1 服务返回了无法识别的响应", response.status, null);
  }
  if (!response.ok || payload.code !== "OK" || payload.data === null) {
    throw new V1ApiError(
      (payload.code as ErrorCode) ?? "UNKNOWN",
      payload.message || "v1 服务请求失败",
      response.status,
      payload.request_id ?? null,
    );
  }
  return { data: payload.data, requestId: payload.request_id };
}

export function buildQueryBody(question: string, page: number, pageSize: number) {
  return {
    question,
    clean_result: true,
    max_retries: 2,
    page: Math.max(1, Math.floor(page) || 1),
    page_size: Math.min(50, Math.max(1, Math.floor(pageSize) || 10)),
  };
}

export async function loadWorkspaceOverviewV1Live(signal?: AbortSignal): Promise<{
  health: HealthStatus; schema: SchemaInfo; quality: QualityInfo;
}> {
  const [health, schema, quality] = await Promise.all([
    fetchEnvelope<HealthStatus>("/health", { signal }),
    fetchEnvelope<SchemaInfo>("/schema", { signal }),
    fetchEnvelope<QualityInfo>("/quality", { signal }),
  ]);
  return { health: health.data, schema: schema.data, quality: quality.data };
}

export async function runQueryV1Live(
  question: string, page: number, pageSize: number, signal?: AbortSignal,
): Promise<{ data: V1QueryData; requestId: string }> {
  return fetchEnvelope<V1QueryData>("/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildQueryBody(question, page, pageSize)),
    signal,
  });
}
