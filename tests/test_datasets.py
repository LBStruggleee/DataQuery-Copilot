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


def test_register_rejects_legacy_xls(tmp_path):
    """P2-20：.xls 白名单移除——xlrd 未声明，放行必然 422。"""
    from api.datasets import register_upload
    from api.errors import APIError, ErrorCode

    db = str(tmp_path / "t.db")
    with pytest.raises(APIError) as exc_info:
        register_upload(db, "legacy.xls", b"\xd0\xcf\x11\xe0")
    assert exc_info.value.code is ErrorCode.UPLOAD_REJECTED


def test_register_upload_gbk_fallback(tmp_path):
    """P2-21：GBK 编码 CSV 走 utf-8-sig → gbk 回退链；BOM 由 utf-8-sig 剥离。"""
    from api.datasets import register_upload

    db = str(tmp_path / "t.db")
    gbk_csv = "类别,金额\n食品,12.5\n图书,9.9\n".encode("gbk")
    info = register_upload(db, "gbk.csv", gbk_csv)
    assert info["rows"] == 2

    bom_csv = "类别,金额\n食品,12.5\n".encode("utf-8-sig")
    info2 = register_upload(str(tmp_path / "bom.db"), "bom.csv", bom_csv)
    assert info2["rows"] == 1


def test_register_rejects_undecodable_csv(tmp_path):
    """P2-21：两种编码都解不开的内容仍以 UPLOAD_REJECTED 422 拒绝。"""
    from api.datasets import register_upload
    from api.errors import APIError, ErrorCode

    garbage = bytes([0xFF, 0xFE, 0x41, 0x00, 0x42]) * 64
    with pytest.raises(APIError) as exc_info:
        register_upload(str(tmp_path / "t.db"), "bad.csv", garbage)
    assert exc_info.value.code is ErrorCode.UPLOAD_REJECTED


def test_register_enforces_dataset_count_limit(tmp_path, monkeypatch):
    """P1-10：数据集数量达上限后上传返回 429。"""
    import api.datasets as datasets_module
    from api.datasets import register_upload
    from api.errors import APIError, ErrorCode

    monkeypatch.setattr(datasets_module, "MAX_DATASETS", 1)
    db = str(tmp_path / "t.db")
    register_upload(db, "first.csv", _csv_bytes(3))
    with pytest.raises(APIError) as exc_info:
        register_upload(db, "second.csv", _csv_bytes(3))
    assert exc_info.value.code is ErrorCode.RATE_LIMITED
    assert exc_info.value.status == 429


def test_remove_dataset_rolls_back_registration(tmp_path):
    """P1-10 竞态回滚助手：删除 datasets 行并 DROP 对应表。"""
    from api.datasets import list_datasets, register_upload, remove_dataset, resolve_table
    from api.errors import APIError

    db = str(tmp_path / "t.db")
    info = register_upload(db, "a.csv", _csv_bytes(3))
    remove_dataset(db, info["id"], info["table_name"])

    assert list_datasets(db) == []
    with pytest.raises(APIError) as exc_info:
        resolve_table(db, info["id"])
    assert exc_info.value.code.value == "TABLE_NOT_FOUND"


