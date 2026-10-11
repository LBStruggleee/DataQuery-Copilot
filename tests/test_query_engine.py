"""
QueryEngine 单元测试 — 用 mock LLM 避免 API 调用
"""
import json
import logging
import os
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
        self.fix_history = []
        self._validator = None  # 复用 LLMClient，避免高频构造 httpx 客户端拖慢测试

    def generate_sql(self, question, schema_text):
        self.generate_calls.append(question)
        return self._sql

    def fix_sql(self, question, schema_text, failed_sql, error_msg, history=None):
        self.fix_calls.append(failed_sql)
        self.fix_history.append(history)
        return "SELECT * FROM orders LIMIT 10"

    def validate_sql(self, sql):
        if self._validator is None:
            self._validator = LLMClient(api_key="test")
        return self._validator.validate_sql(sql)


@pytest.fixture
def engine_with_mock(temp_db_path, sample_df):
    """QueryEngine 注入 FakeLLM"""
    conn = sqlite3.connect(temp_db_path)
    try:
        sample_df.to_sql("orders", conn, if_exists="replace", index=False)
    finally:
        conn.close()
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


def test_load_csv(engine, sample_df, tmp_path):
    """测试加载 CSV 数据"""
    csv_path = tmp_path / "test_load.csv"
    sample_df.to_csv(csv_path, index=False)
    info = engine.load_data(str(csv_path), "test_orders")
    assert info["row_count"] == len(sample_df)
    assert info["table_name"] == "test_orders"


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
    """测试重试耗尽：修正的 SQL 仍然无法执行

    P2-38: 弱析取断言（error is not None or valid is False）几乎恒真，
    改为精确断言错误前缀、错误来源与重试次数。
    """
    engine_with_mock.llm._sql = "SELECT nonexistent FROM orders"
    # 让 fix_sql 也返回无效 SQL
    engine_with_mock.llm.fix_sql = lambda *a, **k: "SELECT also_bad FROM orders"
    result = engine_with_mock.ask("会失败的查询", max_retries=1)

    assert result["error_code"] == "EXECUTION_FAILED"
    assert result["error"] is not None
    assert result["error"].startswith("SQL 执行失败（已重试 1 次）")
    assert "no such column" in result["error"]  # 数据库错误原文进入错误信息
    assert "also_bad" in result["error"]  # 失败的是最后一次修正后的 SQL，而非首条
    assert result["retries"] == 1


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
    conn = sqlite3.connect(temp_db_path)
    try:
        sample_df.to_sql("orders", conn, if_exists="replace", index=False)
    finally:
        conn.close()
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
    conn = sqlite3.connect(temp_db_path)
    try:
        sample_df.to_sql("orders", conn, if_exists="replace", index=False)
    finally:
        conn.close()
    eng = QueryEngine(db_path=temp_db_path, enable_cache=False, enable_log=False)
    eng.llm = FakeLLM("SELECT 1")
    eng.ask("不应该记录")
    assert eng._log_file is None
    eng.close()


# ── P1-03: 缓存键纳入表名 + load_data 清缓存 ────────────

def test_cache_key_includes_table_name(engine, sample_df):
    """P1-03: 切换表后相同问题不得命中旧表的缓存"""
    engine.enable_cache = True
    engine.llm = FakeLLM("SELECT COUNT(*) as cnt FROM orders")
    conn = sqlite3.connect(engine.loader.db_path)
    try:
        sample_df.to_sql("products", conn, if_exists="replace", index=False)
    finally:
        conn.close()

    engine.ask("总共有多少订单")
    engine.table_name = "products"
    result2 = engine.ask("总共有多少订单")
    assert result2["from_cache"] is False
    assert len(engine.llm.generate_calls) == 2  # 表不同，重新查询


def test_load_data_clears_cache(engine, sample_df, tmp_path):
    """P1-03: load_data 覆盖加载数据后旧缓存作废"""
    engine.enable_cache = True
    engine.llm = FakeLLM("SELECT COUNT(*) as cnt FROM orders")
    engine.ask("总共有多少订单")
    assert engine.cache_stats()["cache_size"] == 1

    csv_path = tmp_path / "reload_orders.csv"
    sample_df.to_csv(csv_path, index=False)
    engine.load_data(str(csv_path))  # 同名表覆盖加载

    assert engine.cache_stats()["cache_size"] == 0


# ── P2-01: max_retries 校验 ─────────────────────────────

def test_ask_rejects_negative_max_retries(engine):
    """P2-01: max_retries < 0 直接拒绝，不再返回假成功"""
    with pytest.raises(ValueError):
        engine.ask("测试", max_retries=-1)


