"""
pytest 配置 — 共享 fixtures：数据库、数据、mock
"""
import sys
import os
import sqlite3

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DEEPSEEK_API_KEY", "test_key_for_unit_test")

from src.data_loader import DataLoader
from src.data_cleaner import DataCleaner
from src.query_engine import QueryEngine


# ── 共享 fixtures ──────────────────────────────────────

@pytest.fixture
def sample_df():
    """标准电商订单 DataFrame（含缺失值和异常值）"""
    return pd.DataFrame({
        "order_id":    [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010],
        "order_date":  pd.to_datetime([
            "2026-06-01", "2026-06-03", "2026-06-05", "2026-06-07", "2026-06-09",
            "2026-06-11", "2026-06-13", "2026-06-15", "2026-06-17", "2026-06-19",
        ]),
        "category":    ["电子产品", "食品饮料", "电子产品", "图书文具", "食品饮料",
                        "食品饮料", "图书文具", "电子产品", None, "食品饮料"],
        "amount":      [2999.0, 15.5, 199.0, 9.9, 25.0,
                        8.0, 3.0, 2499.0, 39.0, 99999.0],
        "quantity":    [1, 2, 1, 3, 2, 4, 5, 1, 1, 1],
        "region":      ["华东", "华北", "华南", "西南", "华东",
                        "华北", "华南", "西南", "华东", "华北"],
    })


@pytest.fixture
def temp_db_path(tmp_path):
    """临时数据库路径（P2-39：pytest tmp_path 进程内唯一，不再依赖共享临时目录）"""
    return str(tmp_path / "test.db")


@pytest.fixture
def loader(temp_db_path, sample_df):
    """已加载数据的 DataLoader"""
    dl = DataLoader(db_path=temp_db_path)
    sample_df.to_sql("orders", dl.conn, if_exists="replace", index=False)
    yield dl
    dl.close()


@pytest.fixture
def engine(temp_db_path, sample_df):
    """已加载数据、关闭日志和缓存的 QueryEngine"""
    conn = sqlite3.connect(temp_db_path)
    try:
        sample_df.to_sql("orders", conn, if_exists="replace", index=False)
    finally:
        conn.close()
    eng = QueryEngine(db_path=temp_db_path, enable_cache=False, enable_log=False)
    yield eng
    eng.close()


@pytest.fixture
def cleaner():
    return DataCleaner()


@pytest.fixture(autouse=True)
def _isolated_api_memory_state():
    """API 层进程内存态（Key 限流桶 / 鉴权失败桶）逐用例清空，避免用例顺序耦合。"""
    import api.auth as auth_module

    auth_module._hits.clear()
    auth_module._auth_failures.clear()
    yield
    auth_module._hits.clear()
    auth_module._auth_failures.clear()


# ── P2-40：TestClient + create_key + FakeService 样板收敛 ───────────

class FakeQueryService:
    """DataQueryService 替身：默认各方法返回固定数据，测试按需子类化覆写。

    db_path 由 api_test_client 工厂注入（挂 _db_path 类属性），保证指向
    每个用例独立的临时库。
    """

    _db_path = "data/query.db"

    @property
    def db_path(self):
        return self._db_path

    def health(self):
        return {"status": "ok", "database_ready": True, "llm_configured": False}

    def schema(self):
        return {"table_name": "orders", "columns": [{"name": "category", "type": "TEXT"}]}

    def quality(self, table_name=None):
        return {"table_name": "orders", "sampled_rows": 10, "total_rows": 10, "total_columns": 1,
                "missing_values": {}, "duplicates": 0, "column_types": {"category": "str"}}

    def query_page(self, question, clean_result, max_retries, page, page_size, table_name=None):
        from api.errors import APIError, ErrorCode

        if question == "触发拒绝":
            raise APIError(ErrorCode.SQL_REJECTED, 422, "SQL 安全校验未通过")
        return {"question": question, "sql": "SELECT 1", "columns": ["a"], "rows": [{"a": 1}],
                "row_count": 1, "page": page, "page_size": page_size, "total_pages": 1,
                "truncated": False, "chart_hint": "table", "execution_time": 0.01,
                "valid": True, "retries": 0, "from_cache": False}


@pytest.fixture
def api_test_client(tmp_path, monkeypatch):
    """P2-40：TestClient + create_key + FakeService 样板收敛到 conftest。

    返回工厂 make(...)，生成**未进入** with 的 TestClient（lifespan 由调用方
    with 触发），client.key / client.db 分别挂明文 Key 与临时库路径：

        client = api_test_client()                        # 默认 FakeQueryService + 预置 X-API-Key
        client = api_test_client(with_header=False)       # 不预置请求头（测试 401）
        client = api_test_client(key_kwargs={"daily_quota": 1})
        client = api_test_client(service_cls=MyService)   # 子类覆写 FakeQueryService
    """
    from fastapi.testclient import TestClient

    from api.auth import create_key
    from api.main import create_app, get_query_service

    db = str(tmp_path / "api.db")
    monkeypatch.setenv("DB_PATH", db)

    def make(service_cls=None, key_kwargs=None, with_header=True, **client_kwargs):
        key = create_key(db, "pytest", **(key_kwargs or {}))
        service = (service_cls or FakeQueryService)()
        service._db_path = db
        app = create_app()
        app.dependency_overrides[get_query_service] = lambda: service
        headers = {"X-API-Key": key} if with_header else None
        client = TestClient(app, headers=headers, **client_kwargs)
        client.key = key
        client.db = db
        return client

    return make