def test_register_rejects_oversize(tmp_path, monkeypatch):
    import api.datasets as datasets_module
    from api.datasets import register_upload
    from api.errors import APIError

    monkeypatch.setattr(datasets_module, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(APIError) as exc_info:
        register_upload(str(tmp_path / "t.db"), "big.csv", _csv_bytes(100))
    assert exc_info.value.status == 422


# ── P2-36：上传解析失败 / 空内容 / 扩展名大小写边界 ───────────────────

def test_register_rejects_empty_csv(tmp_path):
    """P2-36：空 CSV（零字节）→ pandas EmptyDataError 转 422 UPLOAD_REJECTED。"""
    from api.datasets import register_upload
    from api.errors import APIError, ErrorCode

    with pytest.raises(APIError) as exc_info:
        register_upload(str(tmp_path / "t.db"), "empty.csv", b"")
    assert exc_info.value.code is ErrorCode.UPLOAD_REJECTED
    assert exc_info.value.status == 422


def test_register_rejects_malformed_xlsx(tmp_path):
    """P2-36：.xlsx 扩展名但内容不是合法 zip 容器 → 422 UPLOAD_REJECTED。"""
    from api.datasets import register_upload
    from api.errors import APIError, ErrorCode

    with pytest.raises(APIError) as exc_info:
        register_upload(str(tmp_path / "t.db"), "broken.xlsx", b"not-an-xlsx-container")
    assert exc_info.value.code is ErrorCode.UPLOAD_REJECTED


def test_register_extension_case_insensitive(tmp_path):
    """P2-36：扩展名比较不区分大小写——.CSV 放行，大写 .EXE 同样拒绝。"""
    from api.datasets import register_upload
    from api.errors import APIError

    db = str(tmp_path / "t.db")
    info = register_upload(db, "数据.CSV", _csv_bytes(2))
    assert info["rows"] == 2

    with pytest.raises(APIError):
        register_upload(db, "evil.EXE", b"MZ")
    with pytest.raises(APIError):
        register_upload(db, "evil.Exe", b"MZ")


# ── P1-11：xlsx 声明维度解压炸弹防护 ─────────────────────────────────

def _small_xlsx_bytes(rows=5, cols=4):
    """生成带表头 + rows 行数据的小 xlsx"""
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    buf = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append([f"col{i}" for i in range(cols)])
    for r in range(rows):
        ws.append([r * cols + c for c in range(cols)])
    wb.save(buf)
    return buf.getvalue()


def test_register_xlsx_within_declared_limit(tmp_path):
    """P1-11：声明维度在上限内的小 xlsx 正常入库。"""
    from api.datasets import register_upload

    info = register_upload(str(tmp_path / "t.db"), "small.xlsx", _small_xlsx_bytes(rows=5, cols=4))
    assert info["rows"] == 5
    assert info["table_name"].startswith("ds_")


def test_register_rejects_oversized_declared_xlsx(tmp_path, monkeypatch):
    """P1-11：声明维度估算的单元格数超上限 → 解析前直接拒绝（不给 pandas 全量加载机会）。"""
    import api.datasets as datasets_module
    from api.datasets import register_upload
    from api.errors import APIError, ErrorCode

    monkeypatch.setattr(datasets_module, "MAX_XLSX_CELLS", 10)  # 5×4=20 > 10
    with pytest.raises(APIError) as exc_info:
        register_upload(str(tmp_path / "t.db"), "bomb.xlsx", _small_xlsx_bytes(rows=5, cols=4))
    assert exc_info.value.code is ErrorCode.UPLOAD_REJECTED
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
    # P2-34：API 查询路径不写查询日志（用户问题/SQL 不落盘）
    assert seen["enable_log"] is False
    assert seen["enable_cache"] is False


def test_upload_list_and_scoped_query(tmp_path, monkeypatch, api_test_client):
    from tests.conftest import FakeQueryService

    class ShouldNotQueryService(FakeQueryService):
        def query_page(self, *args, **kwargs):
            raise AssertionError("should be overridden per-call")

    client = api_test_client(service_cls=ShouldNotQueryService)
    with client:
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
    from fastapi.testclient import TestClient

    from api.main import create_app

    app2 = create_app()
    with TestClient(app2, headers={"X-API-Key": client.key}) as client2:
        ok = client2.post("/api/v1/query", json={"question": "有效问题", "dataset": dataset_id})
        assert ok.status_code == 200, ok.text
        assert ok.json()["data"]["columns"] == ["category", "amount"]

        missing = client2.post("/api/v1/query", json={"question": "有效问题", "dataset": "nope"})
        assert missing.status_code == 404
        assert missing.json()["code"] == "TABLE_NOT_FOUND"
