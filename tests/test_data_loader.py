"""
DataLoader 单元测试
"""
import pandas as pd
import pytest

from src.data_loader import DataLoader


@pytest.fixture
def temp_loader(tmp_path):
    """创建临时数据库 + 测试数据（P2-39：pytest tmp_path，并行运行不互相污染）"""
    db_path = str(tmp_path / "test_query.db")
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


def test_load_csv(temp_loader, tmp_path):
    """测试 CSV 导入"""
    # 创建临时 CSV
    csv_path = tmp_path / "test_data.csv"
    df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
    df.to_csv(csv_path, index=False)

    info = temp_loader.load_csv(str(csv_path), "test_table")
    assert info["row_count"] == 2
    assert info["table_name"] == "test_table"


# ── P1-01: Excel 导入默认第一个工作表 ───────────────────

def _write_multi_sheet_xlsx(path):
    """生成含两个工作表的 xlsx"""
    pytest.importorskip("openpyxl")
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"id": [1, 2], "name": ["A", "B"]}).to_excel(
            writer, sheet_name="first", index=False
        )
        pd.DataFrame({"x": [9, 9, 9]}).to_excel(writer, sheet_name="second", index=False)


def test_load_excel_defaults_to_first_sheet(temp_loader, tmp_path):
    """P1-01: 默认导入第一个工作表，不再因 sheet_name=None 返回 dict 而崩溃"""
    path = tmp_path / "multi.xlsx"
    _write_multi_sheet_xlsx(path)

    info = temp_loader.load_excel(str(path), "excel_table")
    assert info["row_count"] == 2  # 只有第一个工作表的 2 行
    assert info["table_name"] == "excel_table"
    col_names = [c["name"] for c in info["columns"]]
    assert col_names == ["id", "name"]


def test_load_excel_named_sheet(temp_loader, tmp_path):
    """P1-01: 显式指定 sheet_name 仍生效"""
    path = tmp_path / "multi.xlsx"
    _write_multi_sheet_xlsx(path)

    info = temp_loader.load_excel(str(path), "excel_second", sheet_name="second")
    assert info["row_count"] == 3


# ── P2-08: errors=ignore 改 try/except + raise ─────────

def test_optimize_dtypes_convert_or_keep(temp_loader):
    """P2-08: 可转换则转换，不可转换保持原样（行为与 errors=ignore 时代一致）"""
    df = pd.DataFrame({
        "qty": ["1", "2", "3"],
        "note": ["abc", "def", "ghi"],
        "when": ["2026-01-01", "2026-01-02", "2026-01-03"],
    })
    result = temp_loader._optimize_dtypes(df)
    assert pd.api.types.is_numeric_dtype(result["qty"])
    assert pd.api.types.is_datetime64_any_dtype(result["when"])
    assert result["note"].tolist() == ["abc", "def", "ghi"]  # 均不可转，保持 object


# ── P2-09: 表名标识符白名单 ─────────────────────────────

@pytest.mark.parametrize("bad_name", [
    "orders; DROP TABLE orders",
    "orders--",
    "1table",
    "bad name",
    'orders"',
    "",
])
def test_validate_table_name_rejects_bad_names(temp_loader, bad_name):
    """P2-09: 非法表名（注入/空格/数字开头等）被白名单拒绝"""
    with pytest.raises(ValueError):
        temp_loader.validate_table_name(bad_name)


def test_validate_table_name_accepts_normal(temp_loader):
    """P2-09: 正常标识符放行且与 API 层规则一致"""
    assert temp_loader.validate_table_name("orders") == "orders"
    assert temp_loader.validate_table_name("test_orders_2") == "test_orders_2"


def test_get_table_info_rejects_bad_name(temp_loader):
    """P2-09: PRAGMA table_info 的 f-string 插值入口有白名单防护"""
    with pytest.raises(ValueError):
        temp_loader.get_table_info("orders; DROP TABLE orders")


def test_load_csv_rejects_bad_table_name(temp_loader, tmp_path):
    """P2-09: load_csv 入口校验表名"""
    csv_path = tmp_path / "x.csv"
    pd.DataFrame({"id": [1]}).to_csv(csv_path, index=False)
    with pytest.raises(ValueError):
        temp_loader.load_csv(str(csv_path), "bad name")


# ── P1-05: 执行层行数上限 + 超时中断 ────────────────────

def test_execute_query_respects_max_rows(temp_db_path):
    """P1-05: execute_query 只物化 max_rows 行"""
    loader = DataLoader(temp_db_path, max_rows=5)
    try:
        pd.DataFrame({"n": range(50)}).to_sql("t", loader.conn, index=False)
        df = loader.execute_query("SELECT * FROM t")
        assert len(df) == 5
        assert list(df["n"]) == [0, 1, 2, 3, 4]
        # 调用方可显式覆盖
        df2 = loader.execute_query("SELECT * FROM t", max_rows=10)
        assert len(df2) == 10
    finally:
        loader.close()


def test_execute_query_interrupts_runaway_query(temp_db_path):
    """P1-05: 无终止的 WITH RECURSIVE 被超时中断，且连接可恢复"""
    loader = DataLoader(temp_db_path, query_timeout=0.5)
    try:
        loader.conn.execute("CREATE TABLE t (n INTEGER)")
        loader.conn.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(100)])
        loader.conn.commit()

        sql = (
            "WITH RECURSIVE c(i) AS (SELECT 1 UNION ALL SELECT i+1 FROM c) "
            "SELECT COUNT(*) AS c FROM c"
        )
        with pytest.raises(TimeoutError):
            loader.execute_query(sql)

        # 中断后连接仍可用
        df = loader.execute_query("SELECT COUNT(*) AS c FROM t")
        assert df.iloc[0]["c"] == 100
    finally:
        loader.close()


