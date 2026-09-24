import { useCallback, useEffect, useMemo, useState } from "react";

import { loadWorkspaceOverview, runQuery } from "./api";
import { BrandMark } from "./components/BrandMark";
import { Inspector } from "./components/Inspector";
import { QueryComposer } from "./components/QueryComposer";
import { ResultsPanel } from "./components/ResultsPanel";
import { Sidebar } from "./components/Sidebar";
import { V1_EXAMPLE_QUESTIONS, V1_PAGE_SIZE, loadWorkspaceOverviewV1, runQueryV1, toLegacyResponse } from "./contractV1/mockClient";
import type { V1Paging } from "./contractV1/types";
import { V1ApiError, loadWorkspaceOverviewV1Live, runQueryV1Live } from "./apiV1/client";
import { GithubIcon, ThemeIcon } from "./icons";
import { demoQueryResponse } from "./mockData";
import type { ApiState, QueryHistoryItem, QueryPhase, QueryResponse, QueryStatus } from "./types";

const HISTORY_KEY = "dataquery-copilot.query-history";
const initialApiState: ApiState = { health: null, schema: null, quality: null, loading: true, error: null };
const queryPhases: QueryPhase[] = ["schema", "generate", "validate", "execute"];
type ThemeMode = "dark" | "light";
type ContractMode = "v0" | "v1";

