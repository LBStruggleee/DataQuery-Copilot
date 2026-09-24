"""Pydantic models exposed by the HTTP API."""

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database_ready: bool
    llm_configured: bool


class ColumnInfo(BaseModel):
    name: str
    type: str


class SchemaResponse(BaseModel):
    table_name: str
    columns: list[ColumnInfo]


class QualityResponse(BaseModel):
    table_name: str
    total_rows: int
    total_columns: int
    missing_values: dict[str, int]
    duplicates: int
    column_types: dict[str, str]


DataT = TypeVar("DataT")


class ApiEnvelope(BaseModel, Generic[DataT]):
    """统一响应信封：所有 /api/v1/* 接口的唯一外层。"""

    version: Literal["v1"] = "v1"
    code: str
    message: str = "ok"
    data: DataT | None = None
    request_id: str


class QueryRequestV1(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    clean_result: bool = True
    max_retries: int = Field(default=2, ge=0, le=3)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=50)
    dataset: str | None = Field(default=None, description="数据集 id，缺省为默认 orders 表")


class DatasetInfo(BaseModel):
    id: str
    name: str
    table_name: str
    rows: int
    created_at: str


class MetricsData(BaseModel):
    requests_total: int
    errors_total: int
    query_requests: int
    uptime_seconds: float


class QueryDataV1(BaseModel):
    question: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    page: int
    page_size: int
    total_pages: int
    truncated: bool
    chart_hint: Literal["bar", "line", "pie", "scatter", "table"]
    execution_time: float
    valid: bool
    retries: int
    from_cache: bool
