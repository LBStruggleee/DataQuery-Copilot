"""
数据接入层 - Data Loader

负责将 CSV/Excel 数据导入 SQLite，自动推断数据类型，
并提供表结构信息供 LLM 生成 SQL 时使用。
"""

import os
import sqlite3
import pandas as pd
from pathlib import Path
from typing import Optional


class DataLoader:
    """数据接入层：文件 -> SQLite"""

    def __init__(self, db_path: str = "data/query.db"):
        self.db_path = db_path
        # 确保目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")  # 提升并发性能

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

    def load_excel(self, filepath: str, table_name: str = "orders", sheet_name: Optional[str] = None) -> dict:
        """
        从 Excel 文件导入数据到 SQLite

        Args:
            filepath: Excel 文件路径
            table_name: 目标表名
            sheet_name: 工作表名，默认第一个

        Returns:
            包含表信息的字典
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")

        df = pd.read_excel(filepath, sheet_name=sheet_name)
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
        """
        for col in df.columns:
            # 尝试转日期
            if df[col].dtype == "object":
                try:
                    df[col] = pd.to_datetime(df[col], errors="ignore")
                except Exception:
                    pass

            # 尝试转数值
            if df[col].dtype == "object":
                try:
                    df[col] = pd.to_numeric(df[col], errors="ignore")
                except Exception:
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
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
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

    def execute_query(self, sql: str) -> pd.DataFrame:
        """执行 SQL 查询，返回 DataFrame"""
        return pd.read_sql_query(sql, self.conn)

    def close(self):
        """关闭数据库连接"""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