function readContractMode(): ContractMode {
  try {
    return new URLSearchParams(window.location.search).get("contract") === "v1" ? "v1" : "v0";
  } catch {
    return "v0";
  }
}

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
  const [question, setQuestion] = useState(demoQueryResponse.question);
  const [result, setResult] = useState<QueryResponse>(demoQueryResponse);
  const [queryStatus, setQueryStatus] = useState<QueryStatus>("idle");
  const [phase, setPhase] = useState<QueryPhase>("idle");
  const [queryError, setQueryError] = useState<string | null>(null);
  const [history, setHistory] = useState<QueryHistoryItem[]>(readHistory);
  const [isDemo, setIsDemo] = useState(true);
  const [contract, setContract] = useState<ContractMode>(readContractMode);
  const [paging, setPaging] = useState<V1Paging | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [v1Source, setV1Source] = useState<"live" | "mock">("live");
  const forceMock = useMemo(() => {
    try { return new URLSearchParams(window.location.search).get("mock") === "1"; } catch { return false; }
  }, []);
  const [theme, setTheme] = useState<ThemeMode>(() => {
    try { return localStorage.getItem("dataquery-copilot.theme") === "light" ? "light" : "dark"; } catch { return "dark"; }
  });

  const refreshOverview = useCallback(async () => {
    setApi((current) => ({ ...current, loading: true, error: null }));
    try {
      if (contract === "v1") {
        if (!forceMock) {
          try {
            const live = await loadWorkspaceOverviewV1Live();
            setApi({ health: live.health, schema: live.schema, quality: live.quality, loading: false, error: null });
            setV1Source("live");
            return;
          } catch (error) {
            if (!(error instanceof TypeError)) throw error;
            // 网络失败 → 回退 mock 替身
          }
        }
        const overview = await loadWorkspaceOverviewV1();
        if (overview.health.code !== "OK" || !overview.health.data) throw new Error(overview.health.message);
        setApi({
          health: overview.health.data,
          schema: overview.schema.data,
          quality: overview.quality.data,
          loading: false,
          error: null,
        });
        setV1Source("mock");
        return;
      }
      const overview = await loadWorkspaceOverview();
      setApi({ ...overview, loading: false, error: null });
    } catch (error) {
      setApi((current) => ({ ...current, loading: false, error: error instanceof Error ? error.message : "无法连接数据服务" }));
    }
  }, [contract]);

  /** v0 现状 / v1 演示切换：只换数据源，界面同一套 */
  function switchContract(next: ContractMode) {
    if (next === contract) return;
    setContract(next);
    try {
      const url = new URL(window.location.href);
      if (next === "v1") url.searchParams.set("contract", "v1");
      else url.searchParams.delete("contract");
      window.history.replaceState(null, "", url.toString());
    } catch { /* URL 同步失败不影响演示 */ }
    setResult(demoQueryResponse);
    setIsDemo(true);
    setQueryStatus("idle");
    setPhase("idle");
    setQueryError(null);
    setErrorCode(null);
    setPaging(null);
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

  const submitQueryV1 = useCallback(async (trimmed: string, nextPage = 1) => {
    if (!trimmed || queryStatus === "loading") return;
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
      if (!forceMock) {
        try {
          const live = await runQueryV1Live(trimmed, nextPage, V1_PAGE_SIZE);
          const nextResult = toLegacyResponse(live.data);
          setResult(nextResult);
          setIsDemo(false);
          setPaging({ page: live.data.page, totalPages: live.data.total_pages, truncated: live.data.truncated });
          setV1Source("live");
          setQueryStatus("success");
          setPhase("complete");
          rememberQuery(nextResult, "success");
          return;
        } catch (error) {
          if (error instanceof TypeError) {
            // 网络失败 → 回退 mock 替身
          } else {
            const code = error instanceof V1ApiError ? error.code : "SERVICE_UNAVAILABLE";
            const message = error instanceof Error ? error.message : "查询服务执行失败";
            setQueryStatus("error");
            setQueryError(message);
            setErrorCode(code);
            setV1Source("live");
            rememberQuery({ ...result, question: trimmed, error: message }, "error");
            return;
          }
        }
      }
      const envelope = await runQueryV1(trimmed, nextPage, V1_PAGE_SIZE);
      setV1Source("mock");
      if (envelope.code !== "OK" || !envelope.data) {
        setQueryStatus("error");
        setQueryError(envelope.message);
        setErrorCode(envelope.code);
        rememberQuery({ ...result, question: trimmed, error: envelope.message }, "error");
        return;
      }
      const data = envelope.data;
      const nextResult = toLegacyResponse(data);
      setResult(nextResult);
      setIsDemo(false);
      setPaging({ page: data.page, totalPages: data.total_pages, truncated: data.truncated });
      setQueryStatus("success");
      setPhase("complete");
      rememberQuery(nextResult, "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "查询服务执行失败";
      setQueryStatus("error");
      setQueryError(message);
      setErrorCode("SERVICE_UNAVAILABLE");
      rememberQuery({ ...result, question: trimmed, error: message }, "error");
    } finally {
      window.clearInterval(phaseTimer);
      setPhase((current) => current === "execute" || current === "schema" || current === "generate" || current === "validate" ? "complete" : current);
    }
  }, [queryStatus, result]);

  const submitQuery = useCallback(async (nextQuestion = question, nextPage = 1) => {
    const trimmed = nextQuestion.trim();
    if (contract === "v1") {
      await submitQueryV1(trimmed, nextPage);
      return;
    }
    if (!trimmed || queryStatus === "loading") return;
    if (!api.health?.database_ready || !api.health.llm_configured) {
      setQueryError("数据服务尚未就绪，请先确认 API 和 LLM 配置。");
      setQueryStatus("error");
      return;
    }

    setQuestion(trimmed);
    setQueryStatus("loading");
    setQueryError(null);
    setPhase("schema");
    let phaseIndex = 0;
    const phaseTimer = window.setInterval(() => {
      phaseIndex = Math.min(phaseIndex + 1, queryPhases.length - 1);
      setPhase(queryPhases[phaseIndex]);
    }, 650);

    try {
      const nextResult = await runQuery(trimmed);
      setResult(nextResult);
      setIsDemo(false);
      if (nextResult.error) {
        setQueryStatus("error");
        setQueryError(nextResult.error);
        rememberQuery(nextResult, "error");
      } else {
        setQueryStatus("success");
        setPhase("complete");
        rememberQuery(nextResult, "success");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "查询服务执行失败";
      setQueryStatus("error");
      setQueryError(message);
      rememberQuery({ ...result, question: trimmed, error: message }, "error");
    } finally {
      window.clearInterval(phaseTimer);
      setPhase((current) => current === "execute" || current === "schema" || current === "generate" || current === "validate" ? "complete" : current);
    }
  }, [api.health, contract, question, queryStatus, result, submitQueryV1]);

  const live = Boolean(api.health?.database_ready && api.health.llm_configured);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><BrandMark /><strong>DataQuery</strong><span>Copilot</span></div>
        <div className="topbar__context"><span>工作区</span><i>/</i><strong>电商订单分析</strong>
          <span className="contract-toggle" role="group" aria-label="契约版本切换">
            <button type="button" className={contract === "v0" ? "is-active" : ""} onClick={() => switchContract("v0")}>v0 现状</button>
            <button type="button" className={contract === "v1" ? "is-active" : ""} onClick={() => switchContract("v1")}>v1 演示</button>
          </span>
          {contract === "v1" ? <span className="v1-pill">{v1Source === "live" ? "v1 · 真实" : "v1 · mock替身"}</span> : <span className="v0-pill">v0</span>}
        </div>
        <div className="topbar__actions">
          <span className={`connection-pill ${api.error || !live || (contract === "v1" && v1Source === "mock") ? "is-offline" : ""}`}><i />{contract === "v1" && v1Source === "mock" ? "v1 演示 · mock" : api.error ? "演示模式" : live ? "API 已连接" : "等待配置"}</span>
          <button className="icon-button" type="button" onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")} aria-label={theme === "dark" ? "切换到浅色主题" : "切换到深色主题"} title={theme === "dark" ? "浅色主题" : "深色主题"}><ThemeIcon /></button>
          <a className="icon-button" href="https://github.com/LBStruggleee/DataQuery-Copilot" target="_blank" rel="noreferrer" aria-label="打开 GitHub 仓库" title="打开 GitHub 仓库"><GithubIcon /></a>
          <div className="avatar" aria-label="用户 LB">LB</div>
        </div>
      </header>

      <div className="workspace">
        <Sidebar api={api} history={history} onHistorySelect={(item) => void submitQuery(item.question)} onRefresh={() => void refreshOverview()} />
        <main className="main-stage">
          <QueryComposer question={question} status={queryStatus} phase={phase} live={live} onQuestionChange={setQuestion} onSubmit={() => void submitQuery()} examples={contract === "v1" ? V1_EXAMPLE_QUESTIONS : undefined} />
          <ResultsPanel result={result} status={queryStatus} phase={phase} error={queryError} demo={isDemo} paging={contract === "v1" ? paging : null} onPageChange={contract === "v1" ? (page) => void submitQuery(question, page) : undefined} errorCode={contract === "v1" ? errorCode : null} />
        </main>
        <Inspector api={api} result={result} status={queryStatus} phase={phase} error={queryError} />
      </div>
    </div>
  );
}
