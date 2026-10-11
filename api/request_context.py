"""P2-18：请求级 request_id——入口中间件生成，服务端日志与响应信封共用。

放在独立模块避免 main ↔ auth 循环导入：鉴权审计日志也需要读 request_id。
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:12]}"


def get_request_id(request) -> str:
    """优先取中间件写入的 request_id；中间件未覆盖的边缘路径兜底新生成。"""
    state = getattr(request, "state", None)
    return getattr(state, "request_id", None) or new_request_id()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """每个请求入口生成 request_id 存入 request.state（P2-18 全链路透传的起点）。"""

    async def dispatch(self, request, call_next):
        request.state.request_id = new_request_id()
        return await call_next(request)
