# Changelog

本文件记录面向部署与仓库卫生的变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

### 2026-10-12 · 部署与仓库卫生批次（fix(assessment)）

#### 修复

- **P0-01**：新增免鉴权轻量存活探针 `GET /api/health`（`api/main.py`，`include_in_schema=False`，不挂 `require_api_key`，只回报进程与库文件状态）；`render.yaml` 的 `healthCheckPath` 经核对原本已指向 `/api/health`，路由补齐后即生效；`Dockerfile.api` 的 `HEALTHCHECK` 由探测 `/docs` 改为探测 `/api/health`（P2-44 顺带：探针读取 `PORT` 环境变量，避免与启动命令端口失配）。
- **P1-13**：CI 后端作业由 2 个冒烟测试文件改为全量 `pytest tests/ -q`。
- **P1-16**：修正 `docs/deployment.md` 部署验收命令——`/api/schema`、`/api/quality` 等不存在的路由改为 `/api/v1/*` 并补 `X-API-Key` 请求头说明。
- **P1-17**：CI 新增非阻塞（`continue-on-error`）ruff lint 作业；`requirements-dev.txt` 增加 `ruff`；新增 `.github/dependabot.yml`（pip / npm / github-actions，每周）。
- **P1-18**：`.gitignore` 增加 `.idea/`，并 `git rm -r --cached .idea` 移除 7 个被跟踪的 IDE 本地配置文件（本地文件保留）。
- **P1-19**：`scripts/backup_db.py` 由 `shutil.copy` 改为 SQLite 在线备份 API（`conn.backup()`），备份前执行 `PRAGMA wal_checkpoint(TRUNCATE)`，消除 WAL 模式在线库的撕裂快照风险。
- **P1-20**：`render.yaml` 为 API 服务挂载 1GB 持久磁盘（`/var/data`），`DB_PATH` 指向挂载点；应用 lifespan 启动时若 `DB_PATH` 无库文件，自动把构建期示例库 `data/query.db` 播种过去（`api/main.py: ensure_database`）；构建命令显式固定示例库生成在 `data/query.db`。
- **P2-16**：应用启动时检测 `WEB_CONCURRENCY>1` 并打 warning 日志（限流/配额/指标为单进程内存态，多 worker 属误配）。
- **P2-31**：支持 `DQC_DISABLE_DOCS=1` 关闭 `/docs`、`/redoc`、`/openapi.json`（`api/main.py`）；生产镜像默认开启该开关，Render Blueprint 同步设置；健康探针不受影响。
- **P2-43**：`.dockerignore` 追加 `tests/`、`load/`、`docs/`，测试与压测文档不再进入生产镜像。
- **P2-45**：CI 增加 `concurrency`（按 workflow+ref 分组，取消同分支旧 run）。
- **P2-46**：CI 的 `setup-python` 启用 `cache: pip` 依赖缓存。
- **P2-47**：修正 `docs/production_checklist.md` 步骤顺序——先冒烟免鉴权 `/api/health`，再签发管理 Key，之后才能带 Key 冒烟 `/api/v1/health`；uptime 监控目标改为免鉴权 `/api/health`。
- **P2-48**：`docs/deployment.md` 新增「备份与恢复」章节：备份命令、crontab / systemd timer / Render Cron Job 样例、每月恢复演练步骤。

#### 新增

- `CHANGELOG.md`（本文件）。
- `.env.example` 补充 `DQC_JSON_LOGS`、`DQC_DISABLE_DOCS` 变量说明。
- 测试：`tests/test_ops_health.py`（探针 / docs 开关 / worker 告警 / 播种）、`tests/test_backup_db.py`（在线备份一致性 / 保留轮换），并更新 `tests/test_api_v1.py` 中 `/api/health` 相关断言。

#### 延后（本批不修）

- **P2-42**：基础镜像未固定 digest、依赖无锁文件——需查询 registry 确定固定 digest 并生成 lock，另行处理。
- **LICENSE**（P2-49 的一部分）：许可证选择为法律决策，需项目所有者确认后再补。
