import { useEffect, useMemo, useRef, useState } from "react";

import { DatabaseIcon, RefreshIcon, SearchIcon, TableIcon } from "../icons";
import type { ApiState, QueryHistoryItem } from "../types";
import { StatusDot } from "./StatusDot";

type Props = {
  api: ApiState;
  history: QueryHistoryItem[];
  onHistorySelect: (item: QueryHistoryItem) => void;
  onRefresh: () => void;
  apiKey: string;
  onApiKeyChange: (key: string) => void;
};

const fallbackColumns = [
  ["order_id", "INTEGER"], ["order_date", "TEXT"], ["category", "TEXT"],
  ["product", "TEXT"], ["amount", "REAL"], ["quantity", "INTEGER"],
  ["user_id", "TEXT"], ["region", "TEXT"], ["payment_method", "TEXT"],
  ["order_status", "TEXT"],
];

export function Sidebar({ api, history, onHistorySelect, onRefresh, apiKey, onApiKeyChange }: Props) {
  const columns = api.schema?.columns ?? fallbackColumns.map(([name, type]) => ({ name, type }));
  const [columnQuery, setColumnQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const filteredColumns = useMemo(() => {
    const needle = columnQuery.trim().toLowerCase();
    return needle ? columns.filter((column) => `${column.name} ${column.type}`.toLowerCase().includes(needle)) : columns;
  }, [columnQuery, columns]);
  const rows = api.quality?.total_rows ?? 5000;
  const totalColumns = api.quality?.total_columns ?? 10;

  useEffect(() => {
    function focusSearch(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (event.key === "/" && !["INPUT", "TEXTAREA"].includes(target.tagName)) {
        event.preventDefault();
        searchRef.current?.focus();
      }
    }
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  return (
    <aside className="sidebar panel-boundary">
      <section className="sidebar-section sidebar-section--dataset">
        <div className="section-label">数据源</div>
        <div className="dataset-card">
          <div className="dataset-card__icon"><DatabaseIcon /></div>
          <div className="dataset-card__copy">
            <strong>电商订单样本</strong>
            <span>sample_ecommerce.csv</span>
          </div>
          <span className="dataset-card__meta">CSV</span>
        </div>
        <div className="dataset-stats">
          <div><strong>{rows.toLocaleString()}</strong><span>行数据</span></div>
          <div><strong>{totalColumns}</strong><span>个字段</span></div>
          <div><strong>1</strong><span>张表</span></div>
        </div>
      </section>

      <section className="sidebar-section sidebar-section--schema">
        <div className="section-heading">
          <div>
            <span className="section-label">Schema</span>
            <strong><TableIcon /> {api.schema?.table_name ?? "orders"}</strong>
          </div>
          <button className="icon-button" type="button" onClick={onRefresh} aria-label="刷新数据概览">
            <RefreshIcon className={api.loading ? "is-spinning" : ""} />
          </button>
        </div>
        <label className="schema-search">
          <SearchIcon />
          <input ref={searchRef} value={columnQuery} onChange={(event) => setColumnQuery(event.target.value)} placeholder="搜索字段" aria-label="搜索字段" />
          <kbd>/</kbd>
        </label>
        <div className="column-list">
          {filteredColumns.map((column) => (
            <div className="column-row" key={column.name}>
              <span className={`column-glyph column-glyph--${column.type.toLowerCase()}`} />
              <span>{column.name}</span>
              <code>{column.type}</code>
            </div>
          ))}
          {filteredColumns.length === 0 && <p className="column-empty">没有匹配的字段</p>}
        </div>
      </section>

      <section className="history-section">
        <div className="section-heading"><span className="section-label">最近查询</span><span className="history-count">{history.length || "—"}</span></div>
        {history.length === 0 ? <p className="history-empty">运行一次查询后会出现在这里</p> : (
          <div className="history-list">
            {history.slice(0, 3).map((item) => (
              <button className="history-item" type="button" key={item.id} onClick={() => onHistorySelect(item)}>
                <span className={`history-item__dot ${item.status === "error" ? "is-error" : ""}`} />
                <span className="history-item__copy"><strong>{item.question}</strong><small>{item.rowCount} 行 · {item.executionTime.toFixed(2)}s</small></span>
              </button>
            ))}
          </div>
        )}
      </section>

      <footer className="sidebar-footer">
        {api.error ? (
          <StatusDot tone="warning" label="API 未连接 · 使用演示数据" />
        ) : (
          <StatusDot tone={api.health?.database_ready ? "success" : "warning"} label={api.loading ? "正在连接数据服务" : "数据服务已连接"} />
        )}
        <span>SQLite · WAL</span>
      </footer>
      <section className="sidebar-section sidebar-section--key">
        <div className="section-label">访问密钥</div>
        <label className="key-field">
          <input
            type="password"
            value={apiKey}
            onChange={(event) => onApiKeyChange(event.target.value)}
            placeholder="dqc_…（管理员签发）"
            aria-label="API 访问密钥"
            autoComplete="off"
          />
          {apiKey && (
            <button type="button" onClick={() => onApiKeyChange("")} aria-label="清除密钥">清除</button>
          )}
        </label>
      </section>
    </aside>
  );
}
