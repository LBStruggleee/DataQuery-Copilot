"""无 LLM 成本的并发压测（httpx + 线程池）。

只打不调 LLM 的端点：health / schema / quality / datasets / 空白问题 422 / 未知数据集 404。
Key 在本机直接签发（--keys 个，轮询使用，模拟多用户并避开单 Key 限流）。

用法:
    python load/soak.py --base http://127.0.0.1:8002 --db .soak/query.db [--keys 10] [--total 200] [--workers 20]

全量 LLM 压测烧配额，不自动化，手动步骤见 load/README.md。
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.auth import create_key
from load.summarize import summarize


def build_targets():
    return [
        ("GET", "/api/v1/health", None),
        ("GET", "/api/v1/schema", None),
        ("GET", "/api/v1/quality", None),
        ("GET", "/api/v1/datasets", None),
        ("POST", "/api/v1/query", {"question": "   "}),
        ("POST", "/api/v1/query", {"question": "有效问题", "dataset": "nope"}),
        ("GET", "/api/v1/schema?dataset=nope", None),
    ]


def fire(client, base, key, target):
    method, path, body = target
    headers = {"X-API-Key": key}
    start = time.perf_counter()
    try:
        if method == "GET":
            r = client.get(base + path, headers=headers, timeout=30)
        else:
            r = client.post(base + path, headers=headers, json=body, timeout=30)
        latency = (time.perf_counter() - start) * 1000
        ok = r.status_code < 500
        envelope = r.json()
        ok = ok and envelope.get("version") == "v1" and "request_id" in envelope
        return {"ok": ok, "status": r.status_code, "latency": latency, "path": path}
    except Exception as error:
        return {"ok": False, "status": -1, "latency": (time.perf_counter() - start) * 1000,
                "path": path, "error": str(error)}


def main() -> int:
    parser = argparse.ArgumentParser(description="无 LLM 成本并发压测")
    parser.add_argument("--base", default="http://127.0.0.1:8002")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/query.db"))
    parser.add_argument("--keys", type=int, default=10)
    parser.add_argument("--total", type=int, default=140)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--budget-ms", type=float, default=3000.0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    keys = [create_key(args.db, f"soak-{i}") for i in range(args.keys)]
    targets = build_targets()
    jobs = [(keys[i % len(keys)], targets[i % len(targets)]) for i in range(args.total)]

    results = []
    with httpx.Client() as client:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(fire, client, args.base, key, target) for key, target in jobs]
            for future in futures:
                results.append(future.result())

    report = summarize(results, args.budget_ms)
    report["budget_ms"] = args.budget_ms
    by_status: dict = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    report["by_status"] = by_status
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    return 0 if report["within_budget"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
