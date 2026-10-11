# DataQuery-Copilot 专业评估报告

- **评估日期**：2026-10-12
- **评估对象**：`LBStruggleee/DataQuery-Copilot`（本地工作区，master @ 9f04960）
- **评估方法**：dynamic workflow 六个子任务严格串行（max_concurrency=1）——后端核心库 → API 层 → 安全专项 → 测试体系 → CI 与部署 → 前端；每个子任务逐文件通读并返回结构化结论；主智能体（本报告撰写者）在子任务运行前已独立通读关键安全与核心模块（auth.py、query_engine.py、llm_client.py、services.py、datasets.py、main.py、models.py、Dockerfile.api、render.yaml、data_loader.py、.dockerignore），对高风险结论做了交叉核查
- **确定性实测**：`python -m pytest tests/ -q` → **exit 0，99 个用例全部通过**；`npx vitest run` → **3 个测试文件失败 | 1 个通过**（详见 P1-14）；`npm run build`、docker build、e2e 未能在本环境执行（见第八节）
- **git 历史**：41 个提交，2026-07-09 至 2026-09-26，演进轨迹为「核心链路 → 生产化加固（硬化镜像、secret 门禁、JSON 日志、配额收紧）」

---

## 一、总体结论

这是一个**完成度和工程意识显著高于典型个人项目**的 LLM Text-to-SQL 工具：三层架构（src/ 核心库 → api/ FastAPI → frontend/ React）分层清晰、核心库可脱离 FastAPI 独立测试；安全骨架真实成体系（Key 仅存 sha256 + `hmac.compare_digest` 比对、SQL 词边界黑名单 + SELECT/WITH 白名单前缀、表名服务端生成、全路由鉴权、错误信封统一）；**99 个后端测试全部通过**，且安全机制（SQL 校验绕过、401/429、恶意上传）有专项测试覆盖，断言落在真实代码而非 mock 上；仓库内 0 个 TODO/FIXME，代码卫生好。

但**当前状态不可直接上线**：唯一的 P0 是 Render 部署的健康检查指向不存在的路由（必然 404，部署即阻断）；26 个 P1 集中在三类——资源边界缺失（SQL 执行无超时/行数上限、上传先收后检、xlsx 解压炸弹、LLM 调用无 timeout）、CI 门禁缺口（81 个含全部安全测试的用例不进 CI、前端测试在 CI 中完全不执行且 vitest 开箱即挂）、异步边界错误（async 端点内同步跑 pandas/sqlite 阻塞事件循环）。

**总体评价：功能完成度 ~8/10，工程质量 ~7/10，上线就绪度 ~5/10。综合 6.8/10。**「写得好」与「能上线」之间的差距主要在运维侧（部署配置、持久化、CI 门禁），而非代码能力。

### 各层评分表

| 领域 | 评分（0-10） | 状态 | 一句话依据 |
|---|---|---|---|
| 后端核心库 `src/` | **6.5** | 完成 | 分层清晰、SQL 校验在 SQLite 语义下基本不可绕过（实测），但 Excel 导入必崩、清洗污染数据、缓存键缺陷、承诺的清洗能力未接入链路 |
| API 服务层 `api/` | **7.0** | 完成 | 7 条路由全鉴权、契约对齐好、密钥管理规范；短板在异步边界、可观测性与契约缺口（QUERY_TIMEOUT 无实现） |
| 安全专项（健壮度） | **7.0** | 完成 | 未发现 P0 级可利用漏洞（多语句/PRAGMA/load_extension 均实测被拦）；最大风险是校验只拦动词不做表白名单，LLM 可诱导 SELECT 读全库（含 api_keys） |
| 测试体系 | **7.5** | 完成 | 99 例全过、安全测试齐全、无伪测试；但 CI 只跑 18 例冒烟、vitest 开箱即挂、CLI 361 行零测试 |
| CI 与部署 | **5.0** | 完成 | 有骨架（3 job、非 root 镜像、secret 清扫），但健康检查 404 阻断部署、文档验收步骤走不通、无 lint/审计、Render 无持久磁盘 |
| 前端 `frontend/` | **7.5** | 完成 | 结构清晰、无 any/TODO、strict 开启、a11y 认真；但请求无超时、AbortController 形同虚设、Inspector 展示伪造指标 |

---

## 二、问题统计

六个子任务共报告 **91 条原始发现**；跨层重复的 9 组同源问题合并后，统一问题清单为 **82 条**（P0 ×1、P1 ×25、P2 ×56）。

### 按优先级

| 优先级 | 定义 | 条数（合并后） |
|---|---|---|
| **P0** | 阻断上线 | 1 |
| **P1** | 应尽快修复 | 25 |
| **P2** | 可改进 | 56 |

### 按类别 × 领域（原始 91 条）

| 领域 | 不合理 | 不完善 | 空缺 | 小计 |
|---|---|---|---|---|
| 后端核心库 | 3 | 15 | 1 | 19 |
| API 层 | 3 | 11 | 2 | 16 |
| 安全专项 | 0 | 17 | 0 | 17 |
| 测试体系 | 0 | 9 | 3 | 12 |
| CI 与部署 | 3 | 9 | 3 | 15 |
| 前端 | 1 | 10 | 1 | 12 |
| **合计** | **10** | **71** | **10** | **91** |

