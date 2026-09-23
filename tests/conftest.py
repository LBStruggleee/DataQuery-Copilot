"""
pytest 配置 — 共享 fixtures：数据库、数据、mock
"""
import sys
import os
import tempfile
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
def temp_db_path():
    """临时数据库路径"""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="test_")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


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
