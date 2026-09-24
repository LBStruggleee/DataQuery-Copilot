"""SQLite 备份脚本：时间戳快照 + 保留最近 N 份。

用法:
    python scripts/backup_db.py [--db data/query.db] [--dir backups] [--keep 7]

恢复演练:
    cp backups/query_<timestamp>.db /tmp/restored.db
    python -c "import sqlite3; print(sqlite3.connect('/tmp/restored.db').execute('SELECT COUNT(*) FROM orders').fetchone())"
"""

import argparse
import glob
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def backup_db(db_path: str, backup_dir: str, keep: int = 7) -> str:
    """拷贝快照并清理旧份，返回快照路径。"""
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"数据库不存在: {db_path}")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_dir, f"{os.path.splitext(os.path.basename(db_path))[0]}_{stamp}.db")
    shutil.copy(db_path, dest)
    snapshots = sorted(glob.glob(os.path.join(backup_dir, "*.db")), key=os.path.getmtime)
    for old in snapshots[:max(0, len(snapshots) - keep)]:
        os.remove(old)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="备份 SQLite 数据库")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/query.db"))
    parser.add_argument("--dir", default="backups")
    parser.add_argument("--keep", type=int, default=7)
    args = parser.parse_args()
    print(backup_db(args.db, args.dir, args.keep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
