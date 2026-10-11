import { useCallback, useEffect, useRef, useState } from "react";

import { BrandMark } from "./components/BrandMark";
import { Inspector } from "./components/Inspector";
import { QueryComposer } from "./components/QueryComposer";
import { ResultsPanel } from "./components/ResultsPanel";
import { Sidebar } from "./components/Sidebar";
import { API_KEY_STORAGE_KEY, DEFAULT_PAGE_SIZE, V1ApiError, listDatasetsLive, loadWorkspaceOverviewV1Live, runQueryV1Live, toQueryResponse, uploadDatasetLive } from "./apiV1/client";
import { HISTORY_LIMIT, buildHistoryItem, readHistory, readTheme, saveHistory, saveTheme, type HistoryMetrics } from "./history";
import type { DatasetInfo } from "./apiV1/types";
import { GithubIcon, ThemeIcon } from "./icons";
import type { ApiState, QueryHistoryItem, QueryPhase, QueryResponse, QueryStatus } from "./types";

const initialApiState: ApiState = { health: null, schema: null, quality: null, loading: true, error: null, status: null, code: null };
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

/** P1-22：概览错误按码给出针对性短标签（连接指示器）。 */
function apiErrorLabel(code: string | null): string {
  if (code === "AUTH_REQUIRED") return "Key 无效";
  if (code === "RATE_LIMITED") return "请求受限";
  if (code === "NETWORK_ERROR") return "网络错误";
  if (code === "QUERY_TIMEOUT") return "请求超时";
  return "连接失败";
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
  const [requestId, setRequestId] = useState<string | null>(null);
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [datasetId, setDatasetId] = useState("orders");
  // P2-53：同一渲染帧内双击防并发（queryStatus 闭包值做不到同步互斥）
  const inflightRef = useRef(false);
  // P2-52：在途查询的 AbortController，切换数据集时取消
  const queryAbortRef = useRef<AbortController | null>(null);
  const [apiKey, setApiKey] = useState(() => {
    try { return localStorage.getItem(API_KEY_STORAGE_KEY) ?? ""; } catch { return ""; }
  });
  const [theme, setTheme] = useState<ThemeMode>(readTheme);

  const refreshOverview = useCallback(async (signal?: AbortSignal) => {
    setApi((current) => ({ ...current, loading: true, error: null, status: null, code: null }));
    try {
      const [overview, ds] = await Promise.all([
        loadWorkspaceOverviewV1Live(signal, datasetId),
        listDatasetsLive(signal),
      ]);
      setDatasets(ds.data);
      setApi({ health: overview.health, schema: overview.schema, quality: overview.quality, loading: false, error: null, status: null, code: null });
    } catch (error) {
      // P1-21：数据集/Key 切换导致的过期请求（AbortController 已取消）静默丢弃，不用旧响应覆盖新状态
      if (signal?.aborted) return;
      if (error instanceof V1ApiError) {
        // P1-22：保留 V1ApiError 的 status/code，供 401/429 针对性提示
        setApi((current) => ({ ...current, loading: false, error: error.message, status: error.status, code: error.code }));
      } else {
        // P1-22：网络错误（断网等非信封错误）单独提示
        setApi((current) => ({ ...current, loading: false, error: "网络错误：无法连接数据服务，请检查网络与 API 地址后重试。", status: null, code: "NETWORK_ERROR" }));
      }
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
    // P2-52：切换数据集时取消在途查询，旧数据集的迟到响应不再覆盖展示
    queryAbortRef.current?.abort();
    setDatasetId(next);
    setPaging(null);
    setQueryError(null);
    setErrorCode(null);
    setRequestId(null);
    if (inflightRef.current) {
      // 在途查询被取消：回到初始态，避免旧结果以新数据集名义展示
      setQueryStatus("idle");
      setPhase("idle");
      setResult(emptyResult);
    }
  }

  async function uploadFile(file: File) {
    setQueryError(null);
    setErrorCode(null);
    try {
      const uploaded = await uploadDatasetLive(file);
      const ds = await listDatasetsLive();
      setDatasets(ds.data);
      // P2-52 同源：上传成功同样切换数据集，取消在途查询避免旧数据集结果覆盖展示
      queryAbortRef.current?.abort();
      if (inflightRef.current) {
        setQueryStatus("idle");
        setPhase("idle");
        setResult(emptyResult);
      }
      setDatasetId(uploaded.data.id);
    } catch (error) {
      const code = error instanceof V1ApiError ? error.code : "SERVICE_UNAVAILABLE";
      setQueryStatus("error");
      setQueryError(error instanceof Error ? error.message : "上传失败");
      setErrorCode(code);
    }
  }

  useEffect(() => {
    // P1-21：useEffect 内 AbortController，依赖（数据集）变化时自动取消上一轮概览请求
    const controller = new AbortController();
    void refreshOverview(controller.signal);
    return () => controller.abort();
  }, [refreshOverview]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    saveTheme(theme);
  }, [theme]);

  function rememberQuery(question: string, status: "success" | "error", metrics?: HistoryMetrics) {
    const item = buildHistoryItem(question, status, metrics);
    setHistory((current) => {
      const nextHistory = [item, ...current.filter((entry) => entry.question !== item.question)].slice(0, HISTORY_LIMIT);
      saveHistory(nextHistory);
      return nextHistory;
    });
  }

  const submitQuery = useCallback(async (nextQuestion = question, nextPage = 1) => {
    const trimmed = nextQuestion.trim();
    if (!trimmed || inflightRef.current) return;
    if (!api.health?.database_ready || !api.health.llm_configured) {
      setQueryError("数据服务尚未就绪，请先确认 API Key 与 LLM 配置。");
      setQueryStatus("error");
      return;
    }

    setQuestion(trimmed);
    setQueryStatus("loading");
    setQueryError(null);
    setErrorCode(null);
    setRequestId(null);
    setPhase("schema");
    inflightRef.current = true;
    const controller = new AbortController();
    queryAbortRef.current = controller;
    let phaseIndex = 0;
    const phaseTimer = window.setInterval(() => {
      phaseIndex = Math.min(phaseIndex + 1, queryPhases.length - 1);
      setPhase(queryPhases[phaseIndex]);
    }, 650);

    try {
      const live = await runQueryV1Live(trimmed, nextPage, DEFAULT_PAGE_SIZE, datasetId, controller.signal);
      if (controller.signal.aborted) return;
      const nextResult = toQueryResponse(live.data);
      setResult(nextResult);
      setRequestId(live.requestId);
      setPaging({ page: live.data.page, totalPages: live.data.total_pages, truncated: live.data.truncated });
      setQueryStatus("success");
      setPhase("complete");
      rememberQuery(trimmed, "success", { rowCount: nextResult.row_count, executionTime: nextResult.execution_time });
    } catch (error) {
      // P1-21/P2-52：调用方主动取消（切换数据集）静默处理，不提示也不写历史
      if (controller.signal.aborted) return;
      let code: string;
      let message: string;
      if (error instanceof V1ApiError) {
        code = error.code;
        message = error.message;
      } else {
        // P1-22：网络错误单独提示，与业务错误区分
        code = "NETWORK_ERROR";
        message = "网络错误：无法连接查询服务，请检查网络后重试。";
      }
      setQueryStatus("error");
      setQueryError(message);
      setErrorCode(code);
      // P2-51：失败条目不沿用上一次成功结果的行数/耗时
      rememberQuery(trimmed, "error");
    } finally {
      if (queryAbortRef.current === controller) {
        inflightRef.current = false;
        queryAbortRef.current = null;
      }
      window.clearInterval(phaseTimer);
      setPhase((current) => current === "execute" || current === "schema" || current === "generate" || current === "validate" ? "complete" : current);
    }
  }, [api.health, datasetId, question]);

  const live = Boolean(api.health?.database_ready && api.health.llm_configured);
  // P1-22：401 时聚焦侧栏 Key 输入框并提示重新粘贴
  const authRequired = api.status === 401 || api.code === "AUTH_REQUIRED" || errorCode === "AUTH_REQUIRED";

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><BrandMark /><strong>DataQuery</strong><span>Copilot</span></div>
        <div className="topbar__context"><span>工作区</span><i>/</i><strong>电商订单分析</strong></div>
        <div className="topbar__actions">
          <span className={`connection-pill ${api.error || !live ? "is-offline" : ""}`}><i />{api.error ? apiErrorLabel(api.code) : live ? "API 已连接" : "等待配置"}</span>
          <button className="icon-button" type="button" onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")} aria-label={theme === "dark" ? "切换到浅色主题" : "切换到深色主题"} title={theme === "dark" ? "浅色主题" : "深色主题"}><ThemeIcon /></button>
          <a className="icon-button" href="https://github.com/LBStruggleee/DataQuery-Copilot" target="_blank" rel="noreferrer" aria-label="打开 GitHub 仓库" title="打开 GitHub 仓库"><GithubIcon /></a>
          <div className="avatar" aria-label="用户 LB">LB</div>
        </div>
      </header>

      <div className="workspace">
        <Sidebar api={api} history={history} onHistorySelect={(item) => void submitQuery(item.question)} onRefresh={() => void refreshOverview()} apiKey={apiKey} onApiKeyChange={changeApiKey} authRequired={authRequired} datasets={datasets} datasetId={datasetId} onDatasetChange={changeDataset} onUploadFile={(file) => void uploadFile(file)} />
        <main className="main-stage">
          <QueryComposer question={question} status={queryStatus} phase={phase} live={live} onQuestionChange={setQuestion} onSubmit={() => void submitQuery()} />
          <ResultsPanel result={result} status={queryStatus} phase={phase} error={queryError} paging={paging} onPageChange={(page) => void submitQuery(question, page)} errorCode={errorCode} />
        </main>
        <Inspector api={api} result={result} status={queryStatus} phase={phase} error={queryError} requestId={requestId} />
      </div>
    </div>
  );
}
