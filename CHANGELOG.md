# Changelog

本文件记录面向部署与仓库卫生的变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

### 2026-10-12 · 文档同步批次（fix(assessment)）

#### 修复

- **P1-12**：README 用例数 66 → 245（`python -m pytest tests/ --collect-only -q` 末行实测 245 collected，全量运行 245 passed）；tests/ 目录树由 3 个文件补齐为 14 个 test_*.py + conftest.py；项目结构树同步补齐 api/（auth、datasets、errors、logjson、metrics、request_context）、scripts/（manage_keys、backup_db、e2e_up.sh、e2e_up.ps1）与 load/（soak 压测脚本）。
- **README 缓存承诺**：「查询缓存」章节保持既有准确表述（核心库默认开启，HTTP API `/api/v1/query` 固定 `enable_cache=False`，`from_cache` 恒为 `false`）；`docs/technical_doc.md` 的「无缓存机制」过时表述改为现状（核心库已内置内存 LRU 缓存，API 路径固定关闭，多 worker 不共享）。
- **README 清洗可选开关**：新增「结果清洗开关」小节——核心库 `ask(clean_result=False)` 与 HTTP API 请求体 `"clean_result": false` 均可关闭默认开启的结果清洗（对应 `src/query_engine.py:62`、`api/models.py:50`）。
- **README .xls 移除**：数据接入与数据集上传表述改为 CSV / Excel(.xlsx)（对应 `api/datasets.py` `_ALLOWED_EXTS`，P2-20 移除 .xls）。
- **README /api/health 免鉴权探针**：「访问控制」不再声称「所有 `/api/*` 接口要求 `X-API-Key`」，改为除免鉴权存活探针 `GET /api/health`（P0-01）外均需 Key。
- **README LLM 超时**：新增「LLM 超时」小节——默认 30 秒，`LLM_TIMEOUT_SECONDS` 可覆盖（对应 `src/llm_client.py:23-24`）；`docs/deployment.md` 环境变量表同步新增该变量。
- **README 上传配额与数量上限**：补充「查询与上传均计入当日配额（默认 200 次/天，成功后记账）」「数据集数量上限 50 个，超出 429」（对应 `api/main.py:355-366`、`api/datasets.py:22`）。
- **README CI 检查**：由「API/可视化 smoke test + React 构建」更新为现状——全量后端测试（`pytest tests/ -q`，P1-13）、非阻塞 ruff lint（P1-17）、前端生产构建、密钥清扫。
- **docs/e2e 启动方式**：`docs/production_plan.md` 中「只写 Windows 可跑的 `scripts/e2e_up.ps1`」的表述（含一处错字）改为 bash 版 `scripts/e2e_up.sh`（P1-15 交付）与 PowerShell 版双入口；Self-Review 段同步更正；Phase 4/5 的 `load/query_soak.js`（k6）、healthcheck 指向 `/api/v1/health`、技术栈含 k6 等过时表述改为现状（`load/soak.py`、免鉴权 `/api/health`）。
- **docs/frontend_showcase_plan.md**：「首版 API 契约」章节补充现状说明——v0 路由已下线，现行接口为 `/api/v1/*`（除免鉴权探针 `GET /api/health` 外均需 `X-API-Key`），查询响应含分页字段且 `from_cache` 恒为 `false`。
- **docs/v1_contract_proposal.md**：验收标准中「现有 66 个后端用例」同步为 245。
- **docs/technical_doc.md** 其余过时表述：安全校验补充多语句拒绝与表白名单兜底（P1-09/P2-32）；LLM 客户端补 SDK 内建重试；数据接入层补 `execute_query` 资源边界（行数上限 / 执行超时 / 表白名单）；「后续优化方向」勾选已交付项（查询缓存、SQL 自动重试、批量查询 CLI、Web 界面）。

#### 说明

- 本批为纯文档变更，未改动任何代码，按仓库纪律免测试更新；测试数字以 `python -m pytest tests/ --collect-only -q` 实测为准。

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
