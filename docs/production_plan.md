# 成品化实施计划（Production Plan）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan phase-by-phase. Checkboxes (`- [ ]`) mark execution state.

**Goal:** 把 DataQuery-Copilot 从演示级推到可内测的成品：鉴权 + 数据管道 + 去脚手架 + 验证 + 上线就绪。

**Architecture:** 后端加 `api/auth.py`（Key 校验/配额/限流）与数据集注册表（SQLite 元信息表），所有 `/api/*` 强制鉴权；前端加 Key 配置 + 数据集下拉 + 上传入口；E2E/负载本地可跑；收尾做镜像加固与上线清单。

**Tech Stack:** Python ≥3.10, FastAPI + Pydantic 2.x, SQLite（Key/配额/数据集元信息与业务库同库）, pytest + TestClient；React 19 + TS，vitest（已有），Playwright + k6（阶段四新增）。

**Spec:** 本计划即 spec。输入决策：鉴权 = API Key（无登录体系）；多表 = 多数据集并存 + 下拉切换；部署目标 = 暂不上线（阶段五只做到随时可上）。基础契约见 `docs/v1_contract_proposal.md`。

## Global Constraints

- Python `>=3.10`；Pydantic 2.x。
- 老 `/api/*` 行为除"新增鉴权"外不变（`tests/test_api.py` 须同步更新：fixture 自动建 Key 并带请求头）。
- v1 信封与错误码体系沿用；新增 `AUTH_REQUIRED`(401)、`RATE_LIMITED`(429) 两个码，后端 `api/errors.py` 与前端 `apiV1/types.ts` 同步。
- Key 只存 sha256（`secrets` 生成，`hmac.compare_digest` 比对），明文只在创建时显示一次。
- 限流为单进程内存实现（uvicorn 单 worker 前提，计划内注明；多 worker 需换 Redis——非目标）。
- 每个阶段独立提交、可独立交付；全量 pytest + 前端 build/vitest 全绿才能进入下一阶段。

## Review Focus

- Key 明文落盘/日志：创建接口只返一次，日志禁打完整 Key——阶段一测试覆盖（断言日志无 Key）。
- 配额按自然日重置：跨日边界行为——阶段一测试覆盖（伪造日期）。
- 上传文件名目录穿越（`../../etc` 类）：清洗 + 白名单——阶段二测试覆盖。
- 限流内存实现多 worker 失效：文档注明而非代码解决——阶段一在限流模块注释 + 阶段五清单注明。
- 密钥进仓库：阶段五加 CI grep 门禁（`.env`、`sk-`、`dqc_` 明文），测试覆盖。

---

## File Structure

- Create: `api/auth.py` —— Key 校验/配额/限流/表初始化，无其他职责。
- Create: `scripts/manage_keys.py` —— Key 签发/吊销/列表（CLI，跑在服务器上，无需鉴权）。
- Modify: `api/errors.py` —— 追加 `AUTH_REQUIRED`、`RATE_LIMITED`。
- Modify: `api/main.py` —— 所有 `/api/*` 加鉴权依赖；Key 管理走 CLI 不加路由。
- Modify: `api/models.py` —— 数据集模型（`DatasetInfo`、上传响应）。
- Modify: `api/services.py` —— 服务方法接受 `table_name` 参数（经注册表校验，非任意表名）。
- Create: `api/datasets.py` —— 数据集注册表（建表/登记/列表/解析上传文件→入库）。
- Create: `tests/test_api_auth.py` —— 鉴权/限流/配额测试。
- Create: `tests/test_datasets.py` —— 数据集管道测试。
- Create: `scripts/backup_db.py` —— 定时快照脚本。
- Modify: `frontend/src/apiV1/types.ts` + `client.ts` —— 附 `X-API-Key` 请求头。
- Modify: `frontend/src/App.tsx`、`Sidebar.tsx` —— Key 配置入口 + 数据集下拉 + 上传入口。
- Delete（阶段三）: `api/main.py` 内 v0 四路由、`frontend/src/contractV1/`、`?contract`/`?mock` 开关、演示快照默认页。
- Create（阶段四）: `frontend/e2e/`（Playwright）、`load/query_soak.js`（k6，只打无 LLM 成本端点）。
- Modify（阶段五）: `Dockerfile.api`（非 root + healthcheck）、`.github/workflows/ci.yml`（密钥 grep 门禁）、`docs/production_checklist.md`（上线清单）。

---

### Phase 1: 鉴权 + 限流

**Files:**
- Create: `api/auth.py`, `scripts/manage_keys.py`
- Modify: `api/errors.py`, `api/main.py`, `api/models.py`（仅为 Key 哈希表建模则不需要，表结构放 `auth.py` 内 SQL）
- Test: `tests/test_api_auth.py`
- Frontend: `apiV1/client.ts` + `api.ts` 附请求头；Key 配置入口；`apiV1/types.ts` 加两码

