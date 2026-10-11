"""部署与运维相关测试：免鉴权探针、docs 开关、多 worker 告警、挂载盘播种。

对应评估编号：P0-01（/api/health）、P2-31（DQC_DISABLE_DOCS）、
P2-16（WEB_CONCURRENCY 告警）、P1-20（ensure_database 播种）。
"""

import logging
import sqlite3

# ── P0-01：免鉴权轻量探针 /api/health ──────────────────────────

def test_health_probe_needs_no_api_key(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import create_app

    db = tmp_path / "query.db"
    db.write_bytes(b"")  # 库文件存在
    monkeypatch.setenv("DB_PATH", str(db))
    client = TestClient(create_app())  # 不带 X-API-Key

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "database_ready": True}


def test_health_probe_reports_degraded_when_db_missing(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import create_app

    monkeypatch.setenv("DB_PATH", str(tmp_path / "missing.db"))
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "database_ready": False}


def test_health_probe_not_in_openapi_contract(monkeypatch):
    """探针只服务于基础设施，不应进入 v1 契约或暴露给 openapi 枚举。"""
    from fastapi.testclient import TestClient

    from api.main import create_app

    client = TestClient(create_app())
    spec = client.get("/openapi.json").json()
    assert "/api/health" not in spec["paths"]
    assert "/api/v1/health" in spec["paths"]


# ── P2-31：DQC_DISABLE_DOCS 关闭 docs/openapi ──────────────────

def test_disable_docs_hides_docs_and_openapi(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import create_app

    monkeypatch.setenv("DQC_DISABLE_DOCS", "1")
    client = TestClient(create_app())

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    # 健康探针不受 docs 开关影响（Dockerfile HEALTHCHECK 依赖它）
    assert client.get("/api/health").status_code == 200


def test_docs_enabled_by_default(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import create_app

    monkeypatch.delenv("DQC_DISABLE_DOCS", raising=False)
    client = TestClient(create_app())

    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


# ── P2-16：多 worker 误配启动告警 ──────────────────────────────

def test_multi_worker_config_warns_on_startup(monkeypatch, caplog):
    from api.main import create_app

    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    with caplog.at_level(logging.WARNING, logger="api.main"):
        create_app()

    warnings = [r for r in caplog.records if "WEB_CONCURRENCY" in r.getMessage()]
    assert warnings and warnings[0].levelno == logging.WARNING


def test_single_worker_does_not_warn(monkeypatch, caplog):
    from api.main import create_app

    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    with caplog.at_level(logging.WARNING, logger="api.main"):
        create_app()

    assert not [r for r in caplog.records if "WEB_CONCURRENCY" in r.getMessage()]


# ── P1-20：挂载点无库文件时用构建期示例库播种 ───────────────────

def _make_seed_db(path):
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO orders (name) VALUES ('seed_row')")
        conn.commit()
    finally:
        conn.close()


def test_ensure_database_seeds_missing_db(tmp_path):
    from api.main import ensure_database

    seed = tmp_path / "seed" / "query.db"
    seed.parent.mkdir()
    _make_seed_db(seed)
    target = tmp_path / "var" / "data" / "query.db"

    seeded = ensure_database(str(target), str(seed))

    assert seeded is True
    conn = sqlite3.connect(str(target))
    try:
        assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
    finally:
        conn.close()


def test_ensure_database_never_overwrites_existing(tmp_path):
    from api.main import ensure_database

    seed = tmp_path / "seed.db"
    _make_seed_db(seed)
    target = tmp_path / "var" / "data" / "query.db"
    target.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute("CREATE TABLE production (id INTEGER)")
        conn.commit()
    finally:
        conn.close()

    seeded = ensure_database(str(target), str(seed))

    assert seeded is False
    conn = sqlite3.connect(str(target))
    try:
        # 真实业务库不被示例库覆盖
        assert conn.execute("SELECT COUNT(*) FROM production").fetchone()[0] == 0
    finally:
        conn.close()


def test_ensure_database_noop_without_seed(tmp_path, caplog):
    from api.main import ensure_database

    target = tmp_path / "var" / "data" / "query.db"
    with caplog.at_level(logging.WARNING, logger="api.main"):
        seeded = ensure_database(str(target), str(tmp_path / "no-seed.db"))

    assert seeded is False
    assert not target.exists()
    assert any("无示例库" in r.getMessage() for r in caplog.records)


def test_ensure_database_noop_when_target_is_seed(tmp_path):
    from api.main import ensure_database

    seed = tmp_path / "query.db"
    _make_seed_db(seed)

    assert ensure_database(str(seed), str(seed)) is False


def test_lifespan_seeds_db_on_startup(tmp_path, monkeypatch):
    """应用启动（lifespan）时把示例库播种到 DB_PATH 挂载点。"""
    from fastapi.testclient import TestClient

    import api.main as main_module
    from api.main import create_app

    seed = tmp_path / "seed" / "query.db"
    seed.parent.mkdir()
    _make_seed_db(seed)
    target = tmp_path / "var" / "data" / "query.db"
    monkeypatch.setenv("DB_PATH", str(target))
    monkeypatch.setattr(main_module, "SEED_DB_PATH", str(seed))

    with TestClient(create_app()) as client:  # with 触发 lifespan
        assert client.get("/api/health").json()["database_ready"] is True

    assert target.is_file()
