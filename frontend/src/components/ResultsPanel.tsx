import { useState } from "react";

import { ChartIcon, CodeIcon, TableIcon } from "../icons";
import type { QueryPhase, QueryResponse, QueryStatus } from "../types";
import { ChartPreview } from "./ChartPreview";

type Tab = "table" | "chart" | "sql";
type Props = {
  result: QueryResponse;
  status: QueryStatus;
  phase: QueryPhase;
  error: string | null;
  demo: boolean;
};

const phaseLabels: Partial<Record<QueryPhase, string>> = {
  schema: "正在读取 Schema",
  generate: "正在生成 SQL",
  validate: "正在校验查询安全性",
  execute: "正在执行查询",
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

export function ResultsPanel({ result, status, phase, error, demo }: Props) {
  const [tab, setTab] = useState<Tab>("table");
  const loading = status === "loading";
  const empty = !loading && !error && result.rows.length === 0;

  return (
    <section className="results-panel" aria-busy={loading}>
      <header className="results-header">
        <nav className="tabs" aria-label="查询结果视图">
          <button className={tab === "table" ? "is-active" : ""} type="button" onClick={() => setTab("table")}><TableIcon />结果</button>
          <button className={tab === "chart" ? "is-active" : ""} type="button" onClick={() => setTab("chart")}><ChartIcon />图表</button>
          <button className={tab === "sql" ? "is-active" : ""} type="button" onClick={() => setTab("sql")}><CodeIcon />SQL</button>
        </nav>
        <div className="result-summary">
          {demo && <span className="demo-label">演示</span>}
          <span>{result.row_count} 行</span><span>{result.columns.length} 列</span><span>{result.execution_time.toFixed(3)}s</span>
        </div>
      </header>

      <div className="results-content">
        {error && (
          <div className="result-state result-state--error" role="alert">
            <span>查询未完成</span><strong>{error}</strong><p>可以调整问题后重新运行，已有结果不会丢失。</p>
          </div>
        )}
        {empty && (
          <div className="result-state" role="status">
            <span>[ empty ]</span><strong>查询成功，但没有返回数据</strong><p>尝试放宽时间、地区或金额条件。</p>
          </div>
        )}
        {!error && !empty && tab === "table" && (
          <div className="table-wrap">
            <table>
              <thead><tr>{result.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
              <tbody>
                {result.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {result.columns.map((column, columnIndex) => (
                      <td className={typeof row[column] === "number" ? "numeric" : ""} key={column}>
                        {columnIndex === 0 && <span className="category-dot" />}{formatValue(row[column])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="table-footer"><span>{demo ? "演示快照 · 运行查询后替换为实时结果" : `问题：${result.question}`}</span><span>{result.rows.length} / {result.row_count}</span></div>
          </div>
        )}
        {!error && !empty && tab === "chart" && <ChartPreview result={result} />}
        {!error && !empty && tab === "sql" && <pre className="mobile-sql"><code>{result.sql || "-- 暂无 SQL"}</code></pre>}
        {loading && (
          <div className="query-loading" role="status" aria-live="polite">
            <div className="query-loading__mark"><i /><i /><i /></div>
            <strong>{phaseLabels[phase] ?? "正在处理查询"}</strong>
            <span>结果完成后会自动更新表格、图表和执行详情</span>
          </div>
        )}
      </div>
    </section>
  );
}
