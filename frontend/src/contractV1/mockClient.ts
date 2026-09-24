/**
 * v1 契约的 mock 实现（demo 用）。
 *
 * 只模拟「修改文档」里约定的三件事：
 * 1. 统一响应信封 + 错误码（ApiEnvelope / ErrorCode）
 * 2. 分页 + 行数上限（page / page_size / truncated）
 * 3. 真实落地后，这个文件的调用位置不变，只需把 mock 换成 fetch
 */
import type { HealthStatus, QualityInfo, QueryResponse, SchemaInfo } from "../types";
import type { ApiEnvelope, ErrorCode, V1QueryData } from "./types";

export const V1_PAGE_SIZE = 10;
/** 服务端行数上限：超过即截断，置 truncated 标记 */
const V1_MAX_ROWS = 100;

const CATEGORIES = ["电子产品", "食品饮料", "服装鞋帽", "家居用品", "美妆护肤", "图书文具", "运动户外", "母婴用品"];
const REGIONS = ["华东", "华北", "华南", "西南"];
const MONTHS = ["06", "07", "08", "09", "10", "11"];

export const V1_EXAMPLE_QUESTIONS = [
  "各品类分地区销售统计",
  "超大结果集导出",
  "删掉订单表",
  "查询不存在的表",
];

let requestSeq = 0;
const servedCache = new Map<string, true>();

function nextRequestId(): string {
  requestSeq += 1;
  return `req_${Date.now().toString(36)}${requestSeq.toString(36)}`;
}

function ok<T>(data: T, message = "ok"): ApiEnvelope<T> {
  return { version: "v1", code: "OK", message, data, request_id: nextRequestId() };
}

function fail(code: ErrorCode, message: string): ApiEnvelope<null> {
  return { version: "v1", code, message, data: null, request_id: nextRequestId() };
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      window.clearTimeout(timer);
      reject(new DOMException("aborted", "AbortError"));
    }, { once: true });
  });
}

type MockRow = Record<string, unknown>;

/** 确定性 mock 数据集：无随机数，快照稳定 */
function buildDataset(big: boolean): { columns: string[]; rows: MockRow[] } {
  const rows: MockRow[] = [];
  if (!big) {
    const columns = ["category", "region", "order_count", "total_sales"];
    CATEGORIES.forEach((category, ci) => {
      REGIONS.forEach((region, ri) => {
        const orderCount = 500 + ((ci * 37 + ri * 53) % 400);
        const totalSales = Math.round(orderCount * (28 + ((ci * 13 + ri * 7) % 160)) * 100) / 100;
        rows.push({ category, region, order_count: orderCount, total_sales: totalSales });
      });
    });
    return { columns, rows };
  }
  const columns = ["category", "region", "month", "order_count", "total_sales"];
  CATEGORIES.forEach((category, ci) => {
    REGIONS.forEach((region, ri) => {
      MONTHS.forEach((month, mi) => {
        const orderCount = 120 + ((ci * 41 + ri * 29 + mi * 17) % 260);
        const totalSales = Math.round(orderCount * (24 + ((ci * 11 + ri * 5 + mi * 3) % 150)) * 100) / 100;
        rows.push({ category, region, month: `2026-${month}`, order_count: orderCount, total_sales: totalSales });
      });
    });
  });
  return { columns, rows };
}

function buildSql(big: boolean): string {
  return big
    ? "SELECT\n  category,\n  region,\n  strftime('%Y-%m', order_date) AS month,\n  COUNT(*) AS order_count,\n  ROUND(SUM(amount), 2) AS total_sales\nFROM orders\nGROUP BY category, region, month\nORDER BY total_sales DESC;"
    : "SELECT\n  category,\n  region,\n  COUNT(*) AS order_count,\n  ROUND(SUM(amount), 2) AS total_sales\nFROM orders\nGROUP BY category, region\nORDER BY total_sales DESC;";
}

/** mock 版工作区概览：health 直接就绪，方便走查查询流程 */
export async function loadWorkspaceOverviewV1(): Promise<{
  health: ApiEnvelope<HealthStatus>;
  schema: ApiEnvelope<SchemaInfo>;
  quality: ApiEnvelope<QualityInfo>;
}> {
  await delay(400);
  return {
    health: ok({ status: "ok", database_ready: true, llm_configured: true }),
    schema: ok({
      table_name: "orders",
      columns: [
        { name: "order_id", type: "INTEGER" },
        { name: "order_date", type: "TEXT" },
        { name: "category", type: "TEXT" },
        { name: "amount", type: "REAL" },
        { name: "quantity", type: "INTEGER" },
        { name: "region", type: "TEXT" },
      ],
    }),
    quality: ok({
      table_name: "orders",
      total_rows: 5000,
      total_columns: 10,
      missing_values: { amount: 50 },
      duplicates: 3,
      column_types: { order_id: "INTEGER", amount: "REAL", category: "TEXT" },
    }),
  };
}

export async function runQueryV1(
  question: string,
  page: number,
  pageSize: number,
  signal?: AbortSignal,
): Promise<ApiEnvelope<V1QueryData | null>> {
  await delay(800, signal);
  const trimmed = question.trim();
  const lowered = trimmed.toLowerCase();

  if (/(删|删除|drop|delete|update|insert)/i.test(trimmed)) {
    return fail("SQL_REJECTED", "SQL 安全校验未通过：仅允许 SELECT 查询");
  }
  if (trimmed.includes("不存在")) {
    return fail("TABLE_NOT_FOUND", "数据表不存在：orders_archive");
  }
  if (trimmed.includes("超时")) {
    return fail("QUERY_TIMEOUT", "查询执行超时（30s），请缩小时间或地区范围后重试");
  }

  const big = /(超大|全部|导出)/.test(trimmed);
  const { columns, rows } = buildDataset(big);
  const truncated = rows.length > V1_MAX_ROWS;
  const visible = truncated ? rows.slice(0, V1_MAX_ROWS) : rows;
  const totalPages = Math.max(1, Math.ceil(visible.length / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const pageRows = visible.slice((safePage - 1) * pageSize, safePage * pageSize);

  const cacheKey = `${trimmed}::${safePage}::${pageSize}`;
  const fromCache = servedCache.has(cacheKey);
  servedCache.set(cacheKey, true);

  return ok(
    {
      question: trimmed,
      sql: buildSql(big),
      columns,
      rows: pageRows,
      row_count: visible.length,
      page: safePage,
      page_size: pageSize,
      total_pages: totalPages,
      truncated,
      chart_hint: "bar",
      execution_time: 0.042,
      valid: true,
      retries: 0,
      from_cache: fromCache,
    },
    truncated ? `结果超过 ${V1_MAX_ROWS} 行上限，仅返回前 ${V1_MAX_ROWS} 行` : "ok",
  );
}

/** v1 数据 → 现有 QueryResponse（真实落地后由 codegen 类型直接替代） */
export function toLegacyResponse(data: V1QueryData): QueryResponse {
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
