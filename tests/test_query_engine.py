"""
QueryEngine 单元测试 — 用 mock LLM 避免 API 调用
"""
import json
import os
import tempfile
import sqlite3

import pandas as pd
import pytest

from src.query_engine import QueryEngine
from src.llm_client import LLMClient


class FakeLLM:
    """模拟 LLM 客户端，返回固定 SQL"""

    def __init__(self, sql="SELECT * FROM orders LIMIT 3"):
        self._sql = sql
        self.generate_calls = []
        self.fix_calls = []

    def generate_sql(self, question, schema_text):
        self.generate_calls.append(question)
        return self._sql

    def fix_sql(self, question, schema_text, failed_sql, error_msg):
        self.fix_calls.append(failed_sql)
        return "SELECT * FROM orders LIMIT 10"

    def validate_sql(self, sql):
        return LLMClient(api_key="test").validate_sql(sql)


@pytest.fixture
def engine_with_mock(temp_db_path, sample_df):
    """QueryEngine 注入 FakeLLM"""
    sample_df.to_sql("orders", sqlite3.connect(temp_db_path),
                     if_exists="replace", index=False)
    eng = QueryEngine(db_path=temp_db_path, enable_cache=False, enable_log=False)
    eng.llm = FakeLLM()
    yield eng
    eng.close()


# ── 基础功能 ────────────────────────────────────────────

def test_show_schema(engine):
    """测试显示表结构"""
    schema = engine.show_schema()
    assert "orders" in schema
    assert "order_id" in schema
    assert "category" in schema


def test_load_csv(engine, sample_df):
    """测试加载 CSV 数据"""
    csv_path = os.path.join(tempfile.gettempdir(), "test_load.csv")
    sample_df.to_csv(csv_path, index=False)
    try:
        info = engine.load_data(csv_path, "test_orders")
        assert info["row_count"] == len(sample_df)
        assert info["table_name"] == "test_orders"
    finally:
        if os.path.exists(csv_path):
            os.remove(csv_path)


def test_quality_check(engine):
    """测试数据质量检查"""
    report = engine.quality_check()
    assert "total_rows" in report
    assert "missing_values" in report
    assert report["total_rows"] == 10


# ── 核心查询 ────────────────────────────────────────────

def test_ask_basic(engine_with_mock):
    """测试基本查询流程"""
    engine_with_mock.llm._sql = "SELECT * FROM orders LIMIT 3"
    result = engine_with_mock.ask("最近的三笔订单")
    assert result["valid"] is True
    assert result["error"] is None
    assert result["row_count"] == 3
    assert len(result["data"]) == 3


def test_ask_validates_sql(engine_with_mock):
    """测试 SQL 校验被拒"""
    engine_with_mock.llm._sql = "DROP TABLE orders"
    result = engine_with_mock.ask("删掉订单表")
    assert result["valid"] is False
    assert "安全校验" in result["error"]


def test_ask_auto_retry(engine_with_mock):
    """测试自动重试：第一次失败，第二次修正成功"""
    engine_with_mock.llm._sql = "SELECT nonexistent_column FROM orders"
    result = engine_with_mock.ask("不存在的列查询")
    # 第一次执行会失败（列不存在），触发 fix_sql → 返回有效 SQL
    assert result["error"] is None  # 修正成功
    assert result["retries"] >= 1
    assert result["valid"] is True


def test_ask_retry_exhausted(engine_with_mock):
    """测试重试耗尽：修正的 SQL 仍然无法执行"""
    engine_with_mock.llm._sql = "SELECT nonexistent FROM orders"
    # 让 fix_sql 也返回无效 SQL
    engine_with_mock.llm.fix_sql = lambda *a: "SELECT also_bad FROM orders"
    result = engine_with_mock.ask("会失败的查询", max_retries=1)
    assert result["error"] is not None or result["valid"] is False


# ── 缓存 ───────────────────────────────────────────────

def test_cache_hit(engine):
    """测试查询缓存命中"""
    engine.enable_cache = True
    engine.llm = FakeLLM("SELECT COUNT(*) as cnt FROM orders")

    result1 = engine.ask("总共有多少订单")
    assert result1["from_cache"] is False
    assert len(engine.llm.generate_calls) == 1

    result2 = engine.ask("总共有多少订单")  # 相同问题
    assert result2["from_cache"] is True
    assert len(engine.llm.generate_calls) == 1  # 没再调 API


def test_cache_stats(engine):
    """测试缓存统计"""
    engine.enable_cache = True
    engine.llm = FakeLLM("SELECT 1")
    engine.ask("test1")
    engine.ask("test2")
    stats = engine.cache_stats()
    assert stats["cache_size"] == 2


def test_clear_cache(engine):
    """测试清空缓存"""
    engine.enable_cache = True
    engine.llm = FakeLLM("SELECT 1")
    engine.ask("test")
    assert engine.cache_stats()["cache_size"] == 1
    engine.clear_cache()
    assert engine.cache_stats()["cache_size"] == 0


# ── 日志 ───────────────────────────────────────────────

def test_query_logging(temp_db_path, sample_df):
    """测试查询日志写入 JSONL"""
    sample_df.to_sql("orders", sqlite3.connect(temp_db_path),
                     if_exists="replace", index=False)
    eng = QueryEngine(db_path=temp_db_path, enable_cache=False, enable_log=True)
    eng.llm = FakeLLM("SELECT * FROM orders LIMIT 1")
    eng.ask("测试日志")
    eng.close()

    assert os.path.exists(eng._log_file)
    with open(eng._log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) >= 1
    entry = json.loads(lines[0])
    assert entry["question"] == "测试日志"
    assert "sql" in entry

    # 清理
    if os.path.exists(eng._log_file):
        os.remove(eng._log_file)


def test_logging_disabled(temp_db_path, sample_df):
    """测试禁用日志时不创建文件"""
    sample_df.to_sql("orders", sqlite3.connect(temp_db_path),
                     if_exists="replace", index=False)
    eng = QueryEngine(db_path=temp_db_path, enable_cache=False, enable_log=False)
    eng.llm = FakeLLM("SELECT 1")
    eng.ask("不应该记录")
    assert eng._log_file is None
    eng.close()