### 空缺项速览（10 条「该有而没有/承诺未兑现」）

README 承诺的数据清洗能力未接入查询链路、HTTP 路径查询缓存被关闭（与 README 矛盾）、QUERY_TIMEOUT(504) 有定义无实现、Excel(.xls) 白名单缺 xlrd 依赖必失败、CI 无 lint/类型检查/依赖审计、前端测试不进 CI、上传解析失败分支零测试、CLI 零测试、承诺的 cron 备份/月度恢复演练无任何配置支撑、缺 LICENSE/CONTRIBUTING/CHANGELOG/SECURITY.md。

---

## 三、P0 问题清单（阻断上线，1 条）

### P0-01 Render 健康检查指向不存在的路由，部署必然失败「CI 与部署 · 不合理」
- **位置**：render.yaml:7；对照 api/main.py:112-114、api/auth.py:169-170
- **问题**：`healthCheckPath: /api/health` 在代码中不存在——实际路由全部是 `/api/v1/*`，且 `/api/v1/health` 挂了 `require_api_key` 依赖（无 X-API-Key 即 401）。仓库中不存在任何免鉴权健康端点，Render 健康检查无论打哪个现有路径都会失败。
- **证据**：render.yaml:7 `healthCheckPath: /api/health`；`git grep` 实测 api/ 下仅有 `/api/v1/health`（main.py:112），该路由 Depends(require_api_key)（main.py:114）。Dockerfile.api:20-22 的注释也自认「/api/v1/health 需 API Key，不适合做无参探针」并已改用 /docs，但 render.yaml 未同步。
- **修复**：新增免鉴权轻量 `/api/health`（只查进程/库文件存在性），render.yaml 指向它；或临时将 healthCheckPath 改为 `/docs`（与 Dockerfile 做法一致）。
- **复核**：主智能体在子任务运行前独立读码确认 ✓

---

## 四、P1 问题清单（应尽快修复，25 条）

### 资源边界与稳定性

**P1-01｜后端核心库 · 不合理** Excel 导入全路径崩溃
位置 `src/data_loader.py:53,68-70`。默认 `sheet_name=None` 使 `pd.read_excel` 返回 dict，后续 `_optimize_dtypes:85` 访问 `df.columns` 抛 AttributeError。实测 pandas 2.3.2 单/多 Sheet 均返回 dict。README.md:65 承诺「CSV/Excel 导入 SQLite」。修复：默认 `sheet_name=0` 或对 dict 显式取第一个工作表。

**P1-02｜后端核心库 · 不合理** 清洗层把缺失值污染成字符串 `'None'`
位置 `src/data_cleaner.py:112-113`（经 src/query_engine.py:152-153 触发）。`astype(str)` 整列转换使缺失值变成字面量 `'None'`，且挂在每次成功查询之后（ask 默认 clean_result=True）。实测 `DataFrame({'name':['alice',None]})` 处理后输出 `{'name':'None'}`。修复：用 `df[col].str.strip()` 保留 NaN，禁止整列 astype(str)。

**P1-03｜后端核心库 · 不合理** 缓存键不含表名与数据版本，返回过期结果
位置 `src/query_engine.py:78,159-160,194-197` + `src/data_loader.py:46,70`。`cache_key = question.strip().lower()`；`load_data` 切换表不清缓存，数据文件以 `if_exists="replace"` 覆盖同表后旧缓存照常命中。API 层只能以 `enable_cache=False`（services.py:69）掩盖。修复：缓存键纳入 table_name 与数据指纹，load_data 内调用 clear_cache。复核：主智能体独立确认 ✓

**P1-04｜后端核心库 + API 层 · 不完善/空缺** LLM 调用无超时，QUERY_TIMEOUT(504) 契约空缺
位置 `src/llm_client.py:43`、`api/errors.py:10`、`api/services.py:62-71`。`OpenAI(api_key=..., base_url=...)` 未设 timeout（SDK 默认 600s）× 最多 (1+max_retries≤3) 次调用，一个请求可占住线程池 worker 40 分钟；契约 §4.2 定义的 `QUERY_TIMEOUT | 504` 全仓库无一处 raise。修复：显式设置超时（如 30s）并映射为 QUERY_TIMEOUT。

**P1-05｜后端核心库 + 安全专项 · 不完善** 校验放行无终止的 WITH RECURSIVE，执行层无超时/无行数上限
位置 `src/llm_client.py:155-187` + `src/data_loader.py:148-150`、`api/services.py:77-84`。实测 `validate_sql('WITH RECURSIVE x(i) AS (SELECT 1 UNION ALL SELECT i+1 FROM x) SELECT * FROM x') == True`；`execute_query` 仅有 `pd.read_sql_query`，无 progress handler/interrupt/行数预限——大笛卡尔积全量物化后才截断 100 行，单条 SELECT 即可耗尽 CPU/内存。修复：校验层拒绝 RECURSIVE 或强制 LIMIT，执行层加超时中断。复核：主智能体确认执行路径无超时/上限 ✓

### API 层

