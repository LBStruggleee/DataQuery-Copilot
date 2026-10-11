export type HealthStatus = {
  status: "ok" | "degraded";
  database_ready: boolean;
  llm_configured: boolean;
};

export type SchemaColumn = {
  name: string;
  type: string;
};

export type SchemaInfo = {
  table_name: string;
  columns: SchemaColumn[];
};

export type QualityInfo = {
  table_name: string;
  total_rows: number;
  total_columns: number;
  missing_values: Record<string, number>;
  duplicates: number;
  column_types: Record<string, string>;
};

export type ApiState = {
  health: HealthStatus | null;
  schema: SchemaInfo | null;
  quality: QualityInfo | null;
  loading: boolean;
  error: string | null;
  /** P1-22：概览路径保留 HTTP 状态码（401/429 等），null = 非信封错误（网络错误） */
  status: number | null;
  /** P1-22：概览路径保留错误码；"NETWORK_ERROR" 表示网络不可达 */
  code: string | null;
};

export type QueryResponse = {
  question: string;
  sql: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  row_count: number;
  chart_hint: "bar" | "line" | "pie" | "scatter" | "table";
  execution_time: number;
  valid: boolean;
  retries: number;
  from_cache: boolean;
  error: string | null;
};

export type QueryPhase = "idle" | "schema" | "generate" | "validate" | "execute" | "complete";
export type QueryStatus = "idle" | "loading" | "success" | "error";

export type QueryHistoryItem = {
  id: string;
  question: string;
  timestamp: number;
  status: "success" | "error";
  /** P2-51：失败条目无行数/耗时，记 null 而非沿用上一次成功结果 */
  rowCount: number | null;
  executionTime: number | null;
};
