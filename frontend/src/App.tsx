import { useCallback, useEffect, useState } from "react";

import { BrandMark } from "./components/BrandMark";
import { Inspector } from "./components/Inspector";
import { QueryComposer } from "./components/QueryComposer";
import { ResultsPanel } from "./components/ResultsPanel";
import { Sidebar } from "./components/Sidebar";
import { API_KEY_STORAGE_KEY, DEFAULT_PAGE_SIZE, V1ApiError, listDatasetsLive, loadWorkspaceOverviewV1Live, runQueryV1Live, toQueryResponse, uploadDatasetLive } from "./apiV1/client";
import type { DatasetInfo } from "./apiV1/types";
import { GithubIcon, ThemeIcon } from "./icons";
import type { ApiState, QueryHistoryItem, QueryPhase, QueryResponse, QueryStatus } from "./types";

const HISTORY_KEY = "dataquery-copilot.query-history";
const initialApiState: ApiState = { health: null, schema: null, quality: null, loading: true, error: null };
const queryPhases: QueryPhase[] = ["schema", "generate", "validate", "execute"];
const emptyResult: QueryResponse = {
  question: "",
  sql: "",
  columns: [],
  rows: [],
  row_count: 0,
  chart_hint: "table",
  execution_time: 0,
  valid: false,
  retries: 0,
  from_cache: false,
  error: null,
};
type ThemeMode = "dark" | "light";

function readHistory(): QueryHistoryItem[] {
  try {
    const stored = localStorage.getItem(HISTORY_KEY);
    return stored ? JSON.parse(stored) as QueryHistoryItem[] : [];
  } catch {
    return [];
  }
}