**P1-06｜API 层 · 不完善** async 端点与 async 鉴权依赖在事件循环上执行同步阻塞 I/O
位置 `api/main.py:184-190`、`api/auth.py:165-174`。上传路由 `await file.read()` 后同步调 `register_upload`（pandas 解析 + `df.to_sql`，最大 50MB）；`require_api_key` 是 async def，内部 `init_auth_tables`/`verify_key` 为同步 sqlite3——**每个请求**都阻塞事件循环；其余 6 个路由为 sync def（线程池）无此问题。修复：上传下沉线程池，init_auth_tables 移到启动期。复核：主智能体独立确认 ✓

**P1-07｜API 层 + 安全专项 · 不完善** 50MB 上限在全量读入内存后才检查
位置 `api/main.py:189`、`api/datasets.py:47-48`。`content = await file.read()` 先把整个请求体读入内存（Starlette 超 1MB 已先落盘临时文件），之后才 `if len(content) > MAX_UPLOAD_BYTES`；无 Content-Length 预检、无流式限量读取。恶意超大上传先耗内存再被拒。修复：分块流式读取边读边计数，或读前校验 Content-Length。

**P1-08｜API 层 · 不完善** 除 query 外的路由把 500 异常静默吞掉，无任何服务端日志
位置 `api/main.py:118,133,146,176,194`。health/schema/quality/datasets/upload 五处 `except Exception:` 直接返回 500 信封不记日志；main.py:146 的 `error` 变量未使用；query 路由也仅 `logger.warning` 不带 exc_info——「engine 原文只进服务端日志」的注释（main.py:35）在非 query 路径不成立。修复：各 except 统一 `logger.exception(...)` 并附 request_id。

### 安全专项

**P1-09｜安全专项 · 不完善** SQL 校验只拦危险动词、不做表白名单，LLM 可诱导 SELECT 读全库
位置 `src/llm_client.py:155-187`、`src/data_loader.py:148-150`。实测 `validate_sql("SELECT key_hash, name FROM api_keys") → True`；`WITH x AS (SELECT key_hash FROM api_keys) SELECT * FROM x → True`；`SELECT name, sql FROM sqlite_master → True`。用户问题全文直接进 prompt（llm_client.py:57,114），问题文本中嵌入指令即可诱导生成此类 SQL，读取 api_keys/key_usage/其他数据集。修复：执行前表白名单（仅当前 dataset 表）或用 `set_authorizer` 限制，并用只读连接打开业务库。

**P1-10｜安全专项 · 不完善** 上传不计日配额、无数据集数量/磁盘总量上限
位置 `api/main.py:183-195`、`api/auth.py:133-134`。上传路由仅挂鉴权依赖；按限流上限 30 次/分钟 × 50MB 计算，单 key 每分钟可写入约 1.5GB，SQLite 无限膨胀且无清理接口。修复：上传计入配额或独立存储配额，增加数量/总量上限。

**P1-11｜安全专项 · 不完善** xlsx（zip 容器）解析无解压上限，可被解压炸弹打爆内存
位置 `api/datasets.py:53-54`。`pd.read_excel(io.BytesIO(content))` 一次性全量加载，50MB 恶意工作簿可膨胀数 GB。修复：用 openpyxl read_only 流式读取并设单元格/行数上限。

### 测试体系

**P1-12｜测试体系 · 不完善** README 声称 66 个测试用例，实测 99 个，文档失实
位置 `README.md:109,137`。脚本代跑 `python -m pytest tests/ -q` 为 99 passed（94 个测试函数 + 5 个参数化）；README.md:110-113 的目录树只列 3 个测试文件，实际 10 个 test_*.py。修复：更新数字与目录树，建议 CI 自动核对。

**P1-13｜测试体系 + CI · 空缺** CI 只跑 2/12 个后端测试文件（18 例冒烟），81 例（含全部安全测试）不进 CI
位置 `.github/workflows/ci.yml:20`。`python -m pytest tests/test_api.py tests/test_visualizer.py -q`；test_api_auth/test_api_v1/test_query_engine/test_datasets/test_logjson 等全部不在 CI；production_checklist.md:9 却把 `pytest tests/ -q` 定为上线门禁。修复：CI 改跑全量 `pytest tests/ -q`。

**P1-14｜测试体系 · 不完善** 前端 `npm test`（vitest）开箱即挂
位置 `frontend/package.json:10`。实测 `npx vitest run` → "Test Files 3 failed | 1 passed (4)"：vitest 未排除 `e2e/`，把 3 个 Playwright spec 误收集进来加载失败，退出码 1；真正通过的仅 envelope.test.ts 9 例；frontend/ 无 vitest.config。修复：vitest 配置 exclude e2e/，或 test 脚本改为 `vitest run src`。

**P1-15｜测试体系 · 不完善** 真实链路 e2e 依赖 Windows-only 的 PowerShell 脚本注入 Key，CI 无法运行
位置 `frontend/e2e/backend-api.spec.ts:18` 等。4 个用例 `test.skip(!key, "E2E_API_KEY not set (run scripts/e2e_up.ps1)")`，playwright.config.ts 的 webServer 不注入该变量——Linux/CI 上 8 例中 4 例静默 skip。修复：提供 bash 版入口并在 CI 注入测试 Key。

### CI 与部署

