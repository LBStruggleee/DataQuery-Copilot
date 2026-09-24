import type { KeyboardEvent } from "react";

import { ArrowIcon, SparkIcon } from "../icons";
import type { QueryPhase, QueryStatus } from "../types";

type Props = {
  question: string;
  status: QueryStatus;
  phase: QueryPhase;
  live: boolean;
  onQuestionChange: (question: string) => void;
  onSubmit: () => void;
};

const defaultExamples = [
  "各品类分地区销售统计",
  "销售额前 5 的商品",
  "各地区订单数量和总金额",
];

const phaseLabels: Record<QueryPhase, string> = {
  idle: "描述指标、维度和排序方式",
  schema: "正在读取表结构",
  generate: "正在生成 SQL",
  validate: "正在执行安全校验",
  execute: "正在查询 SQLite",
  complete: "查询已完成",
};

export function QueryComposer({ question, status, phase, live, onQuestionChange, onSubmit }: Props) {
  const loading = status === "loading";

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      if (question.trim() && !loading) onSubmit();
    }
  }

  return (
    <section className="query-section">
      <div className="query-heading">
        <div>
          <span className="eyebrow">自然语言查询</span>
          <h1>向数据提问，而不是写 SQL。</h1>
        </div>
        <span className={`snapshot-badge ${live ? "is-live" : ""}`}>{live ? "实时查询" : "服务未就绪"}</span>
      </div>

      <div className={`query-composer ${loading ? "is-running" : ""}`}>
        <div className="query-composer__icon"><SparkIcon className={loading ? "query-spark" : ""} /></div>
        <textarea
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          onKeyDown={handleKeyDown}
          aria-label="自然语言查询问题"
          aria-busy={loading}
          rows={3}
        />
        <div className="query-composer__footer">
          <span className={loading ? "phase-label is-active" : "phase-label"} role="status" aria-live="polite">{phaseLabels[phase]}</span>
          <button className="run-button" type="button" onClick={onSubmit} disabled={!question.trim() || loading || !live}>
            {loading ? "查询中" : "运行查询"} <kbd>⌘↵</kbd><ArrowIcon />
          </button>
        </div>
        {loading && <div className="query-progress"><i /></div>}
      </div>

      <div className="example-row">
        <span>试试这些</span>
        {(defaultExamples).map((item) => (
          <button type="button" key={item} onClick={() => onQuestionChange(item)} disabled={loading}>{item}</button>
        ))}
      </div>
    </section>
  );
}
