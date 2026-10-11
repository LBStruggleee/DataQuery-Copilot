"""src/cli.py 冒烟测试（P2-41）。

CLI 模块此前 361 行零测试。本文件覆盖：
- _is_valid_query 输入校验逻辑（长度/换行/误粘贴工具输出/过短）；
- cmd_load / cmd_schema / cmd_report 基本命令路径（直接调用，不触网）；
- argparse 入口（subprocess 验证 --help 与 schema 子命令）。
"""

import argparse
import os
import subprocess
import sys

import pandas as pd
import pytest

import src.cli as cli

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def cli_db(tmp_path, monkeypatch):
    """建好 orders 表的临时库，并把 cli.DB_PATH 指向它"""
    from src.data_loader import DataLoader

    db = str(tmp_path / "cli.db")
    loader = DataLoader(db)
    pd.DataFrame({"order_id": [1, 2], "amount": [10.0, 20.0]}).to_sql(
        "orders", loader.conn, index=False
    )
    loader.close()
    monkeypatch.setattr(cli, "DB_PATH", db)
    return db


# ── _is_valid_query 输入校验 ─────────────────────────────────────────

class TestIsValidQuery:

    def test_normal_question_passes(self):
        valid, reason = cli._is_valid_query("上个月销售额最高的品类是什么")
        assert valid is True
        assert reason == ""

    def test_rejects_too_long_input(self):
        valid, reason = cli._is_valid_query("订单" * 300)  # 600 字符
        assert valid is False
        assert "输入过长" in reason

    def test_rejects_too_many_newlines(self):
        valid, reason = cli._is_valid_query("行\n" * 8)
        assert valid is False
        assert "换行" in reason

    @pytest.mark.parametrize("pasted", [
        "SQL 安全校验未通过（仅允许 SELECT 语句）...",
        "SQL 生成失败: bad key",
        "SQL 执行失败（已重试 2 次）: no such column",
        "[DEBUG] LLM 原始返回:\n```sql",
        "执行时间: 0.23s",
        "LLM 生成的 SQL: SELECT 1",
    ])
    def test_rejects_pasted_tool_output(self, pasted):
        """误粘贴工具自身错误输出被拦截"""
        valid, reason = cli._is_valid_query(pasted)
        assert valid is False
        assert "工具的错误输出" in reason

    def test_rejects_too_short(self):
        valid, reason = cli._is_valid_query("好")
        assert valid is False
        assert "太短" in reason


# ── cmd_* 基本命令路径（直接调用） ───────────────────────────────────

class TestCmdSmoke:

    def test_cmd_schema_prints_table_structure(self, cli_db, capsys):
        cli.cmd_schema(argparse.Namespace(table="orders"))
        out = capsys.readouterr().out
        assert "orders" in out
        assert "order_id" in out
        assert "amount" in out

    def test_cmd_schema_rejects_invalid_table_name(self, cli_db):
        """CLI --table 与库层共用同一表名白名单"""
        with pytest.raises(ValueError):
            cli.cmd_schema(argparse.Namespace(table="orders; DROP TABLE orders"))

    def test_cmd_load_csv(self, tmp_path, cli_db, capsys, sample_df):
        csv_path = tmp_path / "in.csv"
        sample_df.to_csv(csv_path, index=False)
        cli.cmd_load(argparse.Namespace(file=str(csv_path), table="orders"))
        out = capsys.readouterr().out
        assert "加载完成" in out
        assert "orders" in out

    def test_cmd_load_rejects_unsupported_extension(self, tmp_path, cli_db, capsys):
        bogus = tmp_path / "data.txt"
        bogus.write_text("x", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            cli.cmd_load(argparse.Namespace(file=str(bogus), table="orders"))
        assert exc_info.value.code == 1
        assert "仅支持 CSV 和 Excel" in capsys.readouterr().out

    def test_cmd_report_runs_quality_check(self, cli_db, capsys):
        cli.cmd_report(argparse.Namespace())
        out = capsys.readouterr().out
        assert out.strip() != ""


# ── argparse 入口（subprocess 冒烟） ─────────────────────────────────

def test_cli_entry_help_via_subprocess():
    """argparse 入口可用：--help 正常退出且列出子命令"""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "--help"],
        capture_output=True, text=True, cwd=REPO_ROOT, check=True,
    )
    assert "interactive" in result.stdout
    assert "batch" in result.stdout


def test_cli_entry_schema_via_subprocess(tmp_path):
    """schema 子命令读取 DB_PATH 环境变量指定的库"""
    from src.data_loader import DataLoader

    db = str(tmp_path / "entry.db")
    loader = DataLoader(db)
    pd.DataFrame({"order_id": [1]}).to_sql("orders", loader.conn, index=False)
    loader.close()

    env = dict(os.environ, DB_PATH=db)
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "schema", "--table", "orders"],
        capture_output=True, text=True, cwd=REPO_ROOT, check=True, env=env,
    )
    assert "orders" in result.stdout
    assert "order_id" in result.stdout


def test_main_without_command_prints_help(capsys, monkeypatch):
    """不带子命令调用 main() 打印帮助且正常返回（不抛 SystemExit）"""
    monkeypatch.setattr(sys, "argv", ["cli.py"])
    cli.main()
    out = capsys.readouterr().out
    assert "interactive" in out