**P1-16｜CI 与部署 · 不完善** deployment.md 引用不存在的路由，部署验收步骤走不通
位置 `docs/deployment.md:12,29,66-70`。文档称健康检查为 `/api/health`、验收命令 `curl /api/health /api/schema /api/quality`——实际路由均为 `/api/v1/*` 且需 X-API-Key，直接 curl 得 404/401。修复：文档改为 v1 路由并补 `-H 'X-API-Key: ...'`。

**P1-17｜CI 与部署 + 测试体系 · 空缺** CI 无 lint/后端类型检查/依赖安全审计，前端 vitest 与 Playwright e2e 在 CI 中完全不执行
位置 `.github/workflows/ci.yml:28-38`。frontend-build job 仅 npm ci + npm run build；requirements-dev.txt 无 ruff/mypy；无 dependabot.yml、无 pip-audit/npm audit，仅有自制 grep 密钥清扫（ci.yml:37-51）。修复：增加 lint job（ruff + eslint）、pip-audit/npm audit、frontend-test job。

**P1-18｜CI 与部署 · 不合理** `.idea/` 下 7 个 IDE 本地配置文件被 git 跟踪
位置 `.idea/dataquery-copilot.iml` 等。`git ls-files` 实测跟踪了 .idea/.gitignore、dbnavigator.xml、inspectionProfiles 等 7 个文件；.gitignore 无 .idea 条目。修复：.gitignore 增加 .idea/ 并 `git rm -r --cached .idea`。

**P1-19｜CI 与部署 · 不完善** 备份脚本对 WAL 模式的在线库直接 shutil.copy，有撕裂快照风险
位置 `scripts/backup_db.py:28`、对照 `src/data_loader.py:23`。仅拷主库文件，-wal/-shm 中已提交事务不在快照内，API 运行中备份可能不一致；无锁、未用 sqlite3 backup API。修复：改用 `conn.backup()` 或 `VACUUM INTO`，备份前 wal_checkpoint。

**P1-20｜CI 与部署 · 不合理** Render API 服务无持久磁盘，SQLite 数据重部署即回退到构建期示例数据
位置 `render.yaml:1-20`。DB_PATH=data/query.db 但未声明 `disk:`；deployment.md:31 自认真实业务数据不应依赖本地 SQLite，却未提供挂载或托管库替代路径。密钥表/配额/上传数据集全部随之丢失。修复：挂载 Render disk 或迁移托管 PostgreSQL，并在文档写明触发条件。

### 前端

**P1-21｜前端 · 不完善** refreshOverview 不传 AbortSignal，慢的旧响应覆盖新响应
位置 `frontend/src/App.tsx:62-65`。`loadWorkspaceOverviewV1Live(undefined, datasetId)` 写死 signal=undefined，而 client.ts:74-84 明明支持透传；数据集/Key 快速切换时 useEffect（App.tsx:106）重发请求但旧请求不取消，后到者直接覆盖。修复：useEffect 内 AbortController + catch 静默 AbortError。

**P1-22｜前端 · 不完善** 401/429 无针对性用户提示，断网与 Key 失效不可区分
位置 `frontend/src/App.tsx:157-163,178`。client.ts:43-49 已抛带 status/code 的 V1ApiError，但 App.tsx:158 只取 message、概览路径状态码丢失；Key 输入框（Sidebar.tsx:151-163）不联动、不聚焦；429 无稍后重试引导。修复：保留 status/code，401 时聚焦 Key 输入框提示重贴，429 显示重试引导。

**P1-23｜前端 · 空缺** 所有请求无超时，后端挂起时用户永远停在加载态
位置 `frontend/src/apiV1/client.ts:38`。fetch 无 AbortSignal.timeout 也无定时器；挂起时 650ms 阶段指示器停在「正在执行查询」无限运转，无失败反馈。修复：`AbortSignal.any([init?.signal, AbortSignal.timeout(30_000)])` 统一加超时。

**P1-24｜前端 · 不合理** Inspector 展示伪造指标：硬编码「异常值 5」、用问题长度哈希伪造查询 ID
位置 `frontend/src/components/Inspector.tsx:77,79,83`。查询 ID 是 `qry_${question.length * 7919 ...}` 伪造，而 client.ts:51 明明解析了真实 request_id 却被 App 全程弃用；质量缺失条固定标注 `amount` 与数据集无关；Sidebar.tsx:71 硬编码「1 张表」。分析工具里伪造指标直接误导用户。修复：展示真实 request_id，后端没有的指标显示「—」。

**P1-25｜前端 + 安全专项 · 不完善** API Key 明文持久存于 localStorage 且页面无 CSP
位置 `frontend/src/App.tsx:53,76`、`frontend/src/apiV1/client.ts:7,12`、`frontend/index.html:3-12`。Key 明文落盘、无过期/吊销的前端感知（吊销后仅表现为持续 401），index.html 无 Content-Security-Policy，XSS 可直接窃取长期凭证。缓解项已有：type=password、请求头传输不落 URL。修复：加 CSP meta；401 时提示更换；更敏感部署改 sessionStorage/内存态。

---

## 五、P2 问题清单（可改进，56 条）

### 后端核心库（14 条）

