"""Phase 1: API Key 鉴权、限流、日配额。

Key 只存 sha256，明文仅创建时返回一次；比较用 hmac.compare_digest。
限流为单进程内存实现（uvicorn 单 worker 前提，多 worker 需换 Redis）。
"""

import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import time
from collections import deque
from datetime import date

from fastapi import Request

from .errors import APIError, ErrorCode

logger = logging.getLogger(__name__)

KEY_PREFIX = "dqc_"
RATE_LIMIT_PER_MINUTE = 30
DEFAULT_DAILY_QUOTA = 200
_WINDOW_SECONDS = 60

_hits: dict[str, deque] = {}


def _today() -> str:
    return date.today().isoformat()


def init_auth_tables(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS api_keys "
            "(key_hash TEXT PRIMARY KEY, key_prefix TEXT NOT NULL, name TEXT NOT NULL, "
            "revoked INTEGER NOT NULL DEFAULT 0, daily_quota INTEGER NOT NULL DEFAULT 200, "
            "created_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS key_usage "
            "(key_hash TEXT NOT NULL, day TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0, "
            "PRIMARY KEY (key_hash, day))"
        )
        conn.commit()
    finally:
        conn.close()


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def create_key(db_path: str, name: str, daily_quota: int = DEFAULT_DAILY_QUOTA) -> str:
    """签发 Key：返回明文（只显示一次），库里只存哈希。"""
    init_auth_tables(db_path)
    plaintext = KEY_PREFIX + secrets.token_urlsafe(32)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO api_keys (key_hash, key_prefix, name, revoked, daily_quota, created_at) "
            "VALUES (?, ?, ?, 0, ?, datetime('now'))",
            (_hash(plaintext), plaintext[:12], name, daily_quota),
        )
        conn.commit()
    finally:
        conn.close()
    return plaintext


def revoke_key(db_path: str, plaintext: str) -> bool:
    """吊销 Key：返回是否命中。"""
    init_auth_tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("UPDATE api_keys SET revoked = 1 WHERE key_hash = ?", (_hash(plaintext),))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def list_keys(db_path: str) -> list:
    """列出 Key（仅前缀，不含哈希/明文）。"""
    init_auth_tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT key_prefix, name, revoked, daily_quota, created_at FROM api_keys ORDER BY created_at"
        ).fetchall()
        return [
            {"prefix": r[0], "name": r[1], "revoked": bool(r[2]), "daily_quota": r[3], "created_at": r[4]}
            for r in rows
        ]
    finally:
        conn.close()


def verify_key(db_path: str, plaintext: str) -> str:
    """校验 Key：通过返回 key_hash；失败抛 AUTH_REQUIRED（日志不含 Key 明文）。"""
    init_auth_tables(db_path)
    digest = _hash(plaintext or "")
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT key_hash, revoked FROM api_keys WHERE key_hash = ?", (digest,)
        ).fetchone()
    finally:
        conn.close()
    if row is None or not hmac.compare_digest(row[0], digest) or row[1]:
        logger.warning("api key auth failed")
        raise APIError(ErrorCode.AUTH_REQUIRED, 401, "无效或已吊销的 API Key")
    return digest


def check_rate(key_hash: str) -> None:
    """滑动窗口限流（内存实现，单 worker 前提）。"""
    now = time.monotonic()
    window = _hits.setdefault(key_hash, deque())
    while window and window[0] <= now - _WINDOW_SECONDS:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_MINUTE:
        raise APIError(ErrorCode.RATE_LIMITED, 429, "请求过于频繁，请稍后重试")
    window.append(now)


def charge_quota(db_path: str, key_hash: str) -> None:
    """日配额检查与计数：只在 query 入口调用。"""
    init_auth_tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT daily_quota FROM api_keys WHERE key_hash = ?", (key_hash,)
        ).fetchone()
        quota = row[0] if row else DEFAULT_DAILY_QUOTA
        day = _today()
        used = conn.execute(
            "SELECT count FROM key_usage WHERE key_hash = ? AND day = ?", (key_hash, day)
        ).fetchone()
        used_count = used[0] if used else 0
        if used_count >= quota:
            raise APIError(ErrorCode.RATE_LIMITED, 429, "今日配额已用尽")
        conn.execute(
            "INSERT INTO key_usage (key_hash, day, count) VALUES (?, ?, 1) "
            "ON CONFLICT(key_hash, day) DO UPDATE SET count = count + 1",
            (key_hash, day),
        )
        conn.commit()
    finally:
        conn.close()


def check_rate_and_quota(db_path: str, key_hash: str) -> None:
    """限流 + 配额（组合便利函数；依赖只用 check_rate，配额由 query 入口 charge）。"""
    check_rate(key_hash)
    charge_quota(db_path, key_hash)


async def require_api_key(request: Request) -> str:
    """FastAPI dependency：读 X-API-Key，依次过校验/限流，返回 key_hash（配额由 query 入口单独计）。"""
    init_auth_tables(os.getenv("DB_PATH", "data/query.db"))
    plaintext = request.headers.get("X-API-Key", "")
    if not plaintext:
        raise APIError(ErrorCode.AUTH_REQUIRED, 401, "缺少 X-API-Key 请求头")
    db_path = os.getenv("DB_PATH", "data/query.db")
    key_hash = verify_key(db_path, plaintext)
    check_rate(key_hash)
    return key_hash