**Interfaces:**
- Produces: `api.auth.require_api_key(request) -> str`（FastAPI dependency，返 key_hash；失败抛 `APIError(AUTH_REQUIRED, 401)` / `(RATE_LIMITED, 429)`）；`api.auth.init_auth_tables(db_path)`（建 `api_keys`/`key_usage` 表，`IF NOT EXISTS`）；`scripts/manage_keys.py create --name X [--quota N]` 输出明文 Key 一次。
- Consumes: `api.errors.APIError`（复用 v1 路由的映射逻辑，0 改动）。

- [ ] **Step 1: 错误码先行（TDD / 后端）**——`api/errors.py` 加两码；`frontend/src/apiV1/types.ts` 同步 union；测试断言枚举值稳定。
- [ ] **Step 2: `api/auth.py` 最小实现**——`init_auth_tables`、`create_key`（返明文+存 sha256）、`verify_key`（compare_digest + revoked 检查）、内存滑动窗口限流（30 次/分钟/Key）、日配额检查与计数（`key_usage` 按日期）。
- [ ] **Step 3: 路由接线**——`require_api_key` dependency 加到全部 `/api/*` 与 `/api/v1/*`；计数点放在 query 入口（每次调用计一次 LLM 配额）。
- [ ] **Step 4: 测试**——无 Key/错 Key/吊销 Key → 401 信封（`code == AUTH_REQUIRED`）；打爆限流 → 429 `RATE_LIMITED`；配额耗尽 → 429；伪造跨日日期配额重置；断言日志不含 Key 明文；更新 `tests/test_api.py` fixture（自动建 Key + 带头）。
- [ ] **Step 5: 前端**——`apiV1/client.ts` 与 `api.ts` 从 `localStorage("dqc_api_key")` 读 Key 附 `X-API-Key`；顶栏或 Sidebar 加 Key 配置框；401/429 走现有错误码 chip 展示。
- [ ] **Step 6: CLI**——`scripts/manage_keys.py create/revoke/list`；README 加管理员操作说明。
- [ ] **Acceptance:** 无 Key 调任何接口 401 信封；超频 429；`pytest tests/test_api_auth.py` 全绿且全量 pytest 不变绿；v1 contract 测试仍绿。
- [ ] **Commit:** `feat(api): API key auth with rate limiting and quotas` + `feat(web): API key configuration`

---

### Phase 2: 数据接入管道

**Files:**
- Create: `api/datasets.py`, `scripts/backup_db.py`
- Modify: `api/models.py`（`DatasetInfo`、`UploadResponse`）、`api/services.py`（方法接受注册表校验后的 `table_name`）、`api/main.py`（`GET/POST /api/v1/datasets`、上传接口、query/schema/quality 按数据集作用域）
- Test: `tests/test_datasets.py`
- Frontend: Sidebar 数据集下拉；上传入口（文件选择 → multipart POST → 刷新列表）

**Interfaces:**
- Produces: `api.datasets.register_upload(db_path, filename, content: bytes) -> DatasetInfo`（校验扩展名 csv/xls/xlsx、≤50MB、表名 `ds_<slug>_<shortid>` 正则约束并入库登记）；`api.datasets.list_datasets(db_path)`；`api.datasets.resolve_table(db_path, dataset_id) -> str`（非法 id 抛 `APIError(TABLE_NOT_FOUND, 404)`）。
- Consumes: Phase 1 的鉴权依赖（上传/列表接口同样要求 Key）。

- [ ] **Step 1: 注册表**——`datasets` 元信息表（id/name/table_name/rows/created_at）+ `register_upload` 文件校验（扩展名/大小/文件名清洗，`../../` 攻击测试先行）。
- [ ] **Step 2: 作用域查询**——`QueryRequestV1` 加可选 `dataset` 字段；`services.query_page` 经 `resolve_table` 换表（默认 `orders` 保持兼容）；schema/quality 同理。
- [ ] **Step 3: 测试**——上传合法 CSV → 列表可见 → 按数据集查到新数据；非法扩展名/超大文件/穿越文件名拒绝；未知 dataset id → 404 `TABLE_NOT_FOUND`。
- [ ] **Step 4: 备份**——`scripts/backup_db.py`（时间戳拷贝到 `backups/`，保留最近 N 份）；做一次恢复演练并记录步骤进文档。
- [ ] **Step 5: 前端**——Sidebar 数据集下拉（切换后刷新 schema/quality/结果）；上传按钮 + 进度/错误展示（复用错误码）。
- [ ] **Acceptance:** 非技术人员上传 CSV 后可下拉切换并查到数据；备份可恢复；全量测试绿。
- [ ] **Commit:** `feat(api): dataset registry with upload and scoped queries` + `feat(web): dataset switcher and upload`

---

### Phase 3: 去 demo 脚手架