export default function App() {
  const [api, setApi] = useState<ApiState>(initialApiState);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResponse>(emptyResult);
  const [queryStatus, setQueryStatus] = useState<QueryStatus>("idle");
  const [phase, setPhase] = useState<QueryPhase>("idle");
  const [queryError, setQueryError] = useState<string | null>(null);
  const [history, setHistory] = useState<QueryHistoryItem[]>(readHistory);
  const [paging, setPaging] = useState<{ page: number; totalPages: number; truncated: boolean } | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [datasetId, setDatasetId] = useState("orders");
  const [apiKey, setApiKey] = useState(() => {
    try { return localStorage.getItem(API_KEY_STORAGE_KEY) ?? ""; } catch { return ""; }
  });
  const [theme, setTheme] = useState<ThemeMode>(() => {
    try { return localStorage.getItem("dataquery-copilot.theme") === "light" ? "light" : "dark"; } catch { return "dark"; }
  });

  const refreshOverview = useCallback(async () => {
    setApi((current) => ({ ...current, loading: true, error: null }));
    try {
      const [overview, ds] = await Promise.all([
        loadWorkspaceOverviewV1Live(undefined, datasetId),
        listDatasetsLive(),
      ]);
      setDatasets(ds.data);
      setApi({ health: overview.health, schema: overview.schema, quality: overview.quality, loading: false, error: null });
    } catch (error) {
      setApi((current) => ({ ...current, loading: false, error: error instanceof Error ? error.message : "无法连接数据服务" }));
    }
  }, [datasetId]);

  function changeApiKey(next: string) {
    setApiKey(next);
    try {
      if (next) localStorage.setItem(API_KEY_STORAGE_KEY, next);
      else localStorage.removeItem(API_KEY_STORAGE_KEY);
    } catch { /* 隐私模式下仅内存生效 */ }
    void refreshOverview();
  }

  function changeDataset(next: string) {
    if (next === datasetId) return;
    setDatasetId(next);
    setPaging(null);
    setQueryError(null);
    setErrorCode(null);
  }

  async function uploadFile(file: File) {
    setQueryError(null);
    setErrorCode(null);
    try {
      const uploaded = await uploadDatasetLive(file);
      const ds = await listDatasetsLive();
      setDatasets(ds.data);
      setDatasetId(uploaded.data.id);
    } catch (error) {
      const code = error instanceof V1ApiError ? error.code : "SERVICE_UNAVAILABLE";
      setQueryStatus("error");
      setQueryError(error instanceof Error ? error.message : "上传失败");
      setErrorCode(code);
    }
  }

  useEffect(() => { void refreshOverview(); }, [refreshOverview]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("dataquery-copilot.theme", theme);
  }, [theme]);

  function rememberQuery(next: QueryResponse, status: "success" | "error") {
    const item: QueryHistoryItem = {
      id: `${Date.now()}-${next.question}`,
      question: next.question,
      timestamp: Date.now(),
      status,
      rowCount: next.row_count,
      executionTime: next.execution_time,
    };
    setHistory((current) => {
      const nextHistory = [item, ...current.filter((entry) => entry.question !== item.question)].slice(0, 8);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(nextHistory));
      return nextHistory;
    });
  }

  const submitQuery = useCallback(async (nextQuestion = question, nextPage = 1) => {
    const trimmed = nextQuestion.trim();
    if (!trimmed || queryStatus === "loading") return;
    if (!api.health?.database_ready || !api.health.llm_configured) {
      setQueryError("数据服务尚未就绪，请先确认 API Key 与 LLM 配置。");
      setQueryStatus("error");
      return;
    }

    setQuestion(trimmed);
    setQueryStatus("loading");
    setQueryError(null);
    setErrorCode(null);
    setPhase("schema");
    let phaseIndex = 0;
    const phaseTimer = window.setInterval(() => {
      phaseIndex = Math.min(phaseIndex + 1, queryPhases.length - 1);
      setPhase(queryPhases[phaseIndex]);
    }, 650);

    try {
      const live = await runQueryV1Live(trimmed, nextPage, DEFAULT_PAGE_SIZE, datasetId);
      const nextResult = toQueryResponse(live.data);
      setResult(nextResult);
      setPaging({ page: live.data.page, totalPages: live.data.total_pages, truncated: live.data.truncated });
      setQueryStatus("success");
      setPhase("complete");
      rememberQuery(nextResult, "success");
    } catch (error) {
      const code = error instanceof V1ApiError ? error.code : "SERVICE_UNAVAILABLE";
      const message = error instanceof Error ? error.message : "查询服务执行失败";
      setQueryStatus("error");
      setQueryError(message);
      setErrorCode(code);
      rememberQuery({ ...result, question: trimmed, error: message }, "error");
    } finally {
      window.clearInterval(phaseTimer);
      setPhase((current) => current === "execute" || current === "schema" || current === "generate" || current === "validate" ? "complete" : current);
    }
  }, [api.health, datasetId, question, queryStatus, result]);

  const live = Boolean(api.health?.database_ready && api.health.llm_configured);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><BrandMark /><strong>DataQuery</strong><span>Copilot</span></div>
        <div className="topbar__context"><span>工作区</span><i>/</i><strong>电商订单分析</strong></div>
        <div className="topbar__actions">
          <span className={`connection-pill ${api.error || !live ? "is-offline" : ""}`}><i />{api.error ? "连接失败" : live ? "API 已连接" : "等待配置"}</span>
          <button className="icon-button" type="button" onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")} aria-label={theme === "dark" ? "切换到浅色主题" : "切换到深色主题"} title={theme === "dark" ? "浅色主题" : "深色主题"}><ThemeIcon /></button>
          <a className="icon-button" href="https://github.com/LBStruggleee/DataQuery-Copilot" target="_blank" rel="noreferrer" aria-label="打开 GitHub 仓库" title="打开 GitHub 仓库"><GithubIcon /></a>
          <div className="avatar" aria-label="用户 LB">LB</div>
        </div>
      </header>

      <div className="workspace">
        <Sidebar api={api} history={history} onHistorySelect={(item) => void submitQuery(item.question)} onRefresh={() => void refreshOverview()} apiKey={apiKey} onApiKeyChange={changeApiKey} datasets={datasets} datasetId={datasetId} onDatasetChange={changeDataset} onUploadFile={(file) => void uploadFile(file)} />
        <main className="main-stage">
          <QueryComposer question={question} status={queryStatus} phase={phase} live={live} onQuestionChange={setQuestion} onSubmit={() => void submitQuery()} />
          <ResultsPanel result={result} status={queryStatus} phase={phase} error={queryError} paging={paging} onPageChange={(page) => void submitQuery(question, page)} errorCode={errorCode} />
        </main>
        <Inspector api={api} result={result} status={queryStatus} phase={phase} error={queryError} />
      </div>
    </div>
  );
}
