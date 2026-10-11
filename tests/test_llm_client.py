"""
LLMClient 单元测试 — 只测不需要 API 调用的方法

覆盖:
- validate_sql: SQL 安全校验
- _extract_sql: SQL 提取
- 超时/重试配置
- fix_sql 失败历史与调温
- print → logging
"""
import logging
from types import SimpleNamespace

import pytest

from src.llm_client import LLMClient


@pytest.fixture
def client():
    """实例化 LLMClient（用测试 key，不调用 API）"""
    return LLMClient(api_key="test_key")


def _fake_llm_response(content: str) -> SimpleNamespace:
    """构造 OpenAI SDK 形状的假响应"""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _patch_chat(client, monkeypatch, captured: dict, content: str):
    """用假 create 替换 SDK 调用，并捕获调用参数"""
    def fake_create(**kwargs):
        captured.update(kwargs)
        return _fake_llm_response(content)

    monkeypatch.setattr(
        client,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )


class TestValidateSql:
    """SQL 安全校验测试"""

    def test_valid_select(self, client):
        assert client.validate_sql("SELECT * FROM orders") is True

    def test_valid_select_with_where(self, client):
        assert client.validate_sql("SELECT * FROM orders WHERE amount > 100") is True

    def test_valid_with_clause(self, client):
        sql = "WITH t AS (SELECT * FROM orders) SELECT * FROM t"
        assert client.validate_sql(sql) is True

    def test_block_insert(self, client):
        assert client.validate_sql("INSERT INTO orders VALUES (1, 'A')") is False

    def test_block_update(self, client):
        assert client.validate_sql("UPDATE orders SET amount = 100") is False

    def test_block_delete(self, client):
        assert client.validate_sql("DELETE FROM orders") is False

    def test_block_drop(self, client):
        assert client.validate_sql("DROP TABLE orders") is False

    def test_block_create(self, client):
        assert client.validate_sql("CREATE TABLE test (id INT)") is False

    def test_block_truncate(self, client):
        assert client.validate_sql("TRUNCATE TABLE orders") is False

    def test_block_sql_injection_in_string(self, client):
        """测试字符串中包含 DROP 但不应被拦截（正常的 SELECT）"""
        sql = "SELECT 'DROP TABLE' as comment FROM orders"
        assert client.validate_sql(sql) is True

    def test_block_drop_after_semicolon(self, client):
        """测试分号后跟 DROP（SQL 注入常见手法）"""
        sql = "SELECT * FROM orders; DROP TABLE orders"
        assert client.validate_sql(sql) is False

    def test_created_at_column_not_blocked(self, client):
        """测试 created_at 列名不应被 CREATE 误命中"""
        sql = "SELECT created_at FROM orders"
        assert client.validate_sql(sql) is True

    def test_block_multi_statement(self, client):
        """P2-04: 分号分隔的多语句显式拒绝（不再依赖 sqlite3 单语句限制打回）"""
        assert client.validate_sql("SELECT 1; SELECT 2") is False

    def test_block_stacked_pragma(self, client):
        """P2-04: SELECT 后拼接 PRAGMA 被拒绝"""
        assert client.validate_sql("SELECT 1; PRAGMA table_info(orders)") is False

    def test_trailing_semicolon_allowed(self, client):
        """P2-04: 结尾分号（单语句）不受影响"""
        assert client.validate_sql("SELECT * FROM orders;") is True

    def test_semicolon_inside_string_allowed(self, client):
        """P2-04: 字符串字面量内的分号不算语句分隔"""
        sql = "SELECT 'a;b' AS v FROM orders"
        assert client.validate_sql(sql) is True

    def test_leading_comment_allowed(self, client):
        """P2-14: 移除死代码后，注释前缀的 SQL 仍然放行"""
        sql = "-- 查询订单\nSELECT * FROM orders"
        assert client.validate_sql(sql) is True


class TestExtractSql:
    """SQL 提取测试"""

    def test_extract_from_sql_codeblock(self, client):
        raw = "这是结果：\n```sql\nSELECT * FROM orders\n```\n"
        sql = client._extract_sql(raw)
        assert sql == "SELECT * FROM orders"

    def test_extract_from_plain_codeblock(self, client):
        raw = "```\nSELECT 1\n```"
        sql = client._extract_sql(raw)
        assert sql == "SELECT 1"

    def test_extract_plain_select(self, client):
        raw = "SELECT * FROM orders WHERE amount > 100;"
        sql = client._extract_sql(raw)
        assert "SELECT" in sql
        assert "orders" in sql

    def test_extract_multiline_sql(self, client):
        raw = "```sql\nSELECT category,\n       SUM(amount)\nFROM orders\nGROUP BY category\n```"
        sql = client._extract_sql(raw)
        assert "category" in sql
        assert "GROUP BY" in sql