**P2-01**｜`src/query_engine.py:123,119,159-160`｜不完善——`ask()` 不校验 max_retries：负值使重试循环零次执行但返回 valid=True/error=None 的假成功，且空结果写入缓存被后续命中。实测 `ask(q, max_retries=-1)` 返回假成功。修复：入口校验 max_retries >= 0。
**P2-02**｜`src/query_engine.py:37,44,159-160,241-243`｜不完善——查询缓存与 JSONL 日志均无容量上限/TTL/淘汰：缓存条目内嵌完整 DataFrame，长会话内存与磁盘无界增长。修复：LRU 上限 + 日志轮转。
**P2-03**｜`src/query_engine.py:80,160`｜不完善——dict 浅拷贝使缓存与返回结果共享同一 DataFrame，调用方一旦原地修改即污染缓存（当前调用方只读，属潜伏缺陷）。修复：出入缓存显式 .copy()。
**P2-04**｜`src/llm_client.py:155-187` + `src/data_loader.py:150`｜不完善（含安全专项同源发现）——校验不检查语句数量：`SELECT 1; SELECT 2` 通过校验，靠 sqlite3 单语句限制打回（实测 DatabaseError），白白消耗一轮 LLM 修正调用；多语句防护完全依赖执行层，换执行器即失效。修复：校验层显式拒绝含分号分隔的多语句。
**P2-05**｜`src/llm_client.py:14` + `src/data_cleaner.py:10`｜不完善——未使用导入（json、Optional），pyflakes 视角死导入。
**P2-06**｜`src/data_cleaner.py:53-65`｜不完善——数值列判定不认 pandas 可空扩展类型（Int64/Float64），`strategy='fill'` 时 fillna('unknown') 直接 TypeError（实测）。修复：用 pd.api.types.is_numeric_dtype。
**P2-07**｜`src/data_cleaner.py:89-99`｜不完善——detect_outliers 对未支持的 method 静默返回空表，调用方无法区分「无异常值」与「方法不支持」。修复：未知 method 抛 ValueError。
**P2-08**｜`src/data_loader.py:87,94`｜不完善——pd.to_datetime/to_numeric 使用已弃用的 errors="ignore"（pandas 2.x FutureWarning 实测，未来版本将直接抛错）。修复：try/except 包裹 errors="raise"。
**P2-09**｜`src/query_engine.py:221` + `src/data_loader.py:115`｜不完善——表名 f-string 直接拼进 SQL/PRAGMA，核心库自身不校验标识符（API 层有正则白名单；CLI --table 与直接用库者无防护）。修复：DataLoader 入口统一标识符白名单。
**P2-10**｜`src/llm_client.py:73-74,235` 等｜不完善——核心库 42 处 print（含 [DEBUG] 直接打印 LLM 原始返回与提取的 SQL），API 服务下混入服务器日志、泄露 prompt/schema/用户内容。修复：改 logging。
**P2-11**｜`src/query_engine.py:101-107`｜不完善——LLM API 瞬时故障（网络抖动/429/5xx）零重试直接失败，与「SQL 执行失败自动修正」的容错设计不对称。修复：加 1-2 次指数退避。
**P2-12**｜`src/llm_client.py:65,208-230` + `src/query_engine.py:135`｜不完善——重试闭环无历史记忆：fix_sql 只收最近一次错误，temperature=0.1 近似确定性输出，失败 SQL 极可能原样重放，2 次重试退化为 3 次相同失败。修复：累积失败历史并逐步调温。
**P2-13**｜`src/data_cleaner.py:16-99` + `README.md:66`｜空缺——DataCleaner.clean/handle_missing_values/detect_outliers 未接入任何生产链路（仅测试引用），README 承诺的清洗能力在查询流程中空缺。修复：ask() 加可选开关接入，或修正 README。
**P2-14**｜`src/llm_client.py:180-182`｜不完善——validate_sql 的 code_lines 二次注释过滤是死代码（166 行正则已把 -- 注释全部移除）。

### API 层（12 条）

