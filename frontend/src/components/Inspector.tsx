import { useState } from "react";

import { CheckIcon, CodeIcon, CopyIcon } from "../icons";
import type { ApiState, QueryPhase, QueryResponse, QueryStatus } from "../types";
import { StatusDot } from "./StatusDot";

type Props = { api: ApiState; result: QueryResponse; status: QueryStatus; phase: QueryPhase; error: string | null; /** P1-24：App 保存的 runQueryV1Live 真实 request_id */ requestId?: string | null };

const phases: Array<{ id: QueryPhase; label: string }> = [
  { id: "schema", label: "读取 Schema" },
  { id: "generate", label: "生成 SQL" },
  { id: "validate", label: "安全校验" },
  { id: "execute", label: "执行查询" },
];

function phaseIndex(phase: QueryPhase) {
  return phases.findIndex((item) => item.id === phase);
}

export function Inspector({ api, result, status, phase, error, requestId = null }: Props) {
  const [copied, setCopied] = useState(false);
  // P1-24：缺失值按真实 quality 数据展示；后端没有的指标（异常值）固定显示「—」，不再伪造
  const missingEntries = api.quality
    ? Object.entries(api.quality.missing_values).filter(([, value]) => value > 0).slice(0, 3)
    : [];
  const currentPhase = phaseIndex(phase);

  async function copySql() {
    if (!result.sql) return;
    try { await navigator.clipboard?.writeText(result.sql); } catch { /* clipboard permission is optional */ }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  const executionLabel = status === "loading" ? "执行中" : error ? "失败" : result.valid ? "成功" : "未校验";
  const executionTone = status === "loading" ? "warning" : error ? "warning" : "success";

  return (
    <aside className="inspector panel-boundary">
      <section className="inspector-section inspector-section--sql">
        <div className="inspector-heading">
          <div><CodeIcon /><span>生成的 SQL</span></div>
          <button className="icon-button icon-button--with-label" type="button" onClick={copySql} disabled={!result.sql}>
            {copied ? <CheckIcon /> : <CopyIcon />}{copied ? "已复制" : "复制"}
          </button>
        </div>
        <pre className="sql-code"><code>{result.sql || "-- 查询后显示生成的 SQL"}</code></pre>
        <StatusDot tone={result.valid ? "success" : "muted"} label={result.valid ? "安全校验已通过" : "等待查询"} />
      </section>

      <section className="inspector-section inspector-section--process">
        <div className="section-label">查询阶段</div>
        <div className="phase-list">
          {phases.map((item, index) => {
            const done = status === "success" && index <= 3;
            const active = status === "loading" && index === currentPhase;
            return <div className={`phase-row ${done ? "is-done" : ""} ${active ? "is-active" : ""}`} key={item.id}><span>{done ? "✓" : index + 1}</span><label>{item.label}</label>{active && <i />}</div>;
          })}
        </div>
      </section>

      <section className="inspector-section">
        <div className="section-label">执行详情</div>
        <dl className="metric-list">
          <div><dt>状态</dt><dd><StatusDot tone={executionTone} label={executionLabel} /></dd></div>
          <div><dt>执行时间</dt><dd>{result.execution_time.toFixed(3)} s</dd></div>
          <div><dt>返回行数</dt><dd>{result.row_count}</dd></div>
          <div><dt>自动重试</dt><dd>{result.retries} 次</dd></div>
          <div><dt>缓存</dt><dd>{result.from_cache ? "已命中" : "未命中"}</dd></div>
        </dl>
      </section>

      <section className="inspector-section inspector-section--quality">
        <div className="quality-heading"><div><span className="section-label">数据质量</span><strong>{api.quality?.total_rows.toLocaleString() ?? "—"} 行扫描完成</strong></div><span>{api.quality ? "实时" : "—"}</span></div>
        <div className="quality-grid">
          <div><strong>{api.quality ? missingEntries.reduce((sum, [, value]) => sum + value, 0) : "—"}</strong><span>缺失值</span></div>
          <div><strong>{api.quality ? api.quality.duplicates.toLocaleString() : "—"}</strong><span>重复行</span></div>
          <div><strong>—</strong><span>异常值</span></div>
        </div>
        {/* P1-24：缺失条按真实缺失列渲染（后端 quality.missing_values），不再固定标注 amount */}
        {api.quality && missingEntries.length > 0 ? missingEntries.map(([column, count]) => {
          const total = api.quality?.total_rows ?? 0;
          const ratio = total > 0 ? (count / total) * 100 : 0;
          return (
            <div className="quality-note" key={column}>
              <span>{column}</span>
              <div><i style={{ width: `${Math.max(ratio, 1)}%` }} /></div>
              <strong>{ratio.toFixed(1)}%</strong>
            </div>
          );
        }) : (
          <div className="quality-note"><span>{api.quality ? "无缺失值" : "—"}</span></div>
        )}
      </section>

      <footer className="inspector-footer">
        {/* P1-24：展示后端返回的真实 request_id，不再用问题长度伪造 qry_ 哈希 */}
        <span>查询 ID</span><code>{status === "idle" || !requestId ? "—" : requestId}</code>
      </footer>
    </aside>
  );
}
