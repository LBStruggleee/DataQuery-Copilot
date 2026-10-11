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
from .request_context import get_request_id

logger = logging.getLogger(__name__)

KEY_PREFIX = "dqc_"
RATE_LIMIT_PER_MINUTE = 30
DEFAULT_DAILY_QUOTA = 200
_WINDOW_SECONDS = 60
# P2-27：鉴权失败按来源 IP 的独立限流阈值（与 Key 级限流分开计数）
AUTH_FAILURE_LIMIT_PER_MINUTE = 10

_hits: dict[str, deque] = {}
_auth_failures: dict[str, deque] = {}


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
    if daily_quota < 0:
        raise ValueError(f"daily_quota 必须 >= 0， got {daily_quota}")
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
    """校验 Key：通过返回 key_hash；失败抛 AUTH_REQUIRED（日志不含 Key 明文）。

    api_keys 表由应用启动（lifespan）或 create_key 初始化（P1-06：请求路径不再执行 DDL）。
    """
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


def _read_daily_quota(conn: sqlite3.Connection, key_hash: str) -> int:
    row = conn.execute(
        "SELECT daily_quota FROM api_keys WHERE key_hash = ?", (key_hash,)
    ).fetchone()
    return row[0] if row else DEFAULT_DAILY_QUOTA


def _read_used_count(conn: sqlite3.Connection, key_hash: str, day: str) -> int:
    used = conn.execute(
        "SELECT count FROM key_usage WHERE key_hash = ? AND day = ?", (key_hash, day)
    ).fetchone()
    return used[0] if used else 0


def ensure_quota_available(db_path: str, key_hash: str) -> None:
    """SUP-01 配套的只读预检：配额已尽时提前 429，不再发起 LLM/解析等有成本的工作。

    只做快速失败；真正的扣减由 charge_quota 在成功后原子完成。
    """
    conn = sqlite3.connect(db_path)
    try:
        quota = _read_daily_quota(conn, key_hash)
        if _read_used_count(conn, key_hash, _today()) >= quota:
            raise APIError(ErrorCode.RATE_LIMITED, 429, "今日配额已用尽")
    finally:
        conn.close()


def charge_quota(db_path: str, key_hash: str) -> None:
    """日配额记账（SUP-01）：只在查询/上传成功后调用，失败路径不计费。

    P2-15：BEGIN IMMEDIATE 下「读计数 → 判额 → 累加」为原子事务，
    线程池真并发下不会像 check-then-act 两段式那样超发。
    """
    day = _today()
    conn = sqlite3.connect(db_path, isolation_level=None)  # autocommit，事务手动控制
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            quota = _read_daily_quota(conn, key_hash)
            if _read_used_count(conn, key_hash, day) >= quota:
                raise APIError(ErrorCode.RATE_LIMITED, 429, "今日配额已用尽")
            conn.execute(
                "INSERT INTO key_usage (key_hash, day, count) VALUES (?, ?, 1) "
                "ON CONFLICT(key_hash, day) DO UPDATE SET count = count + 1",
                (key_hash, day),
            )
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()


def check_rate_and_quota(db_path: str, key_hash: str) -> None:
    """限流 + 配额（组合便利函数；依赖只用 check_rate，配额由 query 入口 charge）。"""
    check_rate(key_hash)
    charge_quota(db_path, key_hash)


def _client_ip(request: Request) -> str:
    """P2-27：取来源 IP。

    反向代理（如 Render）后 request.client 是代理地址，优先取 X-Forwarded-For 首段；
    直连部署下该头可伪造，但伪造者只能给自己换新桶，不会误伤他人，可接受。
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _prune_window(window: deque, now: float) -> None:
    while window and window[0] <= now - _WINDOW_SECONDS:
        window.popleft()


def enforce_auth_failure_limit(ip: str) -> None:
    """P2-27：同 IP 鉴权失败超过阈值（默认 10 次/分钟）后直接 429，不再触发校验流程。"""
    now = time.monotonic()
    window = _auth_failures.setdefault(ip, deque())
    _prune_window(window, now)
    if len(window) >= AUTH_FAILURE_LIMIT_PER_MINUTE:
        raise APIError(ErrorCode.RATE_LIMITED, 429, "鉴权失败次数过多，请稍后重试")


def record_auth_failure(request: Request, reason: str) -> None:
    """P2-27：记录一次鉴权失败——内存桶计数 + 审计日志（含 request_id / client_ip）。"""
    ip = _client_ip(request)
    now = time.monotonic()
    window = _auth_failures.setdefault(ip, deque())
    _prune_window(window, now)
    window.append(now)
    logger.warning(
        "auth failure audit: %s", reason,
        extra={"request_id": get_request_id(request), "client_ip": ip, "detail": reason},
    )


def require_api_key(request: Request) -> str:
    """FastAPI 同步依赖（P1-06）：线程池执行，内部 sqlite 阻塞不再占用事件循环。

    api_keys/key_usage 表由应用启动（lifespan）初始化一次，请求路径不执行 DDL。
    """
    db_path = os.getenv("DB_PATH", "data/query.db")
    enforce_auth_failure_limit(_client_ip(request))
    plaintext = request.headers.get("X-API-Key", "")
    if not plaintext:
        record_auth_failure(request, "missing X-API-Key header")
        raise APIError(ErrorCode.AUTH_REQUIRED, 401, "缺少 X-API-Key 请求头")
    try:
        key_hash = verify_key(db_path, plaintext)
    except APIError:
        record_auth_failure(request, "invalid or revoked api key")
        raise
    check_rate(key_hash)
    return key_hash
