"""Phase 1: API Key 鉴权、限流、配额。"""

import logging

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
def authed_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from api.auth import create_key
    from api.main import create_app, get_query_service

    db = str(tmp_path / "t.db")
    monkeypatch.setenv("DB_PATH", db)
    key = create_key(db, "ci")

    class FakeService:
        @property
        def db_path(self):
            return db

        def query_page(self, question, clean_result, max_retries, page, page_size, table_name=None):
            return {"question": question, "sql": "SELECT 1", "columns": ["a"], "rows": [{"a": 1}],
                    "row_count": 1, "page": 1, "page_size": 10, "total_pages": 1,
                    "truncated": False, "chart_hint": "table", "execution_time": 0.01,
                    "valid": True, "retries": 0, "from_cache": False}

    app = create_app()
    app.dependency_overrides[get_query_service] = FakeService
    with TestClient(app) as client:
        client.key = key
        yield client


def test_v1_query_requires_key(authed_client):
    response = authed_client.post("/api/v1/query", json={"question": "有效问题"})
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "AUTH_REQUIRED"
    assert body["data"] is None
    assert body["request_id"].startswith("req_")


def test_v0_health_requires_key(authed_client):
    response = authed_client.get("/api/health")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_valid_key_passes(authed_client):
    response = authed_client.post(
        "/api/v1/query", json={"question": "有效问题"}, headers={"X-API-Key": authed_client.key}
    )
    assert response.status_code == 200
    assert response.json()["code"] == "OK"


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