def test_data_loader_rejects_invalid_limits(temp_db_path):
    """P1-05: max_rows / query_timeout 非法配置在入口拒绝"""
    with pytest.raises(ValueError):
        DataLoader(temp_db_path, max_rows=0)
    with pytest.raises(ValueError):
        DataLoader(temp_db_path, query_timeout=0)


# ── P2-37: PRAGMA table_info / load_excel 插值入口的核心库层防护 ────

def test_get_schema_text_rejects_bad_table_name(temp_loader):
    """P2-37: get_schema_text 走 get_table_info，PRAGMA table_info f-string
    插值之前有白名单校验，直连路径不可注入"""
    with pytest.raises(ValueError):
        temp_loader.get_schema_text('orders"); DROP TABLE orders; PRAGMA table_info("x')


def test_load_excel_rejects_bad_table_name(temp_loader, tmp_path):
    """P2-37: load_excel 入口同样校验表名"""
    pytest.importorskip("openpyxl")
    path = tmp_path / "tiny.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"id": [1]}).to_excel(writer, index=False)
    with pytest.raises(ValueError):
        temp_loader.load_excel(str(path), 'bad"; DROP TABLE orders; --')


# ── P1-09: execute_query 查询窗口表白名单（set_authorizer） ──────────

def test_execute_query_whitelist_allows_current_table_and_master(temp_db_path):
    """P1-09: 白名单内的表与 sqlite_master 可正常 SELECT"""
    loader = DataLoader(temp_db_path)
    try:
        pd.DataFrame({"a": [1, 2]}).to_sql("t", loader.conn, index=False)
        df = loader.execute_query("SELECT * FROM t", allowed_tables=["t"])
        assert list(df["a"]) == [1, 2]

        # sqlite_master 读取放行
        master = loader.execute_query(
            "SELECT name FROM sqlite_master WHERE type='table'", allowed_tables=["t"]
        )
        assert "t" in set(master["name"])
    finally:
        loader.close()


def test_execute_query_whitelist_denies_other_tables(temp_db_path):
    """P1-09: 引用白名单之外的表返回明确错误（含表名），连接仍可用"""
    loader = DataLoader(temp_db_path)
    try:
        pd.DataFrame({"a": [1]}).to_sql("t", loader.conn, index=False)
        pd.DataFrame({"key_hash": ["x"], "name": ["k"]}).to_sql("api_keys", loader.conn, index=False)

        with pytest.raises(PermissionError) as exc_info:
            loader.execute_query("SELECT key_hash, name FROM api_keys", allowed_tables=["t"])
        assert "api_keys" in str(exc_info.value)

        # 聚合读（COUNT(*)）同样受表白名单约束
        with pytest.raises(PermissionError):
            loader.execute_query("SELECT COUNT(*) AS c FROM api_keys", allowed_tables=["t"])

        # 连接未被破坏，白名单内的查询仍可执行
        ok = loader.execute_query("SELECT COUNT(*) AS c FROM t", allowed_tables=["t"])
        assert ok.iloc[0]["c"] == 1
    finally:
        loader.close()


def test_execute_query_whitelist_denies_subquery_and_cte(temp_db_path):
    """P1-09: 子查询 / CTE / WITH 引用白名单外的表同样被拒"""
    loader = DataLoader(temp_db_path)
    try:
        pd.DataFrame({"a": [1]}).to_sql("t", loader.conn, index=False)
        pd.DataFrame({"secret": [1]}).to_sql("hidden", loader.conn, index=False)

        with pytest.raises(PermissionError):
            loader.execute_query(
                "SELECT * FROM t WHERE a IN (SELECT secret FROM hidden)",
                allowed_tables=["t"],
            )
        with pytest.raises(PermissionError):
            loader.execute_query(
                "WITH x AS (SELECT secret FROM hidden) SELECT * FROM x",
                allowed_tables=["t"],
            )
    finally:
        loader.close()


def test_execute_query_whitelist_denies_writes_pragma_attach(temp_db_path):
    """P1-09: 查询窗口内写入/PRAGMA/ATTACH 一律拒绝，数据不被改动"""
    loader = DataLoader(temp_db_path)
    try:
        pd.DataFrame({"a": [1]}).to_sql("t", loader.conn, index=False)
        for sql in [
            "INSERT INTO t VALUES (99)",
            "UPDATE t SET a = 0",
            "DELETE FROM t",
            "PRAGMA journal_mode",
            "ATTACH DATABASE ':memory:' AS other",
        ]:
            with pytest.raises(PermissionError):
                loader.execute_query(sql, allowed_tables=["t"])

        df = loader.execute_query("SELECT a FROM t", allowed_tables=["t"])
        assert list(df["a"]) == [1]  # 数据未被改动
    finally:
        loader.close()


def test_execute_query_authorizer_removed_after_window(temp_db_path):
    """P1-09: authorizer 只在查询窗口挂载——结束后 to_sql 写入路径不受影响"""
    loader = DataLoader(temp_db_path)
    try:
        pd.DataFrame({"a": [1]}).to_sql("t", loader.conn, index=False)
        loader.execute_query("SELECT * FROM t", allowed_tables=["t"])

        # 查询窗口结束后，同一连接的写入（to_sql）依旧可用
        pd.DataFrame({"a": [2, 3]}).to_sql("t2", loader.conn, if_exists="replace", index=False)
        assert loader.execute_query("SELECT COUNT(*) AS c FROM t2").iloc[0]["c"] == 2
    finally:
        loader.close()
