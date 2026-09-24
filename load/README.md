# 负载说明

## 自动化的（无 LLM 成本）

`load/soak.py` 只打不调 LLM 的端点：health / schema / quality / datasets /
空白问题 422 / 未知数据集 404（含信封校验）。Key 在本机直接签发，轮询使用。

```bash
# 1. 准备隔离库（别碰 data/query.db）
mkdir .soak
cp data/query.db .soak/query.db

# 2. 起后端（另开终端）
DB_PATH=.soak/query.db python -m uvicorn api.main:app --port 8002

# 3. 跑压测
python load/soak.py --base http://127.0.0.1:8002 --db .soak/query.db --keys 10 --total 200 --workers 20
```

`.soak/` 已加入 `.gitignore`，不会进仓库。

## 实测基线（本机，2026-09-24）

默认配置（10 并发，140 请求）：0 失败，p50 ≈ 140ms，p95 ≈ 220ms，全路径 <300ms。

20 并发时 `/api/v1/quality` p95 退化到约 4s（万行 pandas 计算在 GIL 下 contention，
单请求仅 67ms），其余端点 <300ms。结论：quality 是当前并发上限瓶颈，
优化它（缓存/减列/索引）是后续性能工作的第一项，本阶段只记录不修。

## 手动的（烧 LLM 配额，不自动化）

全链路 soak（真实提问 → LLM → SQL → 执行）每次调用都烧钱，不进自动化：

1. 在 `.env` 填入 `DEEPSEEK_API_KEY`（测试专用 Key，注意配额）
2. 用管理 Key 调低被测 Key 的日配额（如 50），防止跑飞
3. 手动跑 20～50 次真实提问，记录 p95 与失败 SQL
4. 跑完立即吊销被测 Key：`python scripts/manage_keys.py revoke <Key>`
