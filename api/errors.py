"""v1 统一错误码与领域异常（契约源：docs/v1_contract_proposal.md §4.2）。"""

from enum import Enum


class ErrorCode(str, Enum):
    INVALID_QUESTION = "INVALID_QUESTION"
    SQL_REJECTED = "SQL_REJECTED"
    TABLE_NOT_FOUND = "TABLE_NOT_FOUND"
    QUERY_TIMEOUT = "QUERY_TIMEOUT"
    RESULT_TRUNCATED = "RESULT_TRUNCATED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    # proposal 表外补充：查询路径执行失败与未知异常的 500 兜底
    QUERY_FAILED = "QUERY_FAILED"
    # 成品化阶段一：鉴权与限流
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    # P2-19：上传校验失败专用码（原先复用 INVALID_QUESTION，超出其「问题为空/超长/非法」的契约语义）
    UPLOAD_REJECTED = "UPLOAD_REJECTED"


class APIError(Exception):
    """服务层抛出的领域异常，由路由层统一映射为信封响应。"""

    def __init__(self, code: ErrorCode, status: int, message: str):
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message
