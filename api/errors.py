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


class APIError(Exception):
    """服务层抛出的领域异常，由路由层统一映射为信封响应。"""

    def __init__(self, code: ErrorCode, status: int, message: str):
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message
