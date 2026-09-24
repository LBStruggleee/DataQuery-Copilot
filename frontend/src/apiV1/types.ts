/**
 * 契约源：后端 api/models.py（OpenAPI）。
 * 本文件为生成产物快照，勿手改业务逻辑；契约变更时重新生成。
 */
export const API_VERSION = "v1" as const;

export type ErrorCode =
  | "INVALID_QUESTION"
  | "SQL_REJECTED"
  | "TABLE_NOT_FOUND"
  | "QUERY_TIMEOUT"
  | "RESULT_TRUNCATED"
  | "SERVICE_UNAVAILABLE"
  | "QUERY_FAILED";

export interface ApiEnvelope<T> {
  version: typeof API_VERSION;
  code: "OK" | ErrorCode;
  message: string;
  data: T | null;
  request_id: string;
}

export interface V1QueryData {
  question: string;
  sql: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  row_count: number;
  page: number;
  page_size: number;
  total_pages: number;
  truncated: boolean;
  chart_hint: "bar" | "line" | "pie" | "scatter" | "table";
  execution_time: number;
  valid: boolean;
  retries: number;
  from_cache: boolean;
}
