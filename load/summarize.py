"""soak 压测的纯统计函数（无 IO，可单元测试）。"""


def percentile(values, pct):
    """百分位（nearest-rank，values 非空）。"""
    import math

    ordered = sorted(values)
    rank = max(1, math.ceil((pct / 100) * len(ordered)))
    return float(ordered[rank - 1])


def summarize(samples, budget_ms):
    """汇总：总数/失败数/p50/p95/max/是否在预算内（含分路径明细）。"""
    latencies = [s["latency"] for s in samples]
    failures = sum(1 for s in samples if not s["ok"])
    p95 = percentile(latencies, 95) if latencies else 0.0
    by_path = {}
    paths = sorted({s.get("path", "?") for s in samples})
    for path in paths:
        pls = [s["latency"] for s in samples if s.get("path", "?") == path]
        by_path[path] = {
            "count": len(pls),
            "p95_ms": round(percentile(pls, 95), 1),
            "max_ms": round(max(pls), 1),
            "failures": sum(1 for s in samples if s.get("path", "?") == path and not s["ok"]),
        }
    return {
        "total": len(samples),
        "failures": failures,
        "p50_ms": round(percentile(latencies, 50), 1) if latencies else 0.0,
        "p95_ms": round(p95, 1),
        "max_ms": round(max(latencies), 1) if latencies else 0.0,
        "within_budget": failures == 0 and p95 <= budget_ms,
        "by_path": by_path,
    }