**Files:**
- Modify: `api/main.py`（删 v0 四路由）、`api/models.py`（删 `QueryRequest/QueryResponse` 旧模型，如无他用）、`api/services.py`（删旧 `query()`，如无他用）
- Delete: `frontend/src/contractV1/`、`mockData.ts`（或仅留空状态文案）、`?contract`/`?mock` 开关与 toggle UI
- Modify: `frontend/src/App.tsx`（默认走 v1 真实链路；首屏无数据时空状态）、错误文案脱敏（engine 原文只进服务端日志，`request_id` 关联）

- [ ] **Step 1: 后端清理**——删 v0 路由与旧模型/方法；确认 `tests/test_api.py` 按 Phase 1 更新后的形态继续覆盖 v1（v0 测试随路由删除）。
- [ ] **Step 2: 脱敏**——v1 错误映射只返错误码 + 通用文案，原文 `logger` 落盘带 `request_id`（标准库 logging，JSON 行格式）。
- [ ] **Step 3: 前端清理**——删 mock 模块与开关；空状态页；build 无警告新增。
- [ ] **Acceptance:** 生产构建不含 mock；`grep -r mock frontend/src` 为空（测试除外）；契约测试全绿。
- [ ] **Commit:** `chore: remove demo scaffolding and v0 routes`

---

### Phase 4: E2E + 负载（本地可跑）

**Files:**
- Create: `frontend/e2e/`（Playwright 用例 + `playwright.config.ts`）、`load/query_soak.js`（k6）、`load/README.md`（全量 LLM 压测手动步骤，因烧配额不自动化）
- Modify: `frontend/package.json`（`test:e2e` 脚本）、 Playwright 为 devDependency

- [ ] **Step 1: E2E 基座**——Playwright 安装；fixture：测试 Key（调 `manage_keys.py`）、前后端本地启动脚本（`scripts/e2e_up.sh`  feelings：只写 Windows 可跑的 `scripts/e2e_up.ps1`，本仓库主力环境是 Windows）。
- [ ] **Step 2: 用例**——无 Key 访问 401；填 Key 后提问出结果；翻页；触发 `SQL_REJECTED` 错误码展示；上传数据集并切换（Phase 2 已交付前提下）。
- [ ] **Step 3: k6**——只打无 LLM 成本端点（health/schema/quality + 非法问题 422）：虚拟用户爬坡，输出延迟 p95 与失败率；全量 LLM soak 写手动步骤文档。
- [ ] **Acceptance:** `npm run test:e2e` 全绿；k6 报告给出并发上限与慢查询清单。
- [ ] **Commit:** `test: e2e and load harnesses`

---

### Phase 5: 上线就绪准备（暂不上线）

**Files:**
- Modify: `Dockerfile.api`（非 root 用户、`HEALTHCHECK`）、`.dockerignore`（禁 `data/*.db`、`backups/`、`.env` 进镜像）
- Modify: `.github/workflows/ci.yml`（加密钥 grep 门禁：`.env` 被跟踪、`sk-`、`dqc_` 明文出现在非测试文件即红）
- Create: `docs/production_checklist.md`（域名/备份/告警占位/`ADMIN` Key 轮换步骤，1 小时上线目标）
- Modify: 日志 JSON 化 + `GET /api/v1/metrics`（请求计数/LLM 调用计数/错误计数，纯 JSON，不引入新依赖）

- [ ] **Step 1: 镜像加固**——非 root 运行、healthcheck 指向 `/api/v1/health`；本地 `docker build` + `docker run`冒烟（health 200）。
- [ ] **Step 2: 密钥门禁**——CI grep 步骤；全仓库扫一遍确认无密钥（`git log -S` 抽查历史）。
- [ ] **Step 3: 可观测最小集**——JSON 日志（含 request_id）、metrics 端点、uptime 监控占位（文档写用哪个免费服务）。
- [ ] **Step 4: 清单**——`production_checklist.md` 按"上线前/上线中/上线后"三段写，每步可执行命令。
- [ ] **Acceptance:** 镜像本地可跑；CI 门禁有效（故意提交假密钥能红）；按清单可在 1 小时内上线。
- [ ] **Commit:** `chore: production readiness`

---

## Self-Review

1. **Spec coverage:** API Key→Phase 1；多数据集下拉→Phase 2（含上传/切换/备份）；去脚手架→Phase 3；E2E/负载→Phase 4；暂不上线→Phase 5 只做就绪。输入决策全覆盖。
2. **Placeholder scan:** 无 TBD/TODO；每步有文件/接口/测试/验收；`e2e_up` 脚本明确 Windows ps1（本机主力环境）。
3. **Type consistency:** `require_api_key -> str`（key_hash）Phase 1 定义、路由消费一致；`resolve_table -> str` Phase 2 定义、services 消费一致；错误码新增两处同步（后端 errors.py + 前端 types.ts）。
4. **Review Focus:** 五条各有归属（Key 日志→P1 测试；配额跨日→P1；穿越→P2；多 worker→P1 注释+P5 清单；密钥门禁→P5 CI）。
