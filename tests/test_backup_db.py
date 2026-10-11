"""P1-19：backup_db.py 在线备份一致性测试。

核心场景：源库为 WAL 模式且有一条已提交事务仍在 -wal 中、连接保持打开
（模拟 API 运行中备份）。旧的 shutil.copy 只拷主库文件会丢失该事务；
sqlite3 backup API 必须把它带进快照，且备份后的新写入不影响快照。
"""

import os
import sqlite3
import time

import pytest

from scripts.backup_db import backup_db


def test_backup_includes_wal_committed_data_while_source_open(tmp_path):
    db = tmp_path / "query.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()
        conn.execute("INSERT INTO orders (name) VALUES ('wal_row')")
        conn.commit()  # 事务已提交，但连接打开时数据可能仍在 -wal 中

        # 连接保持打开（模拟 API 运行中）执行备份
        dest = backup_db(str(db), str(tmp_path / "backups"), keep=3)

        # 备份后源库继续写入，不得污染快照
        conn.execute("INSERT INTO orders (name) VALUES ('after_backup')")
        conn.commit()
    finally:
        conn.close()

    assert os.path.isfile(dest)
    snap = sqlite3.connect(dest)
    try:
        assert snap.execute("SELECT COUNT(*) FROM orders WHERE name='wal_row'").fetchone()[0] == 1
        assert snap.execute("SELECT COUNT(*) FROM orders WHERE name='after_backup'").fetchone()[0] == 0
    finally:
        snap.close()


def test_backup_snapshot_is_valid_standalone_sqlite(tmp_path):
    db = tmp_path / "query.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO orders (id) VALUES (1)")
        conn.commit()
    finally:
        conn.close()

    dest = backup_db(str(db), str(tmp_path / "backups"))

    # 快照是完整 SQLite 文件（含表结构），可独立打开校验
    assert sqlite3.connect(dest).execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_backup_rotation_keeps_recent_n(tmp_path):
    db = tmp_path / "query.db"
    sqlite3.connect(str(db)).close()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    old = backup_dir / "query_a.db"
    older = backup_dir / "query_b.db"
    old.write_bytes(b"old")
    older.write_bytes(b"older")
    os.utime(old, (time.time() - 7200,) * 2)
    os.utime(older, (time.time() - 3600,) * 2)

    dest = backup_db(str(db), str(backup_dir), keep=2)

    remaining = sorted(p.name for p in backup_dir.glob("*.db"))
    assert len(remaining) == 2
    assert old.name not in remaining  # mtime 最旧（2 小时前）的被清理
    assert older.name in remaining
    assert os.path.basename(dest) in remaining


def test_backup_missing_db_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup_db(str(tmp_path / "nope.db"), str(tmp_path / "backups"))
