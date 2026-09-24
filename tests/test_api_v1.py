"""v1 契约测试：错误码、分页服务、v1 路由、OpenAPI 契约。"""

import pandas as pd
import pytest


def test_error_codes_are_stable():
    from api.errors import APIError, ErrorCode

    assert ErrorCode.SQL_REJECTED.value == "SQL_REJECTED"
    err = APIError(ErrorCode.TABLE_NOT_FOUND, 404, "数据表不存在: orders")
    assert err.code is ErrorCode.TABLE_NOT_FOUND
    assert err.status == 404
    assert err.message == "数据表不存在: orders"


def test_envelope_serializes():
    from api.models import ApiEnvelope, QueryDataV1

    data = QueryDataV1(
        question="q", sql="SELECT 1", columns=["a"], rows=[{"a": 1}],
        row_count=1, page=1, page_size=10, total_pages=1, truncated=False,
        chart_hint="table", execution_time=0.01, valid=True, retries=0, from_cache=False,
    )
    body = ApiEnvelope[QueryDataV1](code="OK", message="ok", data=data, request_id="req_abc").model_dump()
    assert body == {
        "version": "v1", "code": "OK", "message": "ok",
        "data": {**data.model_dump()}, "request_id": "req_abc",
    }
    assert body["data"]["rows"] == [{"a": 1}]


def test_query_request_v1_validates_paging():
    from pydantic import ValidationError
    from api.models import QueryRequestV1

    with pytest.raises(ValidationError):
        QueryRequestV1(question="有效问题", page=0)
    with pytest.raises(ValidationError):
        QueryRequestV1(question="有效问题", page_size=51)
    req = QueryRequestV1(question="有效问题")
    assert (req.page, req.page_size) == (1, 10)
