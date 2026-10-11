/** P2-50/P2-51：历史与主题持久化的形状校验、失败条目 null 指标、存储被禁容错。 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { buildHistoryItem, isQueryHistoryItem, readHistory, readTheme, saveHistory, saveTheme } from "./history";
import type { QueryHistoryItem } from "./types";

function memoryStorage(options: { initial?: Record<string, string>; failSet?: boolean } = {}): Storage {
  const map = new Map(Object.entries(options.initial ?? {}));
  return {
    get length() { return map.size; },
    clear: () => map.clear(),
    getItem: (key: string) => (map.has(key) ? (map.get(key) as string) : null),
    key: (index: number) => [...map.keys()][index] ?? null,
    removeItem: (key: string) => { map.delete(key); },
    setItem: (key: string, value: string) => {
      if (options.failSet) throw new DOMException("存储被禁", "SecurityError");
      map.set(key, value);
    },
  } as Storage;
}

const validItem: QueryHistoryItem = {
  id: "1-问题", question: "问题", timestamp: 1, status: "success", rowCount: 5, executionTime: 0.1,
};

afterEach(() => vi.unstubAllGlobals());

describe("readHistory（P2-50 形状校验）", () => {
  it("存储为空时返回空数组", () => {
    vi.stubGlobal("localStorage", memoryStorage());
    expect(readHistory()).toEqual([]);
  });

  it("正常数组原样读出", () => {
    vi.stubGlobal("localStorage", memoryStorage({ initial: { "dataquery-copilot.query-history": JSON.stringify([validItem]) } }));
    expect(readHistory()).toEqual([validItem]);
  });

  it("localStorage 被写坏成非数组时返回空数组而非抛 TypeError", () => {
    vi.stubGlobal("localStorage", memoryStorage({ initial: { "dataquery-copilot.query-history": '{"a":1}' } }));
    expect(readHistory()).toEqual([]);
  });

  it("JSON 损坏时返回空数组", () => {
    vi.stubGlobal("localStorage", memoryStorage({ initial: { "dataquery-copilot.query-history": "{oops" } }));
    expect(readHistory()).toEqual([]);
  });

  it("形状非法的元素被过滤，合法元素保留", () => {
    const broken = [
      validItem,
      { id: 1, question: "问题", timestamp: 1, status: "success", rowCount: 1, executionTime: 1 }, // id 非字符串
      { id: "2", question: "问题", timestamp: "1", status: "success", rowCount: 1, executionTime: 1 }, // timestamp 非数字
      { id: "3", question: "问题", timestamp: 1, status: "pending", rowCount: 1, executionTime: 1 }, // status 非法
      { id: "4", question: "问题", timestamp: 1, status: "success" }, // 缺 rowCount/executionTime
      "junk", // 非对象
    ];
    vi.stubGlobal("localStorage", memoryStorage({ initial: { "dataquery-copilot.query-history": JSON.stringify(broken) } }));
    expect(readHistory()).toEqual([validItem]);
  });
});

describe("saveHistory / saveTheme（P2-50 存储被禁容错）", () => {
  it("setItem 抛异常时不向外传播", () => {
    vi.stubGlobal("localStorage", memoryStorage({ failSet: true }));
    expect(() => saveHistory([validItem])).not.toThrow();
    expect(() => saveTheme("light")).not.toThrow();
  });

  it("正常时写入 localStorage", () => {
    const storage = memoryStorage();
    vi.stubGlobal("localStorage", storage);
    saveHistory([validItem]);
    saveTheme("light");
    expect(readHistory()).toEqual([validItem]);
    expect(readTheme()).toBe("light");
  });
});

describe("readTheme", () => {
  it("非 light 值与存储被禁均回退 dark", () => {
    vi.stubGlobal("localStorage", memoryStorage({ initial: { "dataquery-copilot.theme": "neon" } }));
    expect(readTheme()).toBe("dark");
    vi.stubGlobal("localStorage", { getItem: () => { throw new DOMException("denied", "SecurityError"); } });
    expect(readTheme()).toBe("dark");
  });
});

describe("buildHistoryItem（P2-51）", () => {
  it("成功条目记录真实行数与耗时", () => {
    const item = buildHistoryItem("各品类销售", "success", { rowCount: 25, executionTime: 1.23 });
    expect(item.status).toBe("success");
    expect(item.rowCount).toBe(25);
    expect(item.executionTime).toBe(1.23);
  });

  it("失败条目记 null，不再沿用上一次成功结果", () => {
    const item = buildHistoryItem("坏问题", "error", { rowCount: 25, executionTime: 1.23 });
    expect(item.status).toBe("error");
    expect(item.rowCount).toBeNull();
    expect(item.executionTime).toBeNull();
  });
});

describe("isQueryHistoryItem", () => {
  it("接受 null 指标（失败条目）", () => {
    expect(isQueryHistoryItem({ id: "1", question: "q", timestamp: 1, status: "error", rowCount: null, executionTime: null })).toBe(true);
  });

  it("拒绝 NaN/Infinity 等非有限数字", () => {
    expect(isQueryHistoryItem({ id: "1", question: "q", timestamp: 1, status: "success", rowCount: Number.NaN, executionTime: 1 })).toBe(false);
  });
});