# ── P2-02: 缓存 LRU 上限 + 日志轮转 ─────────────────────

def test_cache_lru_eviction(engine, monkeypatch):
    """P2-02: 缓存超过上限 100 后按 LRU 淘汰最早条目"""
    import src.query_engine as qe
    monkeypatch.setattr(qe, "CACHE_MAX_ENTRIES", 2)  # 调小上限便于测试
    engine.enable_cache = True
    engine.llm = FakeLLM("SELECT 1")

    engine.ask("q1")
    engine.ask("q2")
    engine.ask("q1")  # 命中 → 移到队尾续命
    engine.ask("q3")  # 淘汰 q2

    keys = engine.cache_stats()["cached_questions"]
    assert engine.cache_stats()["cache_size"] == 2
    assert "orders::q1" in keys   # 最近使用的保留
    assert "orders::q2" not in keys  # 最久未用的被淘汰


def test_cache_lru_default_limit_100(engine):
    """P2-02: 默认上限 100"""
    engine.enable_cache = True
    engine.llm = FakeLLM("SELECT 1")
    for i in range(105):
        engine.ask(f"问题{i}")
    stats = engine.cache_stats()
    assert stats["cache_size"] == 100
    assert "orders::问题0" not in stats["cached_questions"]
    assert "orders::问题104" in stats["cached_questions"]


def test_query_log_rotation(temp_db_path, sample_df):
    """P2-02: JSONL 日志超过大小上限后轮转为 *.1"""
    conn = sqlite3.connect(temp_db_path)
    try:
        sample_df.to_sql("orders", conn, if_exists="replace", index=False)
    finally:
        conn.close()
    eng = QueryEngine(db_path=temp_db_path, enable_cache=False, enable_log=True)
    eng.llm = FakeLLM("SELECT 1")
    eng._log_max_bytes = 10  # 调小阈值触发轮转
    log_file = eng._log_file
    rotated = log_file + ".1"
    try:
        eng.ask("第一条")
        eng.ask("第二条")  # 触发轮转
        eng.ask("第三条")  # 再次轮转，覆盖旧轮转文件
    finally:
        eng.close()

    assert os.path.exists(rotated)
    with open(rotated, "r", encoding="utf-8") as f:
        assert len(f.readlines()) >= 1
    with open(log_file, "r", encoding="utf-8") as f:
        assert len(f.readlines()) >= 1
    for p in (log_file, rotated):
        if os.path.exists(p):
            os.remove(p)


# ── P2-03: 出入缓存深拷贝 ───────────────────────────────

def test_cache_not_polluted_by_caller_mutation(engine):
    """P2-03: 调用方原地修改返回的 DataFrame 不污染缓存"""
    engine.enable_cache = True
    engine.llm = FakeLLM("SELECT * FROM orders")
    r1 = engine.ask("查订单")
    amount_before = r1["data"]["amount"].iloc[0]
    r1["data"].loc[0, "amount"] = -99999.0  # 调用方原地修改

    r2 = engine.ask("查订单")
    assert r2["from_cache"] is True
    assert r2["data"]["amount"].iloc[0] == amount_before


# ── P2-10: 核心库 print 改 logging ──────────────────────

def test_ask_operational_messages_use_logging(engine, caplog, capsys):
    """P2-10: 重试等运行信息走 logging，不再直接 print"""
    engine.enable_log = False
    engine.llm = FakeLLM("SELECT nonexistent FROM orders")  # 触发一次重试
    with caplog.at_level(logging.WARNING, logger="src.query_engine"):
        engine.ask("触发重试的查询")
    assert any("重试" in r.message for r in caplog.records)
    captured = capsys.readouterr()
    assert captured.out == ""


# ── P2-12: 修正闭环携带失败历史 ─────────────────────────

def test_fix_sql_receives_failure_history(engine_with_mock):
    """P2-12: fix_sql 收到历次失败的 SQL 与错误摘要"""
    sqls = ["SELECT nope1 FROM orders", "SELECT nope2 FROM orders", "SELECT * FROM orders LIMIT 1"]
    engine_with_mock.llm._sql = sqls[0]
    history_seen = []

    def fake_fix(question, schema_text, failed_sql, error_msg, history=None):
        history_seen.append(history)
        return sqls[len(history_seen)]  # 依次返回下一个 SQL

    engine_with_mock.llm.fix_sql = fake_fix
    result = engine_with_mock.ask("反复失败的查询", max_retries=2)

    assert result["valid"] is True
    assert history_seen[0] == []  # 第一次修正无历史
    assert len(history_seen[1]) == 1
    assert "nope1" in history_seen[1][0]["sql"]
    assert "no such column" in history_seen[1][0]["error"].lower()


