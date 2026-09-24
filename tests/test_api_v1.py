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


def _big_frame(n):
    return pd.DataFrame({"category": [f"类{i % 8}" for i in range(n)], "total": [float(i) for i in range(n)]})


def _patch_engine(monkeypatch, frame=None, error=None):
    import api.services as services_module

    class FakeEngine:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def ask(self, question, clean_result, max_retries):
            if error is not None:
                return {"question": question, "sql": "", "data": None, "row_count": 0,
                        "execution_time": 0.0, "valid": False, "error": error,
                        "retries": max_retries, "from_cache": False}
            return {"question": question, "sql": "SELECT * FROM orders", "data": frame,
                    "row_count": len(frame), "execution_time": 0.01, "valid": True,
                    "error": None, "retries": 0, "from_cache": False}

    monkeypatch.setattr(services_module, "QueryEngine", FakeEngine)


def test_query_page_slices_and_clamps(monkeypatch, tmp_path):
    from api.services import DataQueryService

    _patch_engine(monkeypatch, frame=_big_frame(25))
    service = DataQueryService(str(tmp_path / "query.db"))

    page1 = service.query_page("q", True, 2, 1, 10)
    assert page1["page"] == 1 and page1["total_pages"] == 3 and page1["truncated"] is False
    assert [r["total"] for r in page1["rows"]] == [float(i) for i in range(10)]

    overflow = service.query_page("q", True, 2, 99, 10)
    assert overflow["page"] == 3
    assert [r["total"] for r in overflow["rows"]] == [float(i) for i in range(20, 25)]


def test_query_page_truncates_large_results(monkeypatch, tmp_path):
    from api.services import DataQueryService

    _patch_engine(monkeypatch, frame=_big_frame(10000))
    service = DataQueryService(str(tmp_path / "query.db"))

    result = service.query_page("q", True, 2, 1, 10)
    assert result["truncated"] is True
    assert result["row_count"] == 100
    assert result["total_pages"] == 10


@pytest.mark.parametrize(
    "engine_error, code",
    [
        ("SQL 安全校验未通过（仅允许 SELECT 语句）", "SQL_REJECTED"),
        ("SQL 生成失败: bad key", "SERVICE_UNAVAILABLE"),
        ("SQL 执行失败（已重试 2 次）: no such column", "QUERY_FAILED"),
    ],
)
def test_query_page_maps_engine_errors(monkeypatch, tmp_path, engine_error, code):
    from api.errors import APIError
    from api.services import DataQueryService

    _patch_engine(monkeypatch, error=engine_error)
    service = DataQueryService(str(tmp_path / "query.db"))

    with pytest.raises(APIError) as exc_info:
        service.query_page("q", True, 2, 1, 10)
    assert exc_info.value.code.value == code
