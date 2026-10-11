"""Phase 1: API Key 鉴权、限流、配额。"""

import inspect
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest


def test_auth_error_codes_are_stable():
    from api.errors import ErrorCode

    assert ErrorCode.AUTH_REQUIRED.value == "AUTH_REQUIRED"
    assert ErrorCode.RATE_LIMITED.value == "RATE_LIMITED"


def _fresh_db(tmp_path):
    from api.auth import init_auth_tables

    db = str(tmp_path / "auth.db")
    init_auth_tables(db)
    return db


def test_create_and_verify_key(tmp_path):
    from api.auth import create_key, verify_key

    db = _fresh_db(tmp_path)
    plain = create_key(db, "ci")
    assert plain.startswith("dqc_")
    key_hash = verify_key(db, plain)
    assert isinstance(key_hash, str) and len(key_hash) == 64


def test_create_key_rejects_negative_quota(tmp_path):
    from api.auth import create_key

    db = _fresh_db(tmp_path)
    with pytest.raises(ValueError, match="daily_quota"):
        create_key(db, "ci", daily_quota=-5)


def test_unknown_and_revoked_keys_rejected(tmp_path):
    from api.auth import create_key, revoke_key, verify_key
    from api.errors import APIError

    db = _fresh_db(tmp_path)
    with pytest.raises(APIError) as exc_info:
        verify_key(db, "dqc_nonexistent")
    assert exc_info.value.code.value == "AUTH_REQUIRED"
    assert exc_info.value.status == 401

    plain = create_key(db, "ci")
    revoke_key(db, plain)
    with pytest.raises(APIError) as exc_info:
        verify_key(db, plain)
    assert exc_info.value.code.value == "AUTH_REQUIRED"


def test_rate_limit_trips(monkeypatch, tmp_path):
    import api.auth as auth_module
    from api.auth import check_rate_and_quota, create_key, verify_key
    from api.errors import APIError

    monkeypatch.setattr(auth_module, "RATE_LIMIT_PER_MINUTE", 3)
    db = _fresh_db(tmp_path)
    key_hash = verify_key(db, create_key(db, "ci"))
    check_rate_and_quota(db, key_hash)
    check_rate_and_quota(db, key_hash)
    check_rate_and_quota(db, key_hash)
    with pytest.raises(APIError) as exc_info:
        check_rate_and_quota(db, key_hash)
    assert exc_info.value.code.value == "RATE_LIMITED"
    assert exc_info.value.status == 429


def test_quota_exhausted_and_resets_next_day(monkeypatch, tmp_path):
    import api.auth as auth_module
    from api.auth import check_rate_and_quota, create_key, verify_key
    from api.errors import APIError

    db = _fresh_db(tmp_path)
    key_hash = verify_key(db, create_key(db, "ci", daily_quota=1))
    check_rate_and_quota(db, key_hash)
    with pytest.raises(APIError) as exc_info:
        check_rate_and_quota(db, key_hash)
    assert exc_info.value.code.value == "RATE_LIMITED"

    monkeypatch.setattr(auth_module, "_today", lambda: "2099-01-02")
    check_rate_and_quota(db, key_hash)  # 新的一天，配额重置，不抛异常


def test_key_material_never_logged(tmp_path, caplog):
    from api.auth import create_key, verify_key
    from api.errors import APIError

    db = _fresh_db(tmp_path)
    plain = create_key(db, "ci")
    with caplog.at_level(logging.WARNING, logger="api.auth"):
        try:
            verify_key(db, "dqc_wrongkey")
        except APIError:
            pass
        verify_key(db, plain)
    assert plain not in caplog.text


@pytest.fixture
def authed_client(api_test_client):
    """P2-40：样板收敛到 conftest（无预置请求头，测试可分别带/不带 Key 请求）。"""
    client = api_test_client(with_header=False)
    with client:
        yield client


def test_v1_query_requires_key(authed_client):
    response = authed_client.post("/api/v1/query", json={"question": "有效问题"})
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "AUTH_REQUIRED"
    assert body["data"] is None
    assert body["request_id"].startswith("req_")


