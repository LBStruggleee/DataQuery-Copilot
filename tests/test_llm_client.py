"""
LLMClient 单元测试 — 只测不需要 API 调用的方法

覆盖:
- validate_sql: SQL 安全校验
- _extract_sql: SQL 提取
"""
import pytest

from src.llm_client import LLMClient


@pytest.fixture
def client():
    """实例化 LLMClient（用测试 key，不调用 API）"""
    return LLMClient(api_key="test_key")


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