**P2-15**｜`api/auth.py:138-154`｜不完善（含安全专项同源发现）——日配额为 check-then-act 两段式（SELECT 计数与 UPSERT 累加非原子），query_v1 线程池真并发下 N 个请求可同时通过检查造成超发。修复：单条条件 UPSERT 或 BEGIN IMMEDIATE。
**P2-16**｜`api/auth.py:28,122-130`、`api/metrics.py:11-12`｜不完善（含安全专项同源发现）——限流/配额计数/指标均为单进程内存态：多 worker 失效、重启归零。代码与 README 已如实声明且 Dockerfile 单 worker 自洽，但无防误配护栏。修复：启动断言 worker 数或迁移 Redis。
**P2-17**｜`api/main.py:93-110`、`api/services.py:24-25`｜不完善——无 Exception 兜底处理器：TABLE_NAME 环境变量非法时依赖内抛 ValueError，走 Starlette 默认 500 返回非信封 `{"detail":"Internal Server Error"}`，违反契约 §4.1。修复：补 `@app.exception_handler(Exception)`。
**P2-18**｜`api/main.py:98,109`、`api/auth.py:117`｜不完善——401/422 响应携带的 request_id 在服务端无日志可关联（鉴权失败只记 "api key auth failed"），契约「全链路透传」断链。修复：中间件统一生成并贯穿。
**P2-19**｜`api/datasets.py:43,46,48,56`｜不合理——上传校验失败复用 INVALID_QUESTION(422)，超出契约语义（契约定义其仅用于「问题为空/超长/非法字符」），前端无法按 code 区分。修复：新增 UPLOAD_REJECTED 错误码。
**P2-20**｜`api/datasets.py:18,54`｜不合理——白名单接受 .xls 但 xlrd 未声明（requirements.txt/pyproject 均无），.xls 上传必然 422 解析失败。修复：移除 .xls 或补依赖。
**P2-21**｜`api/datasets.py:52`｜不完善——CSV 解析无编码回退，GBK 编码 CSV（中文 Excel 导出常见）必然 422。修复：utf-8-sig → GBK 回退链。
**P2-22**｜`api/services.py:69` + `README.md:149-154`｜空缺——README 宣传「相同问题不重复调用 API」，但 query_page 固定 enable_cache=False，HTTP 路径缓存永不命中、from_cache 恒 False。修复：API 层启用按问题缓存或修正 README。
**P2-23**｜`api/main.py:132,145,193`｜不完善——错误消息净化（_public_message）仅 query 路由执行，schema/quality/upload 直接回传异常原文（含 pandas 报错原文）。修复：统一出口净化。
**P2-24**｜`api/auth.py:159-162`｜不完善——check_rate_and_quota 为生产未用代码（仅测试调用），误用会把配额扣到所有端点。修复：移入测试工具或删除。
**P2-25**｜`api/services.py:50`｜不完善——quality 端点静默只统计前 10000 行，大数据集结果失真且响应模型无采样标记。修复：SQL 聚合下推或显式标注采样。
**P2-26**｜`api/services.py:102-110`｜不合理——错误映射按 src 层中文字符串匹配（"安全校验" in error），src 层改措辞即静默漂移为 500。修复：src 层抛结构化错误。

### 安全专项（8 条，已去重同源）

**P2-27**｜`api/auth.py:165-174`｜不完善——鉴权失败请求不进入限流，无效 Key 可无限次触发验证流程，无失败锁定与来源审计（Key 256 位熵爆破不可行，风险为日志刷量）。修复：按 IP 计入独立限流桶 + 审计日志。
**P2-28**｜`api/main.py:112-181`、`api/services.py:47-52`｜不完善——health/schema/quality/datasets/metrics/upload 均免配额，quality 每次全表扫描 10000 行 + 全列统计，形成免配额 CPU 放大点。修复：重端点更严限流或计配额。
**P2-29**｜`api/models.py:49`、`src/query_engine.py:123-141`｜不完善——1 次配额可放大为最多 4 次 LLM 调用（首次 + 3 次自动修正），成本放大且 metrics 口径自认偏差。修复：重试纳入配额权重。
**P2-30**｜`scripts/manage_keys.py:31,37,43`｜不完善——吊销需传明文 Key 作为命令行参数（shell history/ps 可见），create 明文打印 stdout。修复：revoke 改 stdin 读取，文档提示清理历史。
**P2-31**｜`api/main.py:70-74`、`Dockerfile.api:20-22`｜不完善——/docs 与 /openapi.json 无鉴权公开，可枚举全部端点与参数模型；健康检查还依赖 /docs 存活。修复：生产关闭 docs 或加防护，另设轻量 /healthz。
**P2-32**｜`src/llm_client.py:165`｜不完善——字符串剥离正则仅处理单引号：双引号内容（SQLite DQS 回退为字符串字面量）不剥离导致误伤（实测 `SELECT "delete" FROM t` 被拒）。修复：剥离扩展到双引号。
**P2-33**｜`api/datasets.py:50-64`｜不完善——上传内容（=/+/-/@ 开头的 CSV 公式注入载荷）未消毒直接入库并原样返回；当前前端无导出路径，属潜伏风险。修复：入库消毒或导出上线前强制处理。
**P2-34**｜`src/query_engine.py:27,225-245`、`api/services.py:66-70`｜不完善——API 查询路径未关闭逐条日志，用户问题与生成的 SQL 明文写 logs/query_log.jsonl，可能含敏感业务信息。修复：API 路径关闭或脱敏 + 保留期。

### 测试体系（7 条）

**P2-35**｜`src/llm_client.py:170-173`｜不完善——validate_sql 缺多语句 PRAGMA/ATTACH 场景用例：禁用词表无 PRAGMA，「SELECT 1; PRAGMA ...」能过校验（兜底依赖 sqlite3 单语句限制）但无测试钉住。修复：补用例或校验层显式拒绝。
**P2-36**｜`api/datasets.py:50-56`｜空缺——上传解析失败分支（read_csv/read_excel 异常转 422）零测试；空 CSV、大写 .EXE 等边界无用例。修复：补畸形内容用例。
**P2-37**｜`src/data_loader.py:115`｜不完善——PRAGMA table_info 的 f-string 插值无核心库层防护测试（仅 API 层正则有用例），直连路径防护依赖上游约定。修复：DataLoader 统一校验 + 补测试。
**P2-38**｜`tests/test_query_engine.py:117`｜不完善——重试耗尽用例用弱析取断言（`error is not None or valid is False`）几乎恒真，回归时漏报。修复：精确断言错误前缀与 retries 数。
**P2-39**｜`tests/test_data_loader.py:15`、`tests/test_query_engine.py:62`｜不完善——夹具用 tempfile.gettempdir() 共享固定路径而非 pytest tmp_path，并行运行互相污染。修复：统一改 tmp_path。
**P2-40**｜`tests/test_api_auth.py:106-131` 等｜不完善——TestClient+create_key+FakeService 样板在 3 个测试文件重复约 90 行。修复：沉淀到 conftest.py。
**P2-41**｜`src/cli.py:1-361`｜空缺——CLI 模块 361 行零测试（含 _is_valid_query 校验逻辑，与 API 层校验重复实现且无一致性保证）。修复：补 CLI 冒烟用例并复用 API 层校验。

