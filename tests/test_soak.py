"""Phase 4: soak 压测的统计函数。"""


def test_summarize_latencies():
    from load.summarize import percentile, summarize

    samples = [{"ok": True, "status": 200, "latency": float(i)} for i in range(1, 101)]
    assert percentile([r["latency"] for r in samples], 50) == 50.0
    assert percentile([r["latency"] for r in samples], 95) == 95.0

    report = summarize(samples, budget_ms=100000.0)
    assert report["total"] == 100
    assert report["failures"] == 0
    assert report["within_budget"] is True

    bad = [{"ok": False, "status": 500, "latency": 1.0}]
    report = summarize(bad, budget_ms=100000.0)
    assert report["failures"] == 1
    assert report["within_budget"] is False
