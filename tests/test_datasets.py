"""Phase 2: 数据集注册表、上传入库、作用域查询、备份。"""

import io

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
