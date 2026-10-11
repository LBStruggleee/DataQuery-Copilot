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


def _patch_engine(monkeypatch, frame=None, error=None, error_code=None):
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
                        "error_code": error_code,
                        "retries": max_retries, "from_cache": False}
            return {"question": question, "sql": "SELECT * FROM orders", "data": frame,
                    "row_count": len(frame), "execution_time": 0.01, "valid": True,
                    "error": None, "error_code": None, "retries": 0, "from_cache": False}

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
        ("SQL 执行失败（已重试 2 次）: no such table: archive", "TABLE_NOT_FOUND"),
    ],
)
def test_query_page_maps_engine_errors(monkeypatch, tmp_path, engine_error, code):
    """回退路径：engine result 未携带 error_code 时按历史字符串匹配。"""
    from api.errors import APIError
    from api.services import DataQueryService

    _patch_engine(monkeypatch, error=engine_error)
    service = DataQueryService(str(tmp_path / "query.db"))

    with pytest.raises(APIError) as exc_info:
        service.query_page("q", True, 2, 1, 10)
    assert exc_info.value.code.value == code


@pytest.mark.parametrize(
    "error_code, error, code",
    [
        ("SQL_REJECTED", "措辞已改，不含「安全校验」", "SQL_REJECTED"),
        ("SQL_GENERATION_FAILED", "上游 401", "SERVICE_UNAVAILABLE"),
        ("EXECUTION_FAILED", "no such table: archive", "TABLE_NOT_FOUND"),
        ("EXECUTION_FAILED", "no such column: x", "QUERY_FAILED"),
        ("UNKNOWN_FUTURE_CODE", "whatever", "QUERY_FAILED"),
    ],
)
def test_map_engine_error_prefers_error_code(monkeypatch, tmp_path, error_code, error, code):
    """P2-26：结构化 error_code 优先——src 层措辞变化不再引发静默 500 漂移。"""
    from api.errors import APIError
    from api.services import DataQueryService

    _patch_engine(monkeypatch, error=error, error_code=error_code)
    service = DataQueryService(str(tmp_path / "query.db"))

    with pytest.raises(APIError) as exc_info:
        service.query_page("q", True, 2, 1, 10)
    assert exc_info.value.code.value == code


def test_engine_error_codes_are_wired_from_src():
    """P2-26：映射表覆盖 src/query_engine 当前产出的全部 error_code。"""
    from api.services import DataQueryService

    assert set(DataQueryService._ENGINE_ERROR_CODES) == {
        "SQL_REJECTED", "SQL_GENERATION_FAILED", "EXECUTION_FAILED",
    }


def test_query_page_truncates_before_convert(monkeypatch, tmp_path):
    """终审 C1：截断必须发生在 to_dict 之前，_records 只应看到 ≤100 行。"""
    import api.services as services_module
    from api.services import DataQueryService

    seen = []
    orig_records = DataQueryService._records

    def spy(df):
        seen.append(len(df))
        return orig_records(df)

    monkeypatch.setattr(DataQueryService, "_records", staticmethod(spy))
    _patch_engine(monkeypatch, frame=_big_frame(10000))
    service = DataQueryService(str(tmp_path / "query.db"))

    result = service.query_page("q", True, 2, 1, 10)

    assert result["truncated"] is True
    assert result["row_count"] == 100
    assert seen == [100]


def test_v1_validation_errors_use_envelope(api_test_client):
    """终审 I1：Pydantic 校验失败也必须包信封。"""
    with api_test_client() as client:
        empty = client.post("/api/v1/query", json={"question": ""})
        bad_page = client.post("/api/v1/query", json={"question": "有效问题", "page": 0})

    assert empty.status_code == 422
    assert empty.json()["code"] == "INVALID_QUESTION"
    assert bad_page.status_code == 422
    assert bad_page.json()["version"] == "v1"


def test_v1_health_wraps_unexpected_errors(api_test_client):
    """终审 I2：health_v1 异常也必须包信封。"""
    from tests.conftest import FakeQueryService

    class ExplodingHealthService(FakeQueryService):
        def health(self):
            raise RuntimeError("boom")

    client = api_test_client(service_cls=ExplodingHealthService, raise_server_exceptions=False)
    with client:
        response = client.get("/api/v1/health")

    assert response.status_code == 500
    assert response.json()["code"] == "QUERY_FAILED"