# ── P2-13: handle_missing 可选开关 ──────────────────────

def test_ask_handle_missing_fills_nan(engine_with_mock):
    """P2-13: handle_missing=True 接入 DataCleaner 缺失值填充"""
    engine_with_mock.llm._sql = "SELECT * FROM orders"
    result = engine_with_mock.ask("全部订单", handle_missing=True)
    assert result["data"].isna().sum().sum() == 0


def test_ask_handle_missing_default_off(engine_with_mock):
    """P2-13: 默认关闭，保持原有行为（缺失值保留）"""
    engine_with_mock.llm._sql = "SELECT * FROM orders"
    result = engine_with_mock.ask("全部订单")
    assert result["data"]["category"].isna().sum() == 1


# ── error_code: 供下游结构化判断 ────────────────────────

def test_ask_error_code_sql_rejected(engine_with_mock):
    engine_with_mock.llm._sql = "DROP TABLE orders"
    result = engine_with_mock.ask("删掉订单表")
    assert result["error_code"] == "SQL_REJECTED"


def test_ask_error_code_generation_failed(engine_with_mock):
    def boom(question, schema_text):
        raise RuntimeError("api down")
    engine_with_mock.llm.generate_sql = boom
    result = engine_with_mock.ask("测试")
    assert result["error_code"] == "SQL_GENERATION_FAILED"


def test_ask_error_code_execution_failed(engine_with_mock):
    engine_with_mock.llm._sql = "SELECT nonexistent FROM orders"
    engine_with_mock.llm.fix_sql = lambda *a, **k: "SELECT also_missing FROM orders"
    result = engine_with_mock.ask("查询", max_retries=1)
    assert result["error_code"] == "EXECUTION_FAILED"


def test_ask_success_error_code_none(engine_with_mock):
    engine_with_mock.llm._sql = "SELECT * FROM orders LIMIT 3"
    result = engine_with_mock.ask("正常查询")
    assert result["error"] is None
    assert result["error_code"] is None


# ── SUP-02: quality_check 复用表名白名单 ────────────────

def test_quality_check_rejects_invalid_table_name(engine):
    """SUP-02: quality_check 不再绕过核心库表名校验"""
    engine.table_name = "orders; DROP TABLE orders"
    with pytest.raises(ValueError):
        engine.quality_check()


# ── P1-09: ask() 执行窗口表白名单 ───────────────────────

def test_ask_blocks_cross_table_sql_with_clear_error(engine_with_mock, temp_db_path):
    """P1-09: LLM 被诱导生成引用其他表的 SQL 时，执行层表白名单拦截并返回明确错误"""
    # 造一张敏感表，模拟 validate_sql 拦不住的 SELECT key_hash FROM api_keys 场景
    conn = sqlite3.connect(temp_db_path)
    try:
        pd.DataFrame({"key_hash": ["x"], "name": ["k"]}).to_sql("api_keys", conn, index=False)
    finally:
        conn.close()

    engine_with_mock.llm._sql = "SELECT key_hash, name FROM api_keys"
    engine_with_mock.llm.fix_sql = lambda *a, **k: "SELECT key_hash FROM api_keys"
    result = engine_with_mock.ask("看看有哪些 key", max_retries=1)

    assert result["error"] is not None
    assert "api_keys" in result["error"]  # 明确指出被拒对象
    assert "拒绝" in result["error"]
    assert result["error_code"] == "EXECUTION_FAILED"


def test_ask_cross_table_sql_fixed_by_retry(engine_with_mock, temp_db_path):
    """P1-09: 明确错误可被修正闭环消化——LLM 改写为只查当前表后成功"""
    conn = sqlite3.connect(temp_db_path)
    try:
        pd.DataFrame({"key_hash": ["x"], "name": ["k"]}).to_sql("api_keys", conn, index=False)
    finally:
        conn.close()

    engine_with_mock.llm._sql = "SELECT key_hash FROM api_keys"
    result = engine_with_mock.ask("看看有哪些 key", max_retries=2)

    assert result["error"] is None
    assert result["valid"] is True
    assert result["retries"] == 1  # 第一次被表白名单拒绝，修正后成功
    assert result["row_count"] > 0  # 修正后的 SQL（默认查 orders）成功返回数据
