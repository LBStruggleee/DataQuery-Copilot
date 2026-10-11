#!/usr/bin/env bash
# E2E 一键入口（Linux/macOS/Git Bash，P1-15：与 scripts/e2e_up.ps1 等价的 bash 版）：
#   1. 准备隔离库 .e2e/query.db（拷贝演示库，不碰 data/query.db）
#   2. 签发测试 Key，注入 E2E_API_KEY
#   3. 起 Playwright（自动拉起 8001 后端 + 5173 前端）并跑完全部用例
# 用法：bash scripts/e2e_up.sh
set -euo pipefail

Root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$Root"

mkdir -p .e2e
rm -f .e2e/query.db
cp data/query.db .e2e/query.db
echo "e2e db prepared (fresh copy)"

Key="$(python scripts/manage_keys.py --db .e2e/query.db create --name e2e | tail -n 1 | tr -d '[:space:]')"
case "$Key" in
  dqc_*) ;;
  *) echo "key issue failed: $Key" >&2; exit 1 ;;
esac
export E2E_API_KEY="$Key"
echo "E2E_API_KEY ready"

cd frontend
npx playwright test