### CI 与部署（8 条）

**P2-42**｜`Dockerfile.api:1`｜不完善——基础镜像 python:3.12-slim 未固定 digest/补丁版本，叠加 requirements.txt 全部 >= 下界无锁文件，构建不可复现。修复：固定 digest + pip lock。
**P2-43**｜`.dockerignore:1-21`｜不完善——未排除 tests/、load/、docs/，测试与压测脚本进入生产镜像。修复：追加条目。
**P2-44**｜`Dockerfile.api:21-23`｜不完善——HEALTHCHECK 探测端口写死 8000，启动命令用 ${PORT}，外部覆盖 PORT 后探针失配误判 unhealthy。修复：探针读同一 PORT 变量。
**P2-45**｜`.github/workflows/ci.yml:3-6`｜不完善——触发器全分支 push+PR 且无 concurrency 控制，同一 commit 重复触发、旧 run 不取消。修复：加 concurrency group + cancel-in-progress。
**P2-46**｜`.github/workflows/ci.yml:12-16`｜不完善——Python 作业未启用 pip 缓存，依赖每次冷装（node 侧已正确启用）。修复：setup-python 加 cache: pip。
**P2-47**｜`docs/production_checklist.md:16`｜不完善——清单步骤顺序错误：冒烟 GET /api/v1/health 排在签发管理 Key 之前，而该端点必须带 Key，按清单顺序执行必然 401。修复：调换顺序。
**P2-48**｜`docs/production_checklist.md:23`｜空缺——承诺每天 cron/systemd timer 备份与每月恢复演练，仓库内无任何定时任务配置；恢复步骤只藏在脚本 docstring。修复：deployment.md 补备份/恢复章节与配置样例。
**P2-49**｜仓库根目录｜空缺——缺 LICENSE、CONTRIBUTING、CHANGELOG、SECURITY.md（git ls-files 实测无）。修复：补 LICENSE 明确部署/分发权利边界。

### 前端（7 条）

**P2-50**｜`frontend/src/App.tsx:110,34`｜不完善——主题 setItem 裸调用未包 try/catch（同类写入其他处有保护），存储被禁时 effect 抛未捕获异常；readHistory 不做形状校验，localStorage 键被写坏成非数组时渲染期 filter 抛 TypeError 白屏。修复：包 try/catch + Array.isArray 校验。
**P2-51**｜`frontend/src/App.tsx:163`｜不完善——查询失败写入历史时沿用上一次成功结果的 rowCount/executionTime，历史条目显示错误的行数与耗时。修复：失败项记 0/null。
**P2-52**｜`frontend/src/App.tsx:82-88,150,152`｜不完善——切换数据集不取消在途查询，旧数据集结果返回后仍覆盖展示且无标注。修复：abort 或请求序号比对。
**P2-53**｜`frontend/src/App.tsx:129-131`｜不完善——loading 守卫基于闭包中的 queryStatus，同一渲染帧内双击可发出两个并发查询，后完成者覆盖先完成者。修复：useRef 同步置位 inflight 标志。
**P2-54**｜`frontend/src/components/ResultsPanel.tsx:77,82`｜不完善——结果表以列名做 React key 且按列名取值，SQL 返回重复列名（JOIN 常见）时 key 冲突、后者覆盖前者。修复：key 用行列索引或重名消解。
**P2-55**｜`frontend/e2e/query-flow.spec.ts:50-79`｜不完善——e2e 只覆盖成功/SQL_REJECTED/截断三条路径，401/429/网络错误的界面展示零覆盖。修复：补 stub 用例。
**P2-56**｜`frontend/tsconfig.app.json:2-17`｜不完善——strict 已开启但缺 noUnusedLocals/noUnusedParameters/noFallthroughCasesInSwitch 等 Vite 模板默认严格项。修复：补齐并清理未用导出（如 ChevronIcon）。

### 主智能体独立补充（2 条，子任务未单列，经主智能体读码确认）

**SUP-01**｜`api/main.py:158-160`｜不完善（P2）——配额在查询执行前预扣：`charge_quota` 在 `service.query_page` 之前调用，LLM 调用失败/超时也消耗当日配额且不退还。修复：查询成功后记账，或失败路径回滚。
**SUP-02**｜`src/query_engine.py:219-223`｜不完善（P2，与 P1-09/P2-09 相关但独立）——`QueryEngine.quality_check` 直接执行 `f"SELECT * FROM {self.table_name} LIMIT 10000"`，完全绕过 `validate_sql`；当前仅 CLI 路径可达且表名本地输入，威胁模型内可接受，但若复用到服务端即成注入点。修复：复用统一表名校验。

---

## 六、不合理 / 不完善 / 空缺分类要点

