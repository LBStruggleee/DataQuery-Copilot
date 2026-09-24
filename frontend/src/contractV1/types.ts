/**
 * v1 契约类型（demo 用模拟实现）。
 *
 * 真实落地时，这份文件应由后端 OpenAPI 描述生成，而不是手写——
 * 手写两份类型（api/models.py + types.ts）正是本次重构要消除的漂移源。
 */

export const API_VERSION = "v1" as const;

/** 统一错误码：前端按码展示，不再解析自由文本 */
export type ErrorCode =
  | "INVALID_QUESTION"
  | "SQL_REJECTED"
  | "TABLE_NOT_FOUND"
  | "QUERY_TIMEOUT"
  | "RESULT_TRUNCATED"
  | "SERVICE_UNAVAILABLE";

export type ResultCode = "OK" | ErrorCode;

/** 统一响应信封：所有 v1 接口都包这一层 */
export interface ApiEnvelope<T> {
  version: typeof API_VERSION;
  code: ResultCode;
  message: string;
  data: T | null;
  request_id: string;
}

export type ChartHint = "bar" | "line" | "pie" | "scatter" | "table";

/** 分页查询结果：rows 只含当前页，row_count 为服务端截断后的总量 */
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
  chart_hint: ChartHint;
  execution_time: number;
  valid: boolean;
  retries: number;
  from_cache: boolean;
}

export interface V1QueryParams {
  question: string;
  page: number;
  page_size: number;
}

export interface V1Paging {
  page: number;
  totalPages: number;
  truncated: boolean;
}
