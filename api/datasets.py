"""Phase 2: 数据集注册表（上传入库、多数据集作用域）。

表名统一生成 `ds_<slug>_<shortid>`（纯 ASCII），杜绝注入；原始文件名只做展示。
"""

import io
import logging
import os
import re
import secrets
import sqlite3
from datetime import datetime

import pandas as pd

from .errors import APIError, ErrorCode

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
# P1-10：数据集数量上限（超出返回 429），限制单库表数量与磁盘膨胀
MAX_DATASETS = 50
# P2-20：移除 .xls —— 解析所需的 xlrd 未在 requirements.txt/pyproject 中声明，放行必然 422
_ALLOWED_EXTS = (".csv", ".xlsx")


def init_dataset_tables(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS datasets "
            "(id TEXT PRIMARY KEY, name TEXT NOT NULL, table_name TEXT NOT NULL, "
            "rows INTEGER NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()


def _slugify(filename: str) -> str:
    stem = os.path.splitext(os.path.basename(filename))[0]
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", stem).strip("_")[:24]
    return slug or "data"


def _read_csv_fallback(content: bytes) -> pd.DataFrame:
    """P2-21：CSV 编码回退链 utf-8-sig → gbk（中文 Excel 导出的 CSV 常见 GBK）。

    仅编码错误触发回退；其余解析异常原样抛给调用方转 422。
    """
    try:
        return pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(content), encoding="gbk")


def register_upload(db_path: str, filename: str, content: bytes) -> dict:
    """校验并入库上传文件，返回数据集信息；非法输入抛 UPLOAD_REJECTED(422)（P2-19）。"""
    init_dataset_tables(db_path)
    if re.search(r"[\\/]|\.\.", filename):
        raise APIError(ErrorCode.UPLOAD_REJECTED, 422, "非法文件名")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTS:
        raise APIError(ErrorCode.UPLOAD_REJECTED, 422, f"仅支持 CSV/Excel(.xlsx) 文件：{filename}")
    if len(content) > MAX_UPLOAD_BYTES:
        raise APIError(ErrorCode.UPLOAD_REJECTED, 422, "文件超过 50MB 上限")

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
    finally:
        conn.close()
    if count >= MAX_DATASETS:
        raise APIError(
            ErrorCode.RATE_LIMITED, 429,
            f"数据集数量已达上限（{MAX_DATASETS} 个），请先清理旧数据集",
        )

    try:
        if ext == ".csv":
            df = _read_csv_fallback(content)
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as error:
        raise APIError(ErrorCode.UPLOAD_REJECTED, 422, f"文件解析失败：{error}") from error

    table_name = f"ds_{_slugify(filename)}_{secrets.token_hex(3)}"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
        raise APIError(ErrorCode.INVALID_QUESTION, 422, "无法生成合法表名")

    conn = sqlite3.connect(db_path)
    try:
        df.to_sql(table_name, conn, if_exists="replace", index=False)
    finally:
        conn.close()

    dataset_id = secrets.token_hex(4)
    created_at = datetime.now().isoformat(timespec="seconds")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO datasets (id, name, table_name, rows, created_at) VALUES (?, ?, ?, ?, ?)",
            (dataset_id, os.path.basename(filename), table_name, len(df), created_at),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": dataset_id, "name": os.path.basename(filename),
            "table_name": table_name, "rows": len(df), "created_at": created_at}


def remove_dataset(db_path: str, dataset_id: str, table_name: str) -> None:
    """尽力撤销一次上传注册（P1-10：上传成功但配额记账失败的竞态回滚）。

    table_name 由 register_upload 服务端生成且通过白名单校验，非用户输入。
    """
    conn = sqlite3.connect(db_path)
    try:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
            conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        conn.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
        conn.commit()
    except sqlite3.Error:
        logger.warning("撤销数据集注册失败: %s", dataset_id, exc_info=True)
    finally:
        conn.close()


def list_datasets(db_path: str) -> list:
    init_dataset_tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, name, table_name, rows, created_at FROM datasets ORDER BY created_at"
        ).fetchall()
        return [{"id": r[0], "name": r[1], "table_name": r[2], "rows": r[3], "created_at": r[4]} for r in rows]
    finally:
        conn.close()


def resolve_table(db_path: str, dataset_id) -> str:
    """dataset=None → 默认 orders 表；未知 id 抛 TABLE_NOT_FOUND(404)。"""
    if not dataset_id:
        return "orders"
    init_dataset_tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT table_name FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise APIError(ErrorCode.TABLE_NOT_FOUND, 404, f"数据集不存在：{dataset_id}")
    return row[0]