- **不合理（10 条）**：多数是「设计决定与另一处承诺/约束冲突」——缓存键设计 vs 数据集切换（P1-03）、Excel 默认参数 vs 导入承诺（P1-01）、清洗逻辑 vs 数据保真（P1-02）、Render 无磁盘 vs 多数据集功能（P1-20）、伪造指标 vs 分析工具可信度（P1-24）、错误码复用 vs 契约语义（P2-19/P2-26）等。
- **不完善（71 条）**：集中在资源边界（超时/上限/配额）、异步边界、可观测性、并发竞态与测试健壮性。
- **空缺（10 条）**：集中在「README/契约/清单承诺了但没做」与 CI 门禁缺失，详见第一节统计表下方速览。

## 七、未完成审查项及原因

**子任务级未完成项：无**（6/6 全部完成，无跳过）。

子任务内部未覆盖/未实测项（均已在其结论中如实声明）：

| 未覆盖项 | 原因 | 影响 |
|---|---|---|
| 前端生产构建（npm run build，含 tsc --noEmit 门禁） | 本环境 npm 不可用（spawn ENOENT） | 构建通过性未实测；vitest 已由测试子任务实测（3 failed） |
| Playwright e2e 实跑 | 环境限制 + 依赖 Windows-only 脚本注入 E2E_API_KEY | e2e 通过性未实测（其本身也是 P1-15 问题） |
| coverage 覆盖率数据 | 未安装/未运行 coverage 工具 | 覆盖空缺为人工比对源码与测试清单的结论 |
| docker build 实际构建 | 只读评审约束 | 非 root/健康检查结论来自 Dockerfile 静态分析 |
| backup_db.py 实际运行 | 会在 backups/ 创建文件，违反只读约束 | 备份逻辑为静态审查（copy→mtime 保留逻辑正确） |
| 动态/网络层验证 | 未对任何运行中的服务发起 payload | 所有安全结论为静态推演 + 本地函数级实测 |
| 依赖漏洞扫描（pip-audit/npm audit/bandit） | 未运行，不作断言 | 依赖版本全部为 >= 下界无锁定，扫描留给后续 |
| README 全文逐条核对 | 不在指定子任务范围 | 已核对项见 P1-12/P2-13/P2-22 |
| 真实 DeepSeek API 调用、Render 云端部署 | 未发起网络调用/未部署 | LLM 真实链路行为、云端健康检查失败均为配置级推断 |
| WITH RECURSIVE 无终止查询的实际执行 | 会挂起评审进程 | 结论基于校验实测放行 + 执行层无超时的代码路径 |

## 八、修复路线建议

1. **上线前必须（P0 + 部署相关 P1）**：修 render.yaml 健康检查（P0-01，顺带加免鉴权 /api/health，同时解决 P2-31/P2-47）；给 API 服务挂持久磁盘或明确示例数据定位（P1-20）；修正 deployment.md 验收步骤（P1-16）。
2. **第一周（高价值 P1）**：LLM 客户端加 timeout 并实现 QUERY_TIMEOUT（P1-04，一并消化安全侧无超时问题的执行层部分 P1-05）；上传改为流式限量 + 计配额（P1-07/P1-10）；async 端点与鉴权依赖去阻塞（P1-06）；SQL 执行加表白名单/set_authorizer（P1-09）；修 load_excel 与清洗 'None' 污染（P1-01/P1-02）。
3. **第一周（门禁）**：CI 改跑全量 pytest（P1-13）；修 vitest 配置并把前端测试纳入 CI（P1-14/P1-17）；补 .gitignore 的 .idea（P1-18）；更新 README 数字（P1-12）。
4. **第二周（P2 批次）**：配额原子化（P2-15）、缓存键修复（P1-03 的缓存侧）、错误信封兜底与日志（P1-08/P2-17）、前端 AbortController/超时接线（P1-21/P1-23）、备份改 backup API（P1-19）。
5. **长期**：缓存 LRU 化、核心库 print→logging、结构化错误类型替代字符串匹配、多租户前重新评估表白名单与 Key 生命周期。

---

## 附：证据与复核说明

- **确定性实测（工作流脚本执行）**：`python -m pytest tests/ -q` → exit 0、99 passed；`npx vitest run` → 3 failed | 1 passed（由测试子任务执行）；git 历史采样 41 条。
- **子任务内本地函数级实测**：后端与安全子任务在各自会话内实测了 SQL 校验的 10+ 组输入（堆叠语句、注释混淆、WITH RECURSIVE、api_keys 读取、双引号 DQS、load_extension）、pandas 2.3.2 的 read_excel 返回类型、清洗 'None' 污染、Int64 TypeError 等；安全子任务确认 load_extension 运行时被 Python sqlite3 默认拒绝（纵深防御缺失而非可利用漏洞）。
- **主智能体独立交叉核查**：P0-01、P1-03、P1-06、SUP-01、SUP-02 在子任务返回前已由主智能体直接读码确认；P1-04/P1-05/P1-07/P1-09 的关键证据行（llm_client.py:43、data_loader.py:148-150、main.py:189、llm_client.py:155-187）与主智能体独立阅读结论一致。
- **报告生成方式**：六个子任务按用户指定顺序串行执行并返回结构化结论（无未完成项），由主智能体直接汇总成文，未派额外汇总子智能体；跨层同源的 9 组重复发现已合并并注明。
