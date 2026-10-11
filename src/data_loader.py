"""
数据接入层 - Data Loader

负责将 CSV/Excel 数据导入 SQLite，自动推断数据类型，
并提供表结构信息供 LLM 生成 SQL 时使用。
"""

import os
import re
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Optional, Union

import pandas as pd


class DataLoader:
    """数据接入层：文件 -> SQLite

    execute_query 自带资源边界：
    - 行数上限（max_rows，默认 10000）：fetchmany 分批物化，超出即截断；
    - 执行超时（query_timeout，默认 10s）：set_progress_handler 超时中断长查询；
    - 表白名单（allowed_tables，P1-09）：传入时用 set_authorizer 限制本次查询
      仅可 SELECT 白名单表（及 sqlite_master），LLM 生成 SQL 引用其他表/对象时
      返回明确错误。authorizer 只在查询窗口挂载，结束后移除，不影响 to_sql 写入。
    """

    # 表名白名单：与 API 层（api/services.py）的标识符正则保持一致
    _TABLE_NAME_PATTERN = r"[A-Za-z_][A-Za-z0-9_]*"

    # SQLite authorizer 行为码（Python 3.11+ 内置同名常量；此处带回退值保证兼容）
    _SQLITE_OK = getattr(sqlite3, "SQLITE_OK", 0)
    _SQLITE_DENY = getattr(sqlite3, "SQLITE_DENY", 1)
    _SQLITE_SELECT = getattr(sqlite3, "SQLITE_SELECT", 21)
    _SQLITE_READ = getattr(sqlite3, "SQLITE_READ", 20)
    _SQLITE_FUNCTION = getattr(sqlite3, "SQLITE_FUNCTION", 31)
    _SQLITE_RECURSIVE = getattr(sqlite3, "SQLITE_RECURSIVE", 33)

    def __init__(
        self,
        db_path: str = "data/query.db",
        max_rows: int = 10000,
        query_timeout: float = 10.0,
    ):
        if max_rows < 1:
            raise ValueError(f"max_rows 必须为正整数，当前为: {max_rows}")
        if query_timeout <= 0:
            raise ValueError(f"query_timeout 必须为正数，当前为: {query_timeout}")
        self.db_path = db_path
        self.max_rows = max_rows
        self.query_timeout = query_timeout
        # 确保目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")  # 提升并发性能

    @classmethod
    def validate_table_name(cls, table_name: str) -> str:
        """校验表名为安全标识符（统一入口，防 f-string 拼接注入）

        CLI --table 与直接使用本库的调用方都经过这里，
        与 API 层已有的正则白名单保持同一规则。
        """
        if not isinstance(table_name, str) or not re.fullmatch(
            cls._TABLE_NAME_PATTERN, table_name
        ):
            raise ValueError(
                f"非法表名（仅允许字母/数字/下划线，且不以数字开头）: {table_name!r}"
            )
        return table_name

    def load_csv(self, filepath: str, table_name: str = "orders") -> dict:
        """
        从 CSV 文件导入数据到 SQLite

        Args:
            filepath: CSV 文件路径
            table_name: 目标表名

        Returns:
            包含表信息的字典（行数、列名、数据类型）
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")

        self.validate_table_name(table_name)

        # 读取 CSV
        df = pd.read_csv(filepath)

        # 自动推断并优化数据类型
        df = self._optimize_dtypes(df)

        # 写入 SQLite
        df.to_sql(table_name, self.conn, if_exists="replace", index=False)

        # 返回表信息
        table_info = self.get_table_info(table_name)
        table_info["row_count"] = len(df)
        return table_info

    def load_excel(
        self,
        filepath: str,
        table_name: str = "orders",
        sheet_name: Union[str, int] = 0,
    ) -> dict:
        """
        从 Excel 文件导入数据到 SQLite

        Args:
            filepath: Excel 文件路径
            table_name: 目标表名
            sheet_name: 工作表名或序号，默认导入第一个工作表

        Returns:
            包含表信息的字典
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")

        self.validate_table_name(table_name)

        # sheet_name 必须取单表（默认 0）；传 None 会让 pandas 返回 dict 导致崩溃
        df = pd.read_excel(filepath, sheet_name=sheet_name)
        if isinstance(df, dict):
            # 兜底：显式取第一个工作表
            df = next(iter(df.values()))

        df = self._optimize_dtypes(df)
        df.to_sql(table_name, self.conn, if_exists="replace", index=False)

        table_info = self.get_table_info(table_name)
        table_info["row_count"] = len(df)
        return table_info

    def _optimize_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        自动推断并优化数据类型
        - 尝试将字符串列转为日期
        - 尝试将字符串列转为数值
        - 优化内存占用

        注：pandas 2.x 已弃用 errors="ignore"，改为 errors="raise" + try/except，
        转换失败时保持原列不变（行为与原先一致，但不再产生 FutureWarning）。
        """
        for col in df.columns:
            # 尝试转日期
            if df[col].dtype == "object":
                try:
                    df[col] = pd.to_datetime(df[col], errors="raise")
                except (ValueError, TypeError):
                    pass

            # 尝试转数值
            if df[col].dtype == "object":
                try:
                    df[col] = pd.to_numeric(df[col], errors="raise")
                except (ValueError, TypeError):
                    pass

        return df

    def get_table_info(self, table_name: str = "orders") -> dict:
        """
        获取表结构信息，供 LLM 生成 SQL 时作为上下文

        Returns:
            {
                "table_name": "orders",
                "columns": [
                    {"name": "order_id", "type": "INTEGER"},
                    {"name": "amount", "type": "REAL"},
                    ...
                ]
            }
        """
        info = self.validate_table_name(table_name)
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({info})")
        columns = cursor.fetchall()

        col_info = []
        for col in columns:
            col_info.append({
                "name": col[1],
                "type": col[2],
            })

        return {
            "table_name": table_name,
            "columns": col_info,
        }

    def get_schema_text(self, table_name: str = "orders") -> str:
        """
        获取表结构的文本描述，直接嵌入 prompt

        格式:
        表名: orders
        列:
        - order_id (INTEGER)
        - order_date (TEXT)
        - category (TEXT)
        - amount (REAL)
        """
        info = self.get_table_info(table_name)
        lines = [f"表名: {info['table_name']}", "列:"]
        for col in info["columns"]:
            lines.append(f"  - {col['name']} ({col['type']})")
        return "\n".join(lines)

    def execute_query(
        self,
        sql: str,
        max_rows: Optional[int] = None,
        allowed_tables: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        """
        执行 SQL 查询，返回 DataFrame

        资源边界（P1-05）：
        - 行数上限：用 cursor + fetchmany 只物化前 max_rows 行（额外多取 1 行用于
          判断是否截断），避免大笛卡尔积全量物化耗尽内存；
        - 超时中断：set_progress_handler 在虚拟机指令间隙检查 deadline，
          超时返回非零值使 SQLite 中断执行（如无终止的 WITH RECURSIVE）。

        表白名单（P1-09）：传入 allowed_tables 时挂载 sqlite3 set_authorizer，
        仅允许对白名单表（及 sqlite_master）做 SELECT 读取；引用其他表、
        写入、PRAGMA、ATTACH 等一律拒绝并抛出含被拒对象的明确错误。
        authorizer 只在本次查询窗口挂载，结束后移除，不影响 to_sql 写入路径。
        """
        limit = self.max_rows if max_rows is None else max_rows
        if limit < 1:
            raise ValueError(f"max_rows 必须为正整数，当前为: {limit}")

        # P1-09：查询窗口表白名单（LLM 生成 SQL 的执行层防护）
        allowed: Optional[set] = None
        denied_objects: list = []
        if allowed_tables is not None:
            allowed = {str(t).lower() for t in allowed_tables}
            allowed.update({"sqlite_master", "sqlite_temp_master"})

            def _read_only_authorizer(action, arg1, arg2, db_name, source):
                # 语句级 SELECT / 标量函数 / 递归 CTE 放行；
                # 列级 READ 仅放行白名单表；其余动作（写入/DDL/PRAGMA/ATTACH/
                # 加载扩展等）拒绝并记录被拒对象，用于生成明确错误。
                if action in (self._SQLITE_SELECT, self._SQLITE_FUNCTION,
                              self._SQLITE_RECURSIVE):
                    return self._SQLITE_OK
                if action == self._SQLITE_READ:
                    if arg1 is None or str(arg1).lower() in allowed:
                        return self._SQLITE_OK
                    denied_objects.append(str(arg1))
                    return self._SQLITE_DENY
                denied_objects.append(str(arg1) if arg1 else "<statement>")
                return self._SQLITE_DENY

        deadline = time.monotonic() + self.query_timeout

        def _interrupt_on_timeout() -> int:
            # 返回非零值 -> SQLite 以 SQLITE_INTERRUPT 中断当前语句
            return 1 if time.monotonic() > deadline else 0

        self.conn.set_authorizer(_read_only_authorizer if allowed is not None else None)
        self.conn.set_progress_handler(_interrupt_on_timeout, 100_000)
        cursor = self.conn.cursor()
        try:
            cursor.execute(sql)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows = cursor.fetchmany(limit + 1) if columns else []
        except sqlite3.DatabaseError as e:
            if denied_objects:
                raise PermissionError(
                    f"SQL 被拒绝：引用了表白名单之外的数据库对象 {sorted(set(denied_objects))}，"
                    f"本次查询仅允许访问表 {sorted(allowed)}"
                ) from e
            if isinstance(e, sqlite3.OperationalError) and "interrupted" in str(e).lower():
                raise TimeoutError(
                    f"SQL 执行超过 {self.query_timeout}s，已被中断"
                ) from e
            raise
        finally:
            cursor.close()
            self.conn.set_authorizer(None)  # 查询窗口结束即移除，写入路径不受影响
            self.conn.set_progress_handler(None, 0)

        truncated = len(rows) > limit
        if truncated:
            rows = rows[:limit]

        return pd.DataFrame.from_records(rows, columns=columns)

    def close(self):
        """关闭数据库连接"""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
