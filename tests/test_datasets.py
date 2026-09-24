"""Phase 2: 数据集注册表、上传入库、作用域查询、备份。"""

import io
import os

import pandas as pd
import pytest


def _csv_bytes(rows=5):
    df = pd.DataFrame({"category": [f"类{i}" for i in range(rows)], "amount": [float(i) for i in range(rows)]})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def test_register_upload_and_list(tmp_path):
    from api.datasets import list_datasets, register_upload

    db = str(tmp_path / "t.db")
    info = register_upload(db, "销售 数据.csv", _csv_bytes(7))
    assert info["rows"] == 7
    assert info["table_name"].startswith("ds_")

    datasets = list_datasets(db)
    assert len(datasets) == 1
    assert datasets[0]["name"] == "销售 数据.csv"
    assert datasets[0]["rows"] == 7


def test_register_rejects_bad_files(tmp_path):
    from api.datasets import register_upload
    from api.errors import APIError

    db = str(tmp_path / "t.db")
    with pytest.raises(APIError) as exc_info:
        register_upload(db, "evil.exe", b"data")
    assert exc_info.value.status == 422
    with pytest.raises(APIError):
        register_upload(db, "../../etc/passwd.csv", _csv_bytes())


def test_register_rejects_oversize(tmp_path, monkeypatch):
    import api.datasets as datasets_module
    from api.datasets import register_upload
    from api.errors import APIError

    monkeypatch.setattr(datasets_module, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(APIError) as exc_info:
        register_upload(str(tmp_path / "t.db"), "big.csv", _csv_bytes(100))
    assert exc_info.value.status == 422


def test_resolve_table(tmp_path):
    from api.datasets import register_upload, resolve_table
    from api.errors import APIError

    db = str(tmp_path / "t.db")
    assert resolve_table(db, None) == "orders"
    info = register_upload(db, "a.csv", _csv_bytes(3))
    assert resolve_table(db, info["id"]) == info["table_name"]
    with pytest.raises(APIError) as exc_info:
        resolve_table(db, "nope")
    assert exc_info.value.code.value == "TABLE_NOT_FOUND"


def test_backup_and_restore(tmp_path):
    import sqlite3

    from scripts.backup_db import backup_db

    src = str(tmp_path / "query.db")
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE orders (a TEXT)")
    conn.execute("INSERT INTO orders VALUES ('x')")
    conn.commit()
    conn.close()

    backup_dir = str(tmp_path / "backups")
    path = backup_db(src, backup_dir, keep=2)
    assert os.path.exists(path)

    restored = str(tmp_path / "restored.db")
    import shutil

    shutil.copy(path, restored)
    conn = sqlite3.connect(restored)
    try:
        assert conn.execute("SELECT * FROM orders").fetchall() == [("x",)]
    finally:
        conn.close()


def test_query_page_scoped_table(monkeypatch, tmp_path):
    import api.services as services_module
    from api.services import DataQueryService

    seen = {}

    class FakeEngine:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def ask(self, question, clean_result, max_retries):
            df = pd.DataFrame({"a": [1]})
            return {"question": question, "sql": "SELECT 1", "data": df,
                    "row_count": 1, "execution_time": 0.01, "valid": True,
                    "error": None, "retries": 0, "from_cache": False}

    monkeypatch.setattr(services_module, "QueryEngine", FakeEngine)
    service = DataQueryService(str(tmp_path / "t.db"))
    service.query_page("q", True, 2, 1, 10, table_name="ds_custom_abc")
    assert seen["table_name"] == "ds_custom_abc"


def test_upload_list_and_scoped_query(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from api.auth import create_key
    from api.main import create_app, get_query_service

    db = str(tmp_path / "t.db")
    monkeypatch.setenv("DB_PATH", db)
    key = create_key(db, "pytest")

    class FakeService:
        @property
        def db_path(self):
            return db

        def query_page(self, *args, **kwargs):
            raise AssertionError("should be overridden per-call")

    app = create_app()
    app.dependency_overrides[get_query_service] = FakeService
    headers = {"X-API-Key": key}
    with TestClient(app, headers=headers) as client:
        up = client.post("/api/v1/datasets", files={"file": ("sales.csv", _csv_bytes(5), "text/csv")})
        assert up.status_code == 200, up.text
        dataset_id = up.json()["data"]["id"]

        listed = client.get("/api/v1/datasets")
        assert [d["id"] for d in listed.json()["data"]] == [dataset_id]

    # 作用域查询走真实 service（FakeEngine 隔离 LLM）
    import api.services as services_module

    class FakeEngine:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def ask(self, question, clean_result, max_retries):
            df = pd.DataFrame({"category": ["x"], "amount": [1.0]})
            return {"question": question, "sql": "SELECT 1", "data": df,
                    "row_count": 1, "execution_time": 0.01, "valid": True,
                    "error": None, "retries": 0, "from_cache": False}

    monkeypatch.setattr(services_module, "QueryEngine", FakeEngine)
    from api.main import get_query_service as real_factory

    app2 = create_app()
    with TestClient(app2, headers=headers) as client2:
        ok = client2.post("/api/v1/query", json={"question": "有效问题", "dataset": dataset_id})
        assert ok.status_code == 200, ok.text
        assert ok.json()["data"]["columns"] == ["category", "amount"]

        missing = client2.post("/api/v1/query", json={"question": "有效问题", "dataset": "nope"})
        assert missing.status_code == 404
        assert missing.json()["code"] == "TABLE_NOT_FOUND"