def test_valid_key_passes(authed_client):
    response = authed_client.post(
        "/api/v1/query", json={"question": "有效问题"}, headers={"X-API-Key": authed_client.key}
    )
    assert response.status_code == 200
    assert response.json()["code"] == "OK"


def test_quota_burned_only_by_query(api_test_client):
    """终审 Important 1：health 等读接口不得烧配额，只有 query 计数。"""
    client = api_test_client(key_kwargs={"daily_quota": 1}, with_header=False)
    headers = {"X-API-Key": client.key}
    with client:
        assert client.get("/api/v1/health", headers=headers).status_code == 200
        assert client.get("/api/v1/health", headers=headers).status_code == 200
        ok = client.post("/api/v1/query", headers=headers, json={"question": "有效问题"})
        assert ok.status_code == 200
        over = client.post("/api/v1/query", headers=headers, json={"question": "有效问题"})
        assert over.status_code == 429
        assert over.json()["code"] == "RATE_LIMITED"


def test_manage_keys_cli(tmp_path):
    import subprocess
    import sys

    db = str(tmp_path / "t.db")
    created = subprocess.run(
        [sys.executable, "scripts/manage_keys.py", "--db", db, "create", "--name", "ci"],
        capture_output=True, text=True, cwd="D:/DataQuery-Copilot",
    )
    assert created.returncode == 0
    key = created.stdout.strip().splitlines()[-1]
    assert key.startswith("dqc_")

    listed = subprocess.run(
        [sys.executable, "scripts/manage_keys.py", "--db", db, "list"],
        capture_output=True, text=True, cwd="D:/DataQuery-Copilot",
    )
    assert listed.returncode == 0
    assert "ci" in listed.stdout

    revoked = subprocess.run(
        [sys.executable, "scripts/manage_keys.py", "--db", db, "revoke", key],
        capture_output=True, text=True, cwd="D:/DataQuery-Copilot",
    )
    assert revoked.returncode == 0


def test_manage_keys_revoke_via_stdin(tmp_path):
    """P2-30：revoke 支持 --stdin 读取明文 Key，避免进入 shell 历史/进程列表。"""
    import subprocess
    import sys

    from api.auth import verify_key
    from api.errors import APIError

    db = str(tmp_path / "t.db")
    created = subprocess.run(
        [sys.executable, "scripts/manage_keys.py", "--db", db, "create", "--name", "ci"],
        capture_output=True, text=True, cwd="D:/DataQuery-Copilot",
    )
    assert created.returncode == 0
    key = created.stdout.strip().splitlines()[-1]
    assert key.startswith("dqc_")

    revoked = subprocess.run(
        [sys.executable, "scripts/manage_keys.py", "--db", db, "revoke", "--stdin"],
        input=key + "\n", capture_output=True, text=True, cwd="D:/DataQuery-Copilot",
    )
    assert revoked.returncode == 0, revoked.stderr
    assert "revoked" in revoked.stdout

    # 吊销确实生效
    with pytest.raises(APIError):
        verify_key(db, key)


def test_manage_keys_revoke_stdin_conflicts_with_argv_key(tmp_path):
    """P2-30：--stdin 与位置参数 key 二选一，同时给出报错退出。"""
    import subprocess
    import sys

    db = str(tmp_path / "t.db")
    result = subprocess.run(
        [sys.executable, "scripts/manage_keys.py", "--db", db, "revoke", "dqc_somekey", "--stdin"],
        input="dqc_otherkey\n", capture_output=True, text=True, cwd="D:/DataQuery-Copilot",
    )
    assert result.returncode != 0
    assert "二选一" in result.stderr


def test_manage_keys_revoke_requires_key(tmp_path):
    """P2-30：既无位置参数也无 --stdin 时报错退出，不再 AttributeError。"""
    import subprocess
    import sys

    db = str(tmp_path / "t.db")
    result = subprocess.run(
        [sys.executable, "scripts/manage_keys.py", "--db", db, "revoke"],
        capture_output=True, text=True, cwd="D:/DataQuery-Copilot",
    )
    assert result.returncode != 0
    assert "明文 Key" in result.stderr


# ── P1-06：鉴权依赖去事件循环阻塞、DDL 移到启动期 ──────────────────

