/**
 * P2-50/P2-51：查询历史的持久化读写。
 * 独立成模块以便单测覆盖（localStorage 形状校验、失败条目记 null）。
 */
import type { QueryHistoryItem } from "./types";

export const HISTORY_KEY = "dataquery-copilot.query-history";
export const THEME_KEY = "dataquery-copilot.theme";
export const HISTORY_LIMIT = 8;

/** 逐项校验 localStorage 中的历史条目形状，坏数据直接过滤（防止渲染期 TypeError 白屏）。 */
export function isQueryHistoryItem(value: unknown): value is QueryHistoryItem {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  return typeof item.id === "string"
    && typeof item.question === "string"
    && typeof item.timestamp === "number"
    && (item.status === "success" || item.status === "error")
    && (item.rowCount === null || (typeof item.rowCount === "number" && Number.isFinite(item.rowCount)))
    && (item.executionTime === null || (typeof item.executionTime === "number" && Number.isFinite(item.executionTime)));
}

/** 读取历史：非数组、JSON 损坏、存储被禁一律返回空数组。 */
export function readHistory(): QueryHistoryItem[] {
  try {
    const stored = localStorage.getItem(HISTORY_KEY);
    if (!stored) return [];
    const parsed: unknown = JSON.parse(stored);
    return Array.isArray(parsed) ? parsed.filter(isQueryHistoryItem).slice(0, HISTORY_LIMIT) : [];
  } catch {
    return [];
  }
}

/** 写入历史：存储被禁（隐私模式）时静默降级为仅内存。 */
export function saveHistory(items: QueryHistoryItem[]): void {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items));
  } catch { /* 隐私模式下仅内存生效 */ }
}

export type HistoryMetrics = { rowCount: number; executionTime: number };

/** 构造历史条目：成功记录真实行数/耗时；失败（P2-51）记 null，不再沿用上一次成功结果。 */
export function buildHistoryItem(
  question: string, status: "success" | "error", metrics?: HistoryMetrics,
): QueryHistoryItem {
  const success = status === "success";
  return {
    id: `${Date.now()}-${question}`,
    question,
    timestamp: Date.now(),
    status,
    rowCount: success ? metrics?.rowCount ?? 0 : null,
    executionTime: success ? metrics?.executionTime ?? 0 : null,
  };
}

/** 读取主题偏好：存储被禁或值非法时回退深色。 */
export function readTheme(): "dark" | "light" {
  try {
    return localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

/** 写入主题偏好：存储被禁时静默跳过（P2-50：不抛未捕获异常）。 */
export function saveTheme(theme: "dark" | "light"): void {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch { /* 隐私模式下仅内存生效 */ }
}
