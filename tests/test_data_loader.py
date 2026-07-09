"""
DataLoader 单元测试
"""
import os
import tempfile
import pandas as pd
import pytest

from src.data_loader import DataLoader


@pytest.fixture
def temp_loader():
    """创建临时数据库 + 测试数据"""
    db_path = os.path.join(tempfile.gettempdir(), "test_query.db")
    loader = DataLoader(db_path)

    # 写入测试数据
    df = pd.DataFrame({
        "order_id": [1, 2, 3, 4, 5],
        "category": ["电子产品", "服装", "电子产品", "食品", "服装"],
        "amount": [100.0, 200.0, 150.0, 50.0, 300.0],
        "quantity": [1, 2, 1, 3, 1],
    })
    df.to_sql("orders", loader.conn, if_exists="replace", index=False)

    yield loader

    loader.close()
    if os.path.exists(db_path):
        os.remove(db_path)


def test_get_table_info(temp_loader):
    """测试获取表结构信息"""
    info = temp_loader.get_table_info("orders")
    assert info["table_name"] == "orders"
    assert len(info["columns"]) == 4
    col_names = [c["name"] for c in info["columns"]]
    assert "order_id" in col_names
    assert "category" in col_names


def test_get_schema_text(temp_loader):
    """测试获取表结构文本"""
    schema = temp_loader.get_schema_text("orders")
    assert "orders" in schema
    assert "order_id" in schema
    assert "category" in schema
    assert "amount" in schema


def test_execute_query(temp_loader):
    """测试 SQL 执行"""
    df = temp_loader.execute_query("SELECT COUNT(*) as cnt FROM orders")
    assert df.iloc[0]["cnt"] == 5

    df2 = temp_loader.execute_query("SELECT category, SUM(amount) as total FROM orders GROUP BY category")
    assert len(df2) == 3  # 三个品类


def test_execute_query_with_where(temp_loader):
    """测试带 WHERE 的查询"""
    df = temp_loader.execute_query("SELECT * FROM orders WHERE amount > 100")
    assert len(df) == 3  # 200, 150, 300 三条


def test_load_csv(temp_loader):
    """测试 CSV 导入"""
    # 创建临时 CSV
    csv_path = os.path.join(tempfile.gettempdir(), "test_data.csv")
    df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
    df.to_csv(csv_path, index=False)

    info = temp_loader.load_csv(csv_path, "test_table")
    assert info["row_count"] == 2
    assert info["table_name"] == "test_table"

    os.remove(csv_path)
