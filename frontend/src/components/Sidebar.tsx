import { useEffect, useMemo, useRef, useState } from "react";

import { DatabaseIcon, RefreshIcon, SearchIcon, TableIcon } from "../icons";
import type { DatasetInfo } from "../apiV1/types";
import type { ApiState, QueryHistoryItem } from "../types";
import { StatusDot } from "./StatusDot";

type Props = {
  api: ApiState;
  history: QueryHistoryItem[];
  onHistorySelect: (item: QueryHistoryItem) => void;
  onRefresh: () => void;
  apiKey: string;
  onApiKeyChange: (key: string) => void;
  /** P1-22：401 时为 true，聚焦 Key 输入框并提示重新粘贴 */
  authRequired?: boolean;
  datasets: DatasetInfo[];
  datasetId: string;
  onDatasetChange: (id: string) => void;
  onUploadFile: (file: File) => void;
};

const defaultDatasetOption: DatasetInfo = {
  id: "orders", name: "电商订单样本（默认）", table_name: "orders", rows: 0, created_at: "",
};

const fallbackColumns = [
  ["order_id", "INTEGER"], ["order_date", "TEXT"], ["category", "TEXT"],
  ["product", "TEXT"], ["amount", "REAL"], ["quantity", "INTEGER"],
  ["user_id", "TEXT"], ["region", "TEXT"], ["payment_method", "TEXT"],
  ["order_status", "TEXT"],
];

export function Sidebar({ api, history, onHistorySelect, onRefresh, apiKey, onApiKeyChange, authRequired = false, datasets, datasetId, onDatasetChange, onUploadFile }: Props) {
  const columns = api.schema?.columns ?? fallbackColumns.map(([name, type]) => ({ name, type }));
  const [columnQuery, setColumnQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const keyInputRef = useRef<HTMLInputElement>(null);
  const filteredColumns = useMemo(() => {
    const needle = columnQuery.trim().toLowerCase();
    return needle ? columns.filter((column) => `${column.name} ${column.type}`.toLowerCase().includes(needle)) : columns;
  }, [columnQuery, columns]);
  // P1-24：后端没有的指标显示「—」，不再伪造 5000 行 / 10 字段
  const rows = api.quality?.total_rows;
  const totalColumns = api.quality?.total_columns;
  const datasetOptions = datasets.some((d) => d.id === "orders") ? datasets : [defaultDatasetOption, ...datasets];
  // P1-24：「1 张表」硬编码改为真实可选数据集数量
  const tableCount = datasetOptions.length;

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

  useEffect(() => {
    // P1-22：Key 失效（401）时自动聚焦输入框，引导重新粘贴
    if (authRequired) keyInputRef.current?.focus();
  }, [authRequired]);

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
          <div><strong>{typeof rows === "number" ? rows.toLocaleString() : "—"}</strong><span>行数据</span></div>
          <div><strong>{typeof totalColumns === "number" ? totalColumns : "—"}</strong><span>个字段</span></div>
          <div><strong>{tableCount}</strong><span>张表</span></div>
        </div>
        {(
          <div className="dataset-switcher">
            <label className="dataset-select">
              <span>数据集</span>
              <select value={datasetId} onChange={(event) => onDatasetChange(event.target.value)} aria-label="切换数据集">
                {datasetOptions.map((option) => (
                  <option key={option.id} value={option.id}>{option.name}</option>
                ))}
              </select>
            </label>
            <label className="upload-button" title="上传 CSV/Excel（≤50MB）">
              上传数据
              <input
                type="file"
                accept=".csv,.xls,.xlsx"
                hidden
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (file) onUploadFile(file);
                }}
              />
            </label>
          </div>
        )}
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
                <span className="history-item__copy"><strong>{item.question}</strong><small>{item.rowCount == null ? "失败" : `${item.rowCount} 行 · ${item.executionTime == null ? "—" : `${item.executionTime.toFixed(2)}s`}`}</small></span>
              </button>
            ))}
          </div>
        )}
      </section>

      <footer className="sidebar-footer">
        {api.error ? (
          <StatusDot tone="warning" label={
            api.code === "AUTH_REQUIRED" ? "Key 无效，请重新粘贴"
              : api.code === "RATE_LIMITED" ? "请求受限，请稍后重试"
                : api.code === "NETWORK_ERROR" ? "网络错误，请检查连接"
                  : "API 未连接"
          } />
        ) : (
          <StatusDot tone={api.health?.database_ready ? "success" : "warning"} label={api.loading ? "正在连接数据服务" : "数据服务已连接"} />
        )}
        <span>SQLite · WAL</span>
      </footer>
      <section className="sidebar-section sidebar-section--key">
        <div className="section-label">访问密钥</div>
        <label className="key-field">
          <input
            ref={keyInputRef}
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
        {authRequired && (
          <p className="key-hint" role="alert">Key 无效或已吊销（401），请重新粘贴管理员签发的 Key。</p>
        )}
      </section>
    </aside>
  );
}