def test_require_api_key_is_sync_dependency():
    """require_api_key 必须是同步 def——FastAPI 自动进线程池，sqlite 阻塞不占事件循环。"""
    from api.auth import require_api_key

    assert not inspect.iscoroutinefunction(require_api_key)


def test_auth_tables_initialized_once_on_startup(tmp_path, monkeypatch):
    """lifespan 统一初始化鉴权表，请求路径（verify_key/charge_quota）不再执行 DDL。"""
    from fastapi.testclient import TestClient

    from api.main import create_app

    db = str(tmp_path / "t.db")
    monkeypatch.setenv("DB_PATH", db)
    with TestClient(create_app()):  # with 触发 lifespan
        conn = sqlite3.connect(db)
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
    assert {"api_keys", "key_usage"} <= tables


# ── P2-15：配额记账原子化（BEGIN IMMEDIATE），并发不超发 ─────────────

def test_charge_quota_atomic_under_concurrency(tmp_path):
    from api.auth import _today, charge_quota, create_key, verify_key
    from api.errors import APIError

    db = str(tmp_path / "t.db")
    key_hash = verify_key(db, create_key(db, "ci", daily_quota=5))

    results = []

    def worker(_):
        try:
            charge_quota(db, key_hash)
            results.append("ok")
        except APIError:
            results.append("rejected")

    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(worker, range(40)))

    assert results.count("ok") == 5
    assert results.count("rejected") == 35

    conn = sqlite3.connect(db)
    try:
        count = conn.execute(
            "SELECT count FROM key_usage WHERE key_hash = ? AND day = ?", (key_hash, _today())
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 5


# ── SUP-01：配额在查询成功后记账，失败不扣 ──────────────────────────

def test_failed_query_does_not_charge_quota(api_test_client):
    """SUP-01：查询失败（SQL_REJECTED 等）不消耗当日配额。"""
    from api.errors import APIError, ErrorCode
    from tests.conftest import FakeQueryService

    calls = []

    class RejectedService(FakeQueryService):
        def query_page(self, *args, **kwargs):
            calls.append(1)
            raise APIError(ErrorCode.SQL_REJECTED, 422, "SQL 安全校验未通过")

    client = api_test_client(service_cls=RejectedService, with_header=False)
    headers = {"X-API-Key": client.key}
    with client:
        for _ in range(3):
            response = client.post("/api/v1/query", headers=headers, json={"question": "有效问题"})
            assert response.status_code == 422

    assert len(calls) == 3
    conn = sqlite3.connect(client.db)
    try:
        charged = conn.execute("SELECT COALESCE(SUM(count), 0) FROM key_usage").fetchone()[0]
    finally:
        conn.close()
    assert charged == 0  # 三次失败查询，配额分文未扣


def test_exhausted_quota_fails_fast_before_service(api_test_client):
    """SUP-01 配套：配额已尽时提前 429，不再调用 service（不白付 LLM 成本）。"""
    from tests.conftest import FakeQueryService

    class NeverCalledService(FakeQueryService):
        def query_page(self, *args, **kwargs):
            raise AssertionError("query_page must not run when quota is exhausted")

    client = api_test_client(service_cls=NeverCalledService, key_kwargs={"daily_quota": 0})
    with client:
        response = client.post("/api/v1/query", json={"question": "有效问题"})

    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"


def test_quota_charged_after_successful_query(api_test_client):
    """SUP-01：成功查询记账 1 次；health 等读接口依旧不烧配额。"""
    client = api_test_client(key_kwargs={"daily_quota": 2}, with_header=False)
    headers = {"X-API-Key": client.key}
    with client:
        assert client.get("/api/v1/health", headers=headers).status_code == 200
        assert client.post("/api/v1/query", headers=headers, json={"question": "q"}).status_code == 200
        assert client.post("/api/v1/query", headers=headers, json={"question": "q"}).status_code == 200
        conn = sqlite3.connect(client.db)
        try:
            charged = conn.execute("SELECT COALESCE(SUM(count), 0) FROM key_usage").fetchone()[0]
        finally:
            conn.close()
        assert charged == 2  # health 不计，两次成功查询各计 1
        over = client.post("/api/v1/query", headers=headers, json={"question": "q"})
        assert over.status_code == 429


# ── P2-27：鉴权失败按来源 IP 限流 + 审计日志 ────────────────────────

def test_auth_failure_rate_limited_per_ip(tmp_path, monkeypatch):
    """同一 IP 鉴权失败超过阈值后直接 429，不再进入校验流程。"""
    import api.auth as auth_module
    from fastapi.testclient import TestClient

    from api.auth import init_auth_tables
    from api.main import create_app

    monkeypatch.setattr(auth_module, "AUTH_FAILURE_LIMIT_PER_MINUTE", 3)
    db = str(tmp_path / "t.db")
    init_auth_tables(db)
    monkeypatch.setenv("DB_PATH", db)

    app = create_app()
    with TestClient(app) as client:
        codes = [client.post("/api/v1/query", json={"question": "q"}).status_code for _ in range(5)]
        assert codes == [401, 401, 401, 429, 429]
        assert client.post("/api/v1/query", json={"question": "q"}).json()["code"] == "RATE_LIMITED"


def test_auth_failure_audit_links_request_id_and_ip(tmp_path, monkeypatch, caplog):
    """P2-18/P2-27：鉴权失败审计日志带 request_id 与 client_ip，且与响应信封一致。"""
    from fastapi.testclient import TestClient

    from api.auth import init_auth_tables
    from api.main import create_app

    db = str(tmp_path / "t.db")
    init_auth_tables(db)
    monkeypatch.setenv("DB_PATH", db)

    app = create_app()
    with caplog.at_level(logging.WARNING, logger="api.auth"):
        with TestClient(app) as client:
            response = client.post("/api/v1/query", json={"question": "q"})

    assert response.status_code == 401
    request_id = response.json()["request_id"]
    audits = [r for r in caplog.records if r.getMessage().startswith("auth failure audit")]
    assert audits
    assert getattr(audits[0], "request_id", None) == request_id
    assert getattr(audits[0], "client_ip", None) == "testclient"


# ── P1-10：上传计入日配额 + 竞态回滚 ───────────────────────────────

def _upload_client(api_test_client, **create_kwargs):
    """P2-40：上传路径样板收敛到 conftest（返回未进入 with 的 client/key/db）。"""
    client = api_test_client(key_kwargs=create_kwargs, with_header=False)
    return client, client.key, client.db


def test_upload_charges_daily_quota(api_test_client):
    client, key, db = _upload_client(api_test_client, daily_quota=1)
    headers = {"X-API-Key": key}
    files = {"file": ("a.csv", "类别,金额\n食品,12.5\n".encode("utf-8"), "text/csv")}
    with client:
        ok = client.post("/api/v1/datasets", headers=headers, files=files)
        assert ok.status_code == 200, ok.text

        over = client.post("/api/v1/datasets", headers=headers, files=files)
    assert over.status_code == 429
    assert over.json()["code"] == "RATE_LIMITED"

    conn = sqlite3.connect(db)
    try:
        datasets = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
    finally:
        conn.close()
    assert datasets == 1  # 配额拒绝发生在入库之前，未产生第二个数据集


def test_upload_quota_race_rolls_back_registration(api_test_client, monkeypatch):
    """上传成功但配额记账失败的竞态：回滚注册，不留下未计费的数据集。"""
    from api import main as main_module
    from api.datasets import list_datasets
    from api.errors import APIError, ErrorCode

    def exploding_charge(db_path, key_hash):
        raise APIError(ErrorCode.RATE_LIMITED, 429, "今日配额已用尽")

    monkeypatch.setattr(main_module, "charge_quota", exploding_charge)

    client = api_test_client()
    files = {"file": ("a.csv", "a,b\n1,2\n".encode("utf-8"), "text/csv")}
    with client:
        response = client.post("/api/v1/datasets", files=files)

    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert list_datasets(client.db) == []
    conn = sqlite3.connect(client.db)
    try:
        ds_tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ds_%'"
        ).fetchall()
    finally:
        conn.close()
    assert ds_tables == []