class TestTimeoutConfig:
    """P1-04/P2-11: 显式超时 + SDK 内建重试"""

    def test_default_timeout_30s(self):
        """P1-04: 默认超时 30s（排除环境变量干扰）"""
        import os
        saved = os.environ.pop("LLM_TIMEOUT_SECONDS", None)
        try:
            c = LLMClient(api_key="test_key")
            assert c.timeout == 30.0
            assert c.client.timeout == 30.0
        finally:
            if saved is not None:
                os.environ["LLM_TIMEOUT_SECONDS"] = saved

    def test_sdk_max_retries_2(self, client):
        """P2-11: SDK 内建重试覆盖瞬时故障（连接错误/429/5xx）"""
        assert client.client.max_retries == 2

    def test_explicit_timeout_param(self):
        c = LLMClient(api_key="test_key", timeout=5)
        assert c.timeout == 5
        assert c.client.timeout == 5

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "7.5")
        c = LLMClient(api_key="test_key")
        assert c.timeout == 7.5

    def test_env_invalid_value_rejected(self, monkeypatch):
        monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "abc")
        with pytest.raises(ValueError):
            LLMClient(api_key="test_key")

    def test_env_negative_value_rejected(self, monkeypatch):
        monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "-1")
        with pytest.raises(ValueError):
            LLMClient(api_key="test_key")


class TestFixSql:
    """P2-12: fix_sql 携带历次失败历史并逐步调温"""

    def test_prompt_includes_history_and_raises_temperature(self, client, monkeypatch):
        captured = {}
        _patch_chat(client, monkeypatch, captured, "```sql\nSELECT 1\n```")
        history = [
            {"sql": "SELECT bad1 FROM orders", "error": "no such column: bad1"},
            {"sql": "SELECT bad2 FROM orders", "error": "no such column: bad2"},
        ]

        sql = client.fix_sql(
            "问题", "schema",
            "SELECT bad3 FROM orders",
            "no such column: bad3",
            history=history,
        )

        assert sql == "SELECT 1"
        user_prompt = captured["messages"][1]["content"]
        assert "bad1" in user_prompt  # 历次失败 SQL 进入 prompt
        assert "bad2" in user_prompt
        assert "bad3" in user_prompt  # 最新失败仍在
        assert "no such column: bad1" in user_prompt  # 错误摘要进入 prompt
        assert captured["temperature"] == pytest.approx(0.4)  # 逐步调温

    def test_prompt_without_history_keeps_low_temperature(self, client, monkeypatch):
        captured = {}
        _patch_chat(client, monkeypatch, captured, "```sql\nSELECT 1\n```")

        client.fix_sql("问题", "schema", "SELECT bad FROM orders", "err")

        user_prompt = captured["messages"][1]["content"]
        assert "历次失败的尝试" not in user_prompt
        assert captured["temperature"] == pytest.approx(0.1)


class TestLogging:
    """P2-10: 调试信息走 logging，不再 print 到 stdout"""

    def test_generate_sql_logs_not_prints(self, client, monkeypatch, caplog, capsys):
        captured = {}
        _patch_chat(client, monkeypatch, captured, "```sql\nSELECT 42\n```")

        with caplog.at_level(logging.DEBUG, logger="src.llm_client"):
            sql = client.generate_sql("问题", "schema")

        assert sql == "SELECT 42"
        assert any("SELECT 42" in r.message for r in caplog.records)
        captured_out = capsys.readouterr()
        assert captured_out.out == ""  # stdout 不再有 [DEBUG] 打印

    def test_fix_sql_logs_not_prints(self, client, monkeypatch, caplog, capsys):
        captured = {}
        _patch_chat(client, monkeypatch, captured, "```sql\nSELECT fixed\n```")

        with caplog.at_level(logging.DEBUG, logger="src.llm_client"):
            sql = client.fix_sql("问题", "schema", "SELECT bad", "err")

        assert sql == "SELECT fixed"
        assert any("fixed" in r.message for r in caplog.records)
        assert capsys.readouterr().out == ""
