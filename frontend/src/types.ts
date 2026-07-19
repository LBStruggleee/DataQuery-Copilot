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
  rowCount: number;
  executionTime: number;
};
