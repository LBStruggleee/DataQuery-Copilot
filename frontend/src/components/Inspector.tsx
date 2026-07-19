import { useState } from "react";

import { CheckIcon, CodeIcon, CopyIcon } from "../icons";
import type { ApiState, QueryPhase, QueryResponse, QueryStatus } from "../types";
import { StatusDot } from "./StatusDot";

type Props = { api: ApiState; result: QueryResponse; status: QueryStatus; phase: QueryPhase; error: string | null };

const phases: Array<{ id: QueryPhase; label: string }> = [
  { id: "schema", label: "读取 Schema" },
  { id: "generate", label: "生成 SQL" },
  { id: "validate", label: "安全校验" },
  { id: "execute", label: "执行查询" },
];

function phaseIndex(phase: QueryPhase) {
  return phases.findIndex((item) => item.id === phase);
}

export function Inspector({ api, result, status, phase, error }: Props) {
  const [copied, setCopied] = useState(false);
  const missingCount = api.quality
    ? Object.values(api.quality.missing_values).reduce((sum, value) => sum + value, 0)
    : 50;
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
        <div className="quality-heading"><div><span className="section-label">数据质量</span><strong>{api.quality?.total_rows.toLocaleString() ?? "5,000"} 行扫描完成</strong></div><span>{api.quality ? "实时" : "演示"}</span></div>
        <div className="quality-grid">
          <div><strong>{missingCount}</strong><span>缺失值</span></div>
          <div><strong>{api.quality?.duplicates ?? 0}</strong><span>重复行</span></div>
          <div><strong>5</strong><span>异常值</span></div>
        </div>
        <div className="quality-note"><span>amount</span><div><i style={{ width: `${Math.max((missingCount / (api.quality?.total_rows ?? 5000)) * 100, 1)}%` }} /></div><strong>{((missingCount / (api.quality?.total_rows ?? 5000)) * 100).toFixed(1)}%</strong></div>
      </section>

      <footer className="inspector-footer">
        <span>查询 ID</span><code>{status === "idle" ? "demo_snapshot" : `qry_${Math.abs(result.question.length * 7919).toString(16).slice(0, 8)}`}</code>
      </footer>
    </aside>
  );
}
