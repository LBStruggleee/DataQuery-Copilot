"""API Key 管理 CLI（跑在服务器上，无需鉴权）。

用法:
    python scripts/manage_keys.py create --name <名称> [--quota N] [--db PATH]
    python scripts/manage_keys.py list [--db PATH]
    python scripts/manage_keys.py revoke <明文Key> [--db PATH]

create 输出的明文 Key 只显示一次，请立即保存。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.auth import create_key, list_keys, revoke_key


def main() -> int:
    parser = argparse.ArgumentParser(description="管理 API Key")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/query.db"), help="密钥库路径")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="签发 Key（明文只显示一次）")
    p_create.add_argument("--name", required=True, help="Key 用途备注")
    p_create.add_argument("--quota", type=int, default=200, help="日配额（默认 200）")

    sub.add_parser("list", help="列出 Key（仅前缀）")
    p_revoke = sub.add_parser("revoke", help="吊销 Key")
    p_revoke.add_argument("key", help="签发时输出的明文 Key")

    args = parser.parse_args()
    if args.command == "create":
        print(create_key(args.db, args.name, args.quota))
    elif args.command == "list":
        for item in list_keys(args.db):
            state = "revoked" if item["revoked"] else "active"
            print(f'{item["prefix"]}...  {item["name"]}  {state}  quota={item["daily_quota"]}  {item["created_at"]}')
    elif args.command == "revoke":
        print("revoked" if revoke_key(args.db, args.key) else "not found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
