"""Phase 5: 运行指标（无新依赖，Starlette 中间件 + 内存计数）。

query_requests 按调用次数计（尝试即计数，与配额口径一致）；
真正的 LLM HTTP 调用次数约为 query_requests × (1 + retries)，不做精确插桩。
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware

_started_at = time.monotonic()
_counters = {"requests_total": 0, "errors_total": 0, "query_requests": 0}


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        _counters["requests_total"] += 1
        response = await call_next(request)
        if response.status_code >= 400:
            _counters["errors_total"] += 1
        return response


def record_query() -> None:
    _counters["query_requests"] += 1


def snapshot() -> dict:
    return {
        "requests_total": _counters["requests_total"],
        "errors_total": _counters["errors_total"],
        "query_requests": _counters["query_requests"],
        "uptime_seconds": round(time.monotonic() - _started_at, 1),
    }
