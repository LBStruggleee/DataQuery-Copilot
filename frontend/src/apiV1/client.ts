/** v1 真实客户端：统一解信封、按码抛错、分页参数钳制。 */
import type { HealthStatus, QualityInfo, QueryResponse, SchemaInfo } from "../types";
import type { ApiEnvelope, DatasetInfo, ErrorCode, V1QueryData } from "./types";

const V1_BASE = `${(import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "")}/api/v1`;

export const API_KEY_STORAGE_KEY = "dqc_api_key";

/** 从 localStorage 读 Key（读不到返回空对象，不抛异常）。 */
export function readApiKey(): Record<string, string> {
  try {
    const key = localStorage.getItem(API_KEY_STORAGE_KEY);
    return key ? { "X-API-Key": key } : {};
  } catch {
    return {};
  }
}

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

/** P1-23：所有请求统一 30s 超时，避免后端挂起时前端永远停在加载态。 */
export const REQUEST_TIMEOUT_MS = 30_000;

function isAbortLike(error: unknown): boolean {
  const name = error instanceof Error ? error.name : "";
  return name === "AbortError" || name === "TimeoutError";
}

export async function fetchEnvelope<T>(
  path: string, init?: RequestInit, timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<{ data: T; requestId: string }> {
  const merged: RequestInit = {
    ...init,
    headers: { ...readApiKey(), ...((init?.headers ?? {}) as Record<string, string>) },
  };
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  merged.signal = init?.signal ? AbortSignal.any([init.signal, timeoutSignal]) : timeoutSignal;

  let response: Response;
  let payload: ApiEnvelope<T> | null = null;
  try {
    response = await fetch(`${V1_BASE}${path}`, merged);
  } catch (error) {
    // 调用方主动取消（切换数据集/组件卸载）→ 原样上抛，由调用方按 AbortError 静默处理
    if (init?.signal?.aborted) throw error;
    // 超时（AbortSignal.timeout 触发）→ 映射为契约中的 QUERY_TIMEOUT 明确错误
    if (isAbortLike(error)) {
      throw new V1ApiError("QUERY_TIMEOUT", `请求超过 ${Math.round(timeoutMs / 1000)} 秒无响应，已中止`, 0, null);
    }
    // 其他网络错误（断网等）原样上抛
    throw error;
  }
  try {
    payload = (await response.json()) as ApiEnvelope<T> | null;
  } catch (error) {
    if (init?.signal?.aborted) throw error;
    if (isAbortLike(error)) {
      throw new V1ApiError("QUERY_TIMEOUT", `请求超过 ${Math.round(timeoutMs / 1000)} 秒无响应，已中止`, 0, null);
    }
    // JSON 解析失败 → 保持原有行为：payload=null → 下面的 UNKNOWN 分支
  }
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

export const DEFAULT_DATASET_ID = "orders";

export const DEFAULT_PAGE_SIZE = 10;

export function buildQueryBody(question: string, page: number, pageSize: number, dataset?: string) {
  const body: Record<string, unknown> = {
    question,
    clean_result: true,
    max_retries: 2,
    page: Math.max(1, Math.floor(page) || 1),
    page_size: Math.min(50, Math.max(1, Math.floor(pageSize) || 10)),
  };
  if (dataset && dataset !== DEFAULT_DATASET_ID) body.dataset = dataset;
  return body;
}

function datasetParam(dataset?: string): string {
  return dataset && dataset !== DEFAULT_DATASET_ID ? `?dataset=${encodeURIComponent(dataset)}` : "";
}

export async function loadWorkspaceOverviewV1Live(signal?: AbortSignal, dataset?: string): Promise<{
  health: HealthStatus; schema: SchemaInfo; quality: QualityInfo;
}> {
  const suffix = datasetParam(dataset);
  const [health, schema, quality] = await Promise.all([
    fetchEnvelope<HealthStatus>("/health", { signal }),
    fetchEnvelope<SchemaInfo>(`/schema${suffix}`, { signal }),
    fetchEnvelope<QualityInfo>(`/quality${suffix}`, { signal }),
  ]);
  return { health: health.data, schema: schema.data, quality: quality.data };
}

export async function runQueryV1Live(
  question: string, page: number, pageSize: number, dataset?: string, signal?: AbortSignal,
): Promise<{ data: V1QueryData; requestId: string }> {
  return fetchEnvelope<V1QueryData>("/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildQueryBody(question, page, pageSize, dataset)),
    signal,
  });
}

export async function listDatasetsLive(signal?: AbortSignal): Promise<{ data: DatasetInfo[]; requestId: string }> {
  return fetchEnvelope<DatasetInfo[]>("/datasets", { signal });
}

export async function uploadDatasetLive(file: File, signal?: AbortSignal): Promise<{ data: DatasetInfo; requestId: string }> {
  const form = new FormData();
  form.append("file", file, file.name);
  return fetchEnvelope<DatasetInfo>("/datasets", { method: "POST", body: form, signal });
}

/** v1 数据 → 界面用的 QueryResponse。 */
export function toQueryResponse(data: V1QueryData): QueryResponse {
  return {
    question: data.question,
    sql: data.sql,
    columns: data.columns,
    rows: data.rows,
    row_count: data.row_count,
    chart_hint: data.chart_hint,
    execution_time: data.execution_time,
    valid: data.valid,
    retries: data.retries,
    from_cache: data.from_cache,
    error: null,
  };
}
