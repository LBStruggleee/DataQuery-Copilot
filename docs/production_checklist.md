# 上线检查清单（目标：1 小时内可上线）

> 当前状态：暂不上线。本清单保证任何时候按此执行即可上线。

## 上线前

- [ ] 准备生产 `DEEPSEEK_API_KEY`（测试专用 Key，设小日配额）
- [ ] 确认 `git status` 干净，`origin/master` 为待发布 commit
- [ ] 本地跑一遍门禁：`pytest tests/ -q`、`npm run build`（frontend 目录）、密钥 grep（见 CI `secret-sweep`）
- [ ] 构建镜像：`docker build -f Dockerfile.api -t dataquery-copilot-api:<版本> .`（本机无 docker 的环境下跳过，由 CI/上线机执行）
- [ ] 准备生产数据库：首次用 `scripts/prepare_demo_db.py` 建库，后续靠 `scripts/backup_db.py` 快照

## 上线中

- [ ] 容器注入环境变量（绝不进镜像）：`DEEPSEEK_API_KEY`、`DB_PATH`、（可选）`DQC_JSON_LOGS=1`
- [ ] 启动后冒烟：`GET /api/v1/health` 200；签发管理 Key：`python scripts/manage_keys.py create --name admin`
- [ ] 用管理 Key 调一遍核心链路：health / schema / quality / datasets / query（小问题）/ metrics
- [ ] 前端构建产物部署到静态托管，`VITE_API_BASE_URL` 指向 API 域名

## 上线后

- [ ] uptime 监控占位：任选免费服务监控 `GET /api/v1/health`（未配置前手动每天看一次 metrics）
- [ ] 备份任务：每天 `python scripts/backup_db.py --keep 14`（cron/systemd timer），每月做一次恢复演练
- [ ] Key 轮换：管理 Key 每 90 天 `revoke` + `create`；离职/泄露立即吊销
- [ ] 费用：每周看一次 `query_requests`（metrics）× 单价，超预算先降被测 Key 配额
- [ ] 已知上限（实测）：20 并发下 `/api/v1/quality` p95 约 4s（见 `load/README.md`），优化前不要把 quality 暴露给高频调用
- [ ] 单进程内存限流前提：uvicorn 保持单 worker；要多 worker 先把限流换 Redis（另行排期）
