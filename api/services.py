"""Service layer that adapts the existing Python modules for HTTP use."""

import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.data_cleaner import DataCleaner
from src.data_loader import DataLoader
from src.query_engine import QueryEngine
from src.visualizer import Visualizer

from .errors import APIError, ErrorCode

V1_MAX_ROWS = 100


class DataQueryService:
    def __init__(self, db_path: str, table_name: str = "orders"):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
            raise ValueError(f"无效的数据表名: {table_name}")
        self.db_path = db_path
        self.table_name = table_name

    def health(self) -> dict:
        database_ready = self._database_ready()
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        llm_configured = bool(api_key and api_key != "your_api_key_here")
        return {
            "status": "ok" if database_ready and llm_configured else "degraded",
            "database_ready": database_ready,
            "llm_configured": llm_configured,
        }

    def schema(self) -> dict:
        with DataLoader(self.db_path) as loader:
            info = loader.get_table_info(self.table_name)
        if not info["columns"]:
            raise ValueError(f"数据表不存在: {self.table_name}")
        return info

    def quality(self) -> dict:
        with DataLoader(self.db_path) as loader:
            df = loader.execute_query(f'SELECT * FROM "{self.table_name}" LIMIT 10000')
        report = DataCleaner().quality_report(df)
        return {"table_name": self.table_name, **report}

    def query(self, question: str, clean_result: bool, max_retries: int) -> dict:
        with QueryEngine(
            db_path=self.db_path,
            table_name=self.table_name,
            enable_cache=False,
        ) as engine:
            result = engine.ask(
                question,
                clean_result=clean_result,
                max_retries=max_retries,
            )

        df = result["data"]
        columns = list(df.columns) if df is not None else []
        rows = self._records(df) if df is not None else []
        chart_hint = Visualizer.detect_chart_type(df) if df is not None else "table"

        return {
            "question": result["question"],
            "sql": result["sql"],
            "columns": columns,
            "rows": rows,
            "row_count": result["row_count"],
            "chart_hint": chart_hint,
            "execution_time": result["execution_time"],
            "valid": result["valid"],
            "retries": result["retries"],
            "from_cache": result["from_cache"],
            "error": result["error"],
        }

    def _database_ready(self) -> bool:
        if not Path(self.db_path).is_file():
            return False
        try:
            return bool(self.schema()["columns"])
        except Exception:
            return False

    def query_page(self, question: str, clean_result: bool, max_retries: int, page: int, page_size: int) -> dict:
        """v1 分页查询：失败抛 APIError，超限截断。"""
        with QueryEngine(
            db_path=self.db_path,
            table_name=self.table_name,
            enable_cache=False,
        ) as engine:
            result = engine.ask(question, clean_result=clean_result, max_retries=max_retries)

        if result["error"]:
            raise self._map_engine_error(result["error"])

        df = result["data"]
        total = len(df) if df is not None else 0
        truncated = total > V1_MAX_ROWS
        frame = df.iloc[:V1_MAX_ROWS] if df is not None else None
        rows = self._records(frame) if frame is not None else []
        visible_count = len(frame) if frame is not None else 0
        total_pages = max(1, -(-visible_count // page_size))
        safe_page = min(max(1, page), total_pages)
        page_rows = rows[(safe_page - 1) * page_size:safe_page * page_size]
        return {
            "question": result["question"],
            "sql": result["sql"],
            "columns": list(df.columns) if df is not None else [],
            "rows": page_rows,
            "row_count": visible_count,
            "page": safe_page,
            "page_size": page_size,
            "total_pages": total_pages,
            "truncated": truncated,
            "chart_hint": Visualizer.detect_chart_type(df) if df is not None else "table",
            "execution_time": result["execution_time"],
            "valid": result["valid"],
            "retries": result["retries"],
            "from_cache": result["from_cache"],
        }

    @staticmethod
    def _map_engine_error(error: str) -> APIError:
        if "安全校验" in error:
            return APIError(ErrorCode.SQL_REJECTED, 422, error)
        if "no such table" in error:
            return APIError(ErrorCode.TABLE_NOT_FOUND, 404, error)
        if "SQL 生成失败" in error or "自动修正失败" in error:
            return APIError(ErrorCode.SERVICE_UNAVAILABLE, 503, error)
        return APIError(ErrorCode.QUERY_FAILED, 500, error)

    @classmethod
    def _records(cls, df: pd.DataFrame) -> list[dict[str, Any]]:
        return [
            {column: cls._json_value(value) for column, value in row.items()}
            for row in df.to_dict(orient="records")
        ]

    @staticmethod
    def _json_value(value: Any) -> Any:
        if value is None or pd.isna(value):
            return None
        if isinstance(value, (datetime, date, pd.Timestamp)):
            return value.isoformat()
        if isinstance(value, np.generic):
            return value.item()
        return value
