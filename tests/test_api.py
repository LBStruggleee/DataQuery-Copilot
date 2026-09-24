"""FastAPI bridge tests that never call the real LLM service."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import create_app, get_query_service
import api.services as services_module
from api.services import DataQueryService


class FakeQueryService:
    def health(self):
        return {
            "status": "ok",
            "database_ready": True,
            "llm_configured": True,
        }

    def schema(self):
        return {
            "table_name": "orders",
            "columns": [
                {"name": "category", "type": "TEXT"},
                {"name": "total_sales", "type": "REAL"},
            ],
        }

    def quality(self):
        return {
            "table_name": "orders",
            "total_rows": 10,
            "total_columns": 2,
            "missing_values": {"total_sales": 1},
            "duplicates": 0,
            "column_types": {"category": "str", "total_sales": "float64"},
        }

    def query(self, question, clean_result, max_retries):
        return {
            "question": question,
            "sql": "SELECT category, SUM(amount) AS total_sales FROM orders GROUP BY category",
            "columns": ["category", "total_sales"],
            "rows": [{"category": "电子产品", "total_sales": 5498.0}],
            "row_count": 1,
            "chart_hint": "bar",
            "execution_time": 0.012,
            "valid": True,
            "retries": 0,
            "from_cache": False,
            "error": None,
        }


@pytest.fixture
def client(tmp_path, monkeypatch):
    from api.auth import create_key

    db = str(tmp_path / "t.db")
    monkeypatch.setenv("DB_PATH", db)
    key = create_key(db, "pytest")
    app = create_app()
    app.dependency_overrides[get_query_service] = FakeQueryService
    with TestClient(app, headers={"X-API-Key": key}) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database_ready": True,
        "llm_configured": True,
    }


def test_schema(client):
    response = client.get("/api/schema")
    assert response.status_code == 200
    assert response.json()["columns"][0] == {"name": "category", "type": "TEXT"}


def test_quality(client):
    response = client.get("/api/quality")
    assert response.status_code == 200
    assert response.json()["missing_values"] == {"total_sales": 1}


def test_query(client):
    response = client.post(
        "/api/query",
        json={"question": "  各品类的销售总额  ", "max_retries": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["question"] == "各品类的销售总额"
    assert body["chart_hint"] == "bar"
    assert body["rows"][0]["total_sales"] == 5498.0


@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},
        {"question": "a"},
        {"question": "有效问题", "max_retries": 4},
    ],
)
def test_query_validates_request(client, payload):
    response = client.post("/api/query", json=payload)
    assert response.status_code == 422


def test_schema_maps_missing_table_to_404(tmp_path, monkeypatch):
    from api.auth import create_key

    class MissingTableService(FakeQueryService):
        def schema(self):
            raise ValueError("数据表不存在: orders")

    db = str(tmp_path / "t.db")
    monkeypatch.setenv("DB_PATH", db)
    key = create_key(db, "pytest")
    app = create_app()
    app.dependency_overrides[get_query_service] = MissingTableService
    with TestClient(app, headers={"X-API-Key": key}) as test_client:
        response = test_client.get("/api/schema")

    assert response.status_code == 404
    assert response.json()["detail"] == "数据表不存在: orders"


def test_records_are_json_safe():
    df = pd.DataFrame(
        {
            "created_at": [datetime(2026, 7, 20, 10, 30)],
            "amount": [np.float64(12.5)],
            "optional": [np.nan],
        }
    )

    records = DataQueryService._records(df)

    assert records == [
        {
            "created_at": "2026-07-20T10:30:00",
            "amount": 12.5,
            "optional": None,
        }
    ]


def test_service_query_adapts_engine_result(monkeypatch, tmp_path):
    class FakeEngine:
        def __init__(self, **kwargs):
            assert kwargs["table_name"] == "orders"
            assert kwargs["enable_cache"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def ask(self, question, clean_result, max_retries):
            assert clean_result is True
            assert max_retries == 2
            return {
                "question": question,
                "sql": "SELECT category, SUM(amount) AS total FROM orders GROUP BY category",
                "data": pd.DataFrame({"category": ["电子产品"], "total": [5498.0]}),
                "row_count": 1,
                "execution_time": 0.01,
                "valid": True,
                "error": None,
                "retries": 0,
                "from_cache": False,
            }

    monkeypatch.setattr(services_module, "QueryEngine", FakeEngine)
    service = DataQueryService(str(tmp_path / "query.db"))

    result = service.query("各品类销售额", clean_result=True, max_retries=2)

    assert result["columns"] == ["category", "total"]
    assert result["rows"] == [{"category": "电子产品", "total": 5498.0}]
    assert result["chart_hint"] == "bar"


@pytest.mark.parametrize("table_name", ["orders; DROP TABLE orders", "order-items", ""])
def test_service_rejects_unsafe_table_names(table_name):
    with pytest.raises(ValueError, match="无效的数据表名"):
        DataQueryService("data/query.db", table_name)