def test_v0_routes_removed():
    from fastapi.testclient import TestClient

    from api.main import create_app

    with TestClient(create_app()) as client:
        # /api/health 自 P0-01 起为免鉴权存活探针（见 test_ops_health.py），不再属于已移除的 v0 路由
        assert client.get("/api/schema").status_code == 404
        assert client.get("/api/quality").status_code == 404
        assert client.post("/api/query", json={"question": "有效问题"}).status_code == 404


def test_v1_metrics_counts_requests_and_errors(api_test_client):
    client = api_test_client(with_header=False)
    headers = {"X-API-Key": client.key}
    with client:
        assert client.get("/api/v1/metrics").status_code == 401
        assert client.get("/api/v1/health", headers=headers).status_code == 200
        assert client.post("/api/v1/query", headers=headers, json={"question": "   "}).status_code == 422
        body = client.get("/api/v1/metrics", headers=headers).json()

    assert body["code"] == "OK"
    data = body["data"]
    assert data["requests_total"] >= 3
    assert data["errors_total"] >= 1
    assert data["uptime_seconds"] >= 0
    assert set(["requests_total", "errors_total", "query_requests", "uptime_seconds"]) <= set(data)


def test_v1_query_sanitizes_engine_errors(api_test_client, caplog):
    import logging

    from api.errors import APIError, ErrorCode
    from tests.conftest import FakeQueryService

    class LeakyService(FakeQueryService):
        def query_page(self, *args, **kwargs):
            raise APIError(ErrorCode.SQL_REJECTED, 422, "SQL 安全校验未通过：DROP TABLE secret_schema")

    client = api_test_client(service_cls=LeakyService)
    with caplog.at_level(logging.WARNING, logger="api.main"):
        with client:
            response = client.post("/api/v1/query", json={"question": "删库"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "SQL_REJECTED"
    assert "secret_schema" not in body["message"]
    assert body["request_id"].startswith("req_")
    logged = [r for r in caplog.records if getattr(r, "request_id", None) == body["request_id"]]
    assert logged and "secret_schema" in logged[0].detail


@pytest.fixture
def v1_client(api_test_client):
    """P2-40：样板收敛到 conftest，默认预置 X-API-Key 请求头。"""
    client = api_test_client()
    with client:
        yield client


def test_v1_query_envelope(v1_client):
    response = v1_client.post("/api/v1/query", json={"question": "有效问题", "page": 1, "page_size": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "v1" and body["code"] == "OK"
    assert body["data"]["rows"] == [{"a": 1}]
    assert body["request_id"].startswith("req_")


def test_v1_query_rejects_blank_question(v1_client):
    response = v1_client.post("/api/v1/query", json={"question": "   "})
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_QUESTION"


def test_v1_query_maps_service_error(v1_client):
    response = v1_client.post("/api/v1/query", json={"question": "触发拒绝"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "SQL_REJECTED"
    assert body["data"] is None
    assert body["request_id"].startswith("req_")


def test_v1_health_envelope(v1_client):
    body = v1_client.get("/api/v1/health").json()
    assert (body["version"], body["code"]) == ("v1", "OK")
    assert body["data"]["status"] == "ok"


def test_v1_query_wraps_unexpected_errors_in_envelope(api_test_client):
    from tests.conftest import FakeQueryService

    class ExplodingService(FakeQueryService):
        def query_page(self, *args, **kwargs):
            raise RuntimeError("boom")

    client = api_test_client(service_cls=ExplodingService, raise_server_exceptions=False)
    with client:
        response = client.post("/api/v1/query", json={"question": "有效问题"})

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "QUERY_FAILED"
    assert body["data"] is None
    assert body["request_id"].startswith("req_")


def test_openapi_contract():
    from fastapi.testclient import TestClient

    from api.main import create_app

    with TestClient(create_app()) as client:
        spec = client.get("/openapi.json").json()

    for path in ["/api/v1/health", "/api/v1/schema", "/api/v1/quality", "/api/v1/query"]:
        assert path in spec["paths"], f"missing {path}"

    envelope = spec["components"]["schemas"]["ApiEnvelope_QueryDataV1_"]
    assert set(["request_id"]) <= set(envelope["required"])
    assert set(["version", "code", "message", "data", "request_id"]) <= set(envelope["properties"])

    query_props = spec["components"]["schemas"]["QueryRequestV1"]["properties"]
    assert set(["question", "page", "page_size"]) <= set(query_props)


# ── P2-17：未处理异常兜底包信封 ─────────────────────────────────────

def test_unhandled_dependency_error_returns_envelope(tmp_path, monkeypatch):
    """P2-17：依赖内异常（如 TABLE_NAME 非法）也必须包信封，而非 Starlette 裸 500 detail。"""
    from fastapi.testclient import TestClient

    from api.auth import create_key
    from api.main import create_app

    db = str(tmp_path / "t.db")
    monkeypatch.setenv("DB_PATH", db)
    monkeypatch.setenv("TABLE_NAME", "bad;drop")  # DataQueryService 构造即抛 ValueError
    key = create_key(db, "ci")

    app = create_app()  # 不覆盖 get_query_service，走真实依赖
    with TestClient(app, raise_server_exceptions=False, headers={"X-API-Key": key}) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 500
    body = response.json()
    assert body["version"] == "v1"
    assert body["code"] == "QUERY_FAILED"
    assert body["data"] is None
    assert body["request_id"].startswith("req_")
    # 不再是 Starlette 默认的非信封响应
    assert "detail" not in body


# ── P1-08 + P2-23：意外异常必留日志（含 request_id），且响应消息净化 ──

def test_unexpected_route_error_logged_and_sanitized(v1_client, caplog):
    import logging

    from api.main import get_query_service
    from tests.conftest import FakeQueryService

    class ExplodingSchema(FakeQueryService):
        def schema(self, table_name=None):
            raise RuntimeError("secret-boom: raw pandas/字段原文")

    v1_client.app.dependency_overrides[get_query_service] = lambda: ExplodingSchema()
    with caplog.at_level(logging.ERROR, logger="api.main"):
        response = v1_client.get("/api/v1/schema")

    body = response.json()
    assert response.status_code == 500
    assert body["code"] == "QUERY_FAILED"
    assert "secret-boom" not in body["message"]  # P2-23：净化后统一文案

    logged = [r for r in caplog.records if getattr(r, "request_id", None) == body["request_id"]]
    assert logged and logged[0].levelno == logging.ERROR
    assert logged[0].exc_info  # P1-08：服务端日志带完整堆栈


# ── P2-25：质量报告标注采样行数 ─────────────────────────────────────

def test_quality_response_marks_sampled_rows(v1_client):
    response = v1_client.get("/api/v1/quality")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sampled_rows"] == 10
    assert data["total_rows"] == 10


def test_service_quality_reports_sampled_rows(tmp_path):
    import sqlite3

    from api.services import DataQueryService

    db = str(tmp_path / "t.db")
    conn = sqlite3.connect(db)
    try:
        conn.execute("CREATE TABLE orders (a INTEGER, b TEXT)")
        conn.executemany("INSERT INTO orders VALUES (?, ?)", [(i, f"r{i}") for i in range(3)])
        conn.commit()
    finally:
        conn.close()

    report = DataQueryService(db).quality()

    assert report["sampled_rows"] == 3
    assert report["total_rows"] == 3


# ── P1-07：上传流式限量 ─────────────────────────────────────────────

class _StubRequest:
    def __init__(self, headers):
        self.headers = headers


def test_content_length_preflight_rejects_early():
    from api.main import _content_length_exceeds

    assert _content_length_exceeds(_StubRequest({"content-length": "100"}), 50) is True
    assert _content_length_exceeds(_StubRequest({"content-length": "10"}), 50) is False
    assert _content_length_exceeds(_StubRequest({}), 50) is False  # 无头放行，交给分块计数
    assert _content_length_exceeds(_StubRequest({"content-length": "abc"}), 50) is False


def test_read_upload_bounded_stops_before_full_read():
    """超限立即拒绝：不必读完整个请求体（恶意超大上传不再先耗内存）。"""
    import asyncio

    import api.main as main_module
    from api.errors import APIError

    class FakeUpload:
        def __init__(self, chunk, total_chunks):
            self.chunk = chunk
            self.remaining = total_chunks
            self.reads = 0

        async def read(self, size=-1):
            if self.remaining <= 0:
                return b""
            self.remaining -= 1
            self.reads += 1
            return self.chunk

    async def consume():
        upload = FakeUpload(b"x" * 1024, 200)  # 200KB
        try:
            await main_module._read_upload_bounded(upload, 50 * 1024)  # 上限 50KB
        except APIError:
            return upload.reads
        return None

    reads = asyncio.run(consume())
    assert reads is not None
    assert reads < 200  # 远未读完即拒绝


def test_upload_rejects_oversize_before_register(api_test_client, monkeypatch):
    import api.main as main_module

    from api.datasets import list_datasets

    monkeypatch.setattr(main_module, "MAX_UPLOAD_BYTES", 10)
    with api_test_client() as client:
        response = client.post(
            "/api/v1/datasets",
            files={"file": ("a.csv", "a,b\n" + "1,2\n" * 20, "text/csv")},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "UPLOAD_REJECTED"
    assert list_datasets(client.db) == []


# ── P2-19 / P2-20 / P2-21 / P2-23：上传错误码、白名单、编码回退、净化 ─

def test_upload_bad_extension_uses_upload_rejected_code(api_test_client):
    """P2-19：上传校验失败不再复用 INVALID_QUESTION。"""
    with api_test_client() as client:
        response = client.post(
            "/api/v1/datasets",
            files={"file": ("evil.exe", b"MZ", "application/x-msdownload")},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "UPLOAD_REJECTED"


def test_upload_legacy_xls_rejected(api_test_client):
    """P2-20：.xls 不再放行——解析所需 xlrd 未声明，放行必然 422。"""
    with api_test_client() as client:
        response = client.post(
            "/api/v1/datasets",
            files={"file": ("old.xls", b"\xd0\xcf\x11\xe0", "application/vnd.ms-excel")},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "UPLOAD_REJECTED"


def test_upload_parse_failure_message_sanitized(api_test_client):
    """P2-23：解析失败细节（编码器/pandas 报错原文）不出服务端。"""
    garbage = bytes([0xFF, 0xFE, 0x41, 0x00, 0x42]) * 64  # utf-8-sig 与 gbk 均无法解码
    with api_test_client() as client:
        response = client.post(
            "/api/v1/datasets", files={"file": ("bad.csv", garbage, "text/csv")}
        )

    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "UPLOAD_REJECTED"
    assert "codec" not in body["message"]
    assert "can't decode" not in body["message"]
    assert body["message"] == "文件未通过上传校验，请检查格式与大小"


def test_upload_gbk_csv_accepted(api_test_client):
    """P2-21：GBK 编码 CSV（中文 Excel 导出常见）可以正常入库。"""
    gbk_csv = "类别,金额\n食品,12.5\n图书,9.9\n".encode("gbk")
    with api_test_client() as client:
        response = client.post(
            "/api/v1/datasets", files={"file": ("gbk导出.csv", gbk_csv, "text/csv")}
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["rows"] == 2
    assert data["table_name"].startswith("ds_")


# ── P2-18：request_id 全链路共用（入口中间件生成） ───────────────────

def test_error_envelope_request_id_comes_from_request_context(api_test_client, caplog):
    import logging

    from api.errors import APIError, ErrorCode
    from tests.conftest import FakeQueryService

    class LeakyService(FakeQueryService):
        def query_page(self, *args, **kwargs):
            raise APIError(ErrorCode.SQL_REJECTED, 422, "SQL 安全校验未通过")

    client = api_test_client(service_cls=LeakyService)
    with caplog.at_level(logging.WARNING, logger="api.main"):
        with client:
            response = client.post("/api/v1/query", json={"question": "q"})

    request_id = response.json()["request_id"]
    assert request_id.startswith("req_")
    # 路由日志与响应信封共用中间件生成的同一个 request_id
    logged = [r for r in caplog.records if getattr(r, "request_id", None) == request_id]
    assert logged
