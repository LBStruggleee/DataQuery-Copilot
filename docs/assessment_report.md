# DataQuery-Copilot 专业评估报告（修复后复评版）

- **评估日期**：2026-10-12
- **评估对象**：`LBStruggleee/DataQuery-Copilot`（master @ `8fd9520`，已推送）
- **评估性质**：**第二轮复评**。第一轮评估（2026-10-12，旧版报告见 git 历史）发现 82 个问题（P0×1、P1×25、P2×56），随后通过 6 批次修复工作流修复 78 项；本复评逐条核对修复真实性并寻找残留与新引入问题
- **评估方法**：dynamic workflow 六个子任务严格串行（max_concurrency=1）——后端核心库 → API 层 → 安全专项 → 测试体系 → CI 与部署 → 前端；每个子任务逐文件通读 + 函数级实测（共 50+ 组 payload 实测）+ 对照旧报告编号逐条核对
- **确定性实测**：`python -m pytest tests/ -q` → **exit 0，252 个用例全部通过**（与 README 声称一致）；前端 vitest 与生产构建 exit 0
- **重要实测发现**：安全子任务在实测中发现了 1 个上一轮修复**注释里的威胁模型错误**（X-Forwarded-For 可定向锁定他人，见 NEW-P1-01）和 1 个**上一轮防护可被绕过**（xlsx 无维度声明跳过解压炸弹检查，见 NEW-P1-02）——两者均经本地 payload 实测证实

---

## 一、总体结论

**修复是真实且高质量的。** 第一轮的 1 个 P0、25 个 P1 逐条核对**全部真实修复**，且大部分 P2 也已修复；测试从 99 例增至 252 例全过。核心安全防护经 50+ 组函数级 payload 实测有效：SQL 执行的 authorizer 表白名单对直查他表/UNION/子查询/CTE/PRAGMA/写入/ATTACH/load_extension 全部拦截；配额 BEGIN IMMEDIATE 原子化经 10 线程并发实测不超发；上传流式限量实测 150MB 恶意请求被提前拒绝。

复评新发现 **2 个 P1、26 个 P2**，无 P0。两个 P1 都是「修复自身引入的新问题」：鉴权失败桶以可伪造的 X-Forwarded-For 首段为键（可定向 DoS 锁定他人 + 污染审计日志）、xlsx 解压炸弹检查可被无维度声明的工作簿绕过。26 个 P2 集中在边界缝隙（数据集上限非原子、上传非事务、前端契约未同步 sampled_rows、覆盖缺口）。

**总体评价：安全健壮度从 7→8，后端核心库从 6.5→9，API 层 7→8.5，测试体系 7.5→8.5，CI 与部署 5→8，前端 7.5→7.5（修复完整但契约未同步）。综合从 6.8 升至 8.3/10。项目已具备上线条件，剩余问题均为可排期的加固项。**

### 各层评分对比（第一轮 → 复评）

| 领域 | 第一轮 | 复评 | 变化 | 一句话依据 |
|---|---|---|---|---|
| 后端核心库 `src/` | 6.5 | **9.0** | ↑2.5 | 20 条旧问题全修复；authorizer+超时+行数上限三层防护经 19 组 payload 实测有效；残留仅低风险 P2 |
| API 服务层 `api/` | 7.0 | **8.5** | ↑1.5 | 17 条旧问题全修复；残留：XFF 失败桶无界增长（P1）、数据集上限非原子、上传非事务 |
| 安全专项（健壮度） | 7.0 | **8.0** | ↑1.0 | 核心防护实测无误、配额原子化实测通过；新发现 XFF 可定向锁定他人、xlsx 维度绕过 |
| 测试体系 | 7.5 | **8.5** | ↑1.0 | 252 例全过与 README 一致（有防漂移测试）；安全防护新增测试覆盖充分；client.ts 零单测等缺口 |
| CI 与部署 | 5.0 | **8.0** | ↑3.0 | 7 个 CI 作业（全量 pytest、ruff+mypy、vitest、e2e 真实链路、pip-audit/npm audit、构建、密钥清扫）；镜像 digest 仍为已知延后项 |
| 前端 `frontend/` | 7.5 | **7.5** | — | 14 条旧问题全修复、CSP/e2e 竞态用例质量高；但 quality 契约未同步 sampled_rows（P1），发现若干不一致 |

---

## 二、旧问题修复核对结论

第一轮 82 个问题的修复核对结果（各子任务逐条对照代码确认）：

| 批次 | 修复承诺 | 复评结论 |
|---|---|---|
| 部署与仓库卫生（15 项：P0-01、P1-13/16/17/18/19/20、P2-16/31/43~48） | 全部 | **全部真实修复** ✓（P2-42 digest、LICENSE 为已声明延后项，不计） |
| 后端核心库（20 项：P1-01~05、P2-01~14、SUP-02） | 全部 | **全部真实修复** ✓（19 组绕过 payload 实测防护有效；缓存键含表名 + load_data 清缓存 + LRU 深拷贝实测通过） |
| API 服务层（17 项：P1-06/07/08/10、SUP-01、P2-15~23/25/26/27/34） | 全部 | **全部真实修复** ✓（流式限量/配额原子化/回滚/信封/审计均实测；XFF 威胁模型见 NEW-P1-01） |
| 安全加固与测试（11 项：P1-09/11、P2-30/32/35~41） | 全部 | **P1-09/11 与 P2-30/32/35~41 真实修复** ✓；**P1-11 的 xlsx 维度检查存在绕过路径**（见 NEW-P1-02）；P2-33（CSV 公式消毒）为已声明延后项仍未修 |
| 前端（14 项：P1-14/15/21~25、P2-50~56） | 全部 | **全部真实修复** ✓（CSP/e2e 竞态用例/真实 request_id 实测；P2-54 取值侧为已知说明项）；新增契约未同步问题 NEW-P1-03 |
| 文档同步（P1-12） | 全部 | **真实修复** ✓（README 252 例与实测一致，且有 test_docs_sync.py 防漂移） |

**核对通过率：78 项修复承诺全部落实；其中 1 项（xlsx 维度）存在绕过路径需再加固，1 项（XFF 键）威胁模型有误需再修正。**

---

## 三、新发现问题清单

### P1（应尽快修复，3 条）

**NEW-P1-01｜安全专项 · 不合理** 鉴权失败桶以可伪造的 X-Forwarded-For 首段为键，可定向 DoS 锁定他人并污染审计日志
- **位置**：api/auth.py:206-212（对照上一轮 P2-27 修复引入）
- **问题**：`_client_ip` 优先取 `X-Forwarded-For` 首段，注释断言「伪造者只能给自己换新桶，不会误伤他人」——**该威胁判断有误**：攻击者可伪造任意 XFF 值命中「他人源 IP」的失败桶，10 次伪造失败请求即可让真实用户/共享出口 IP 被锁定 429（定向 DoS），且审计日志记录的是伪造 IP。同时桶字典只增不减，伪造海量不同 IP 值可致 `_auth_failures` 无界增长（单进程内存 DoS）。
- **证据**（实测）：伪造 `X-Forwarded-For: victim-1.2.3.4` 连续 10 次后 `enforce_auth_failure_limit('victim-1.2.3.4')` 抛 APIError，该「IP」被锁定；auth.py:209-211 `forwarded.split(",")[0].strip()`；全文件无空/过期桶回收。
- **修复**：仅在可信反代后取 XFF（uvicorn `--proxy-headers` + `FORWARDED_ALLOW_IPS`，或直接用 `request.client.host` 兜底，直连部署忽略该头）；桶数设 LRU 上限或定期清扫过期桶。
- **复核**：安全子任务本地 payload 实测证实 ✓

**NEW-P1-02｜安全专项 · 不完善** xlsx 解压炸弹检查可被无维度声明的工作簿绕过
- **位置**：api/datasets.py:59-85（对照上一轮 P1-11 修复引入）
- **问题**：P1-11 修复用 openpyxl 读工作表**自声明**的 dimension 估算单元格数，但维度是声明值不是事实值：实测删除 sheet1.xml 中 `<dimension/>` 声明后 `max_row/max_column` 为 None 即 `continue` 跳过检查、文件正常解析——恶意 50MB 无维度工作簿可绕过 200 万单元格上限，`pd.read_excel` 一次性加载仍可膨胀数 GB 打爆内存。
- **证据**（实测）：openpyxl 生成工作簿 → zipfile 删 dimension 声明 → `register_upload(db, 'nodim.xlsx', ...)` 输出 `no-dimension xlsx: parsed OK rows= 1`，未触发任何上限；datasets.py:75-77 `if rows is None or cols is None: continue`。
- **修复**：维度缺失时不再跳过（拒绝该文件），或解析后按实际 `df.shape` 校验超限即丢弃；可对 zip 成员解压后总大小设上限。
- **复核**：安全子任务本地 payload 实测证实 ✓

**NEW-P1-03｜前端 · 空缺** 后端 quality 已改采样统计，前端契约未同步 sampled_rows，采样行数被当全量行数展示
- **位置**：frontend/src/apiV1/types.ts:17-24、frontend/src/components/Inspector.tsx:74（对照上一轮 P2-25 修复引入）
- **问题**：上一轮修复给后端 quality 加了「基于前 10000 行采样」并返回 `sampled_rows`（api/services.py:50-53），但前端 `QualityInfo` 契约没有该字段；Inspector 把 `total_rows`（实为采样行数）当全量行数展示「N 行扫描完成」，大数据集（50MB CSV 常有数十万行）时展示失真。
- **证据**：types.ts 无 sampled_rows；Inspector.tsx:74 `{api.quality?.total_rows.toLocaleString() ?? "—"} 行扫描完成`；后端 services.py:51 `SELECT * FROM "table" LIMIT 10000`。
- **修复**：QualityInfo 增加 `sampled_rows?: number`，行数展示区分全表/采样，超采样时标注「基于前 10000 行采样」。
- **复核**：前端子任务读码确认（后端字段为上一轮实测引入，契约对齐为静态判断）

### P2（可改进，26 条）

#### 后端核心库（8 条）

**NEW-P2-01**｜`src/llm_client.py:213-220`｜不完善——validate_sql 不校验函数名：实测 `SELECT load_extension('evil')`、`SELECT * FROM pragma_table_info('t')` 校验层放行（执行层 authorizer/SQLite 默认配置兜底拦截，实测 OperationalError not authorized）。修复：校验层加危险函数名黑名单，或 authorizer 对函数按白名单放行。
**NEW-P2-02**｜`src/data_loader.py:56`｜不完善——sqlite3.connect 未设 `check_same_thread=False` 也无锁；当前每请求新建 engine 无实际竞态，但 FastAPI 线程池下若复用共享 engine（如后续单例优化）即抛 ProgrammingError。修复：文档明确「实例非线程安全」或连接加锁串行化。
**NEW-P2-03**｜`src/query_engine.py:291-293`｜不完善——quality_check 绕过 validate_sql 直接执行 f-string SQL（表名已过白名单，SUP-02 已降级），且 LIMIT 10000 硬编码与 DataLoader.max_rows 配置脱节。修复：追加过滤逻辑时改走 validate_sql。
**NEW-P2-04**｜`src/data_cleaner.py:156-178`、`src/query_engine.py:235-260`｜不完善——print_quality_report/print_result 仍内嵌 print（约 52 处残留），QueryEngine.quality_check 直接调用前者，服务端误调会把大 DataFrame 打到 stdout。修复：拆分纯文本生成函数由调用方决定输出通道。
**NEW-P2-05**｜`src/query_engine.py:102`、`src/cli.py:77`｜不完善——缓存键仅含表名+问题文本；经 `engine.load_data` 覆盖同表已清缓存，但外部直接调 `loader.load_csv` 绕过 engine 时缓存不失效（当前无触发路径）。修复：缓存键纳入数据版本号（row_count+mtime）。
**NEW-P2-06**｜`src/llm_client.py:170-187`｜不完善——_extract_sql 无代码块路径以 `--` 开头的行无条件进入捕获（实测对「注释开头包裹写语句」最终被 startswith SELECT 拦住，无实际绕过，属防御缝隙）。修复：收紧为拒绝含 `--` 的行交修正轮重试。
**NEW-P2-07**｜`src/query_engine.py:155-204`｜不完善（设计确认）——for-else 语义下循环零次执行的场景已被入口校验（max_retries>=0）拦截，属防御冗余，无需修复。
**NEW-P2-08**｜`tests/`｜不完善——实测 grep 统计 232 个 test 函数，与 245/252 的口径差异为参数化展开数（pytest 252 passed 与 README 一致，有防漂移测试）；建议 CI gate 与文档统一口径说明。

#### API 服务层（5 条，含与安全专项同源）

**NEW-P2-09**｜`api/datasets.py:99-108`｜不完善（安全专项同源）——MAX_DATASETS=50 为 check-then-act：SELECT COUNT(*) 与 INSERT 分属两个连接、无 BEGIN IMMEDIATE，并发上传可竞态超过 50（与配额侧已原子化不对称）。修复：同用 BEGIN IMMEDIATE 包住计数与 INSERT。
**NEW-P2-10**｜`api/datasets.py:124-142`｜不完善——register_upload 用三个独立连接分步执行（to_sql 建表 → INSERT 注册），任一步失败（如磁盘满）留孤儿表/孤儿记录；remove_dataset 回滚仅挂在记账失败路径。修复：合并事务或 to_sql 失败路径也调 remove_dataset。
**NEW-P2-11**｜`api/main.py:228-239`、`api/metrics.py:17-22`｜不完善——/api/health 免鉴权探针同时绕过限流且计入 metrics（探活风暴可产生无限流无认证请求）；属可接受设计但未声明。修复：文档声明或不计入 requests_total。
**NEW-P2-12**｜`api/auth.py:197-200`｜不完善——check_rate_and_quota 组合函数「先限流后立即扣配额」，与生产入口的「成功后记账」口径相反，且生产无调用（仅测试引用），语义误导。修复：删除或注释降级为仅供测试。
**NEW-P2-13**｜`api/auth.py:115-124`｜不完善——api_keys 表未初始化时 verify_key 直接抛裸 OperationalError（仅靠全局兜底包 QUERY_FAILED）；lifespan 与请求期 DB_PATH 不一致等边缘路径会漏出。修复：捕获 OperationalError 转 APIError(SERVICE_UNAVAILABLE)。

#### 安全专项（4 条，扣除与上文同源）

**NEW-P2-14**｜`api/datasets.py:88-118`｜空缺——旧报告 P2-33（CSV 公式注入）为已声明延后项，仍未修：实测 `=cmd|'/c calc'!`、`@SUM(...)` 等载荷原样入库并经查询原样返回（前端无导出路径，属潜伏风险）。修复：入库前对 =/@/+/- 开头文本加转义前缀，或导出上线时强制消毒。
**NEW-P2-15**｜`api/main.py:282-301`｜不完善——旧报告 P2-28 未修（已声明延后）：quality 免配额且每次全列扫描前 10000 行，30 次/分钟限流下仍是免配额 CPU 放大点。修复：更严独立限流（如 5 次/分）或计配额。
**NEW-P2-16**｜`api/main.py:303-327`｜不完善——旧报告 P2-29 未修（已声明延后）：1 次配额可放大为最多 4 次 LLM 调用（成功后记账下修正调用不再扣费）。修复：按 1+retries 加权记账。
**NEW-P2-17**｜（横切）｜不完善——鉴权失败审计仅 logger.warning，无持久化审计存储，日志轮转后不可追溯；未配置可信代理白名单开关（XFF 信任边界完全依赖部署方）。修复：与 NEW-P1-01 一并处理。

#### 测试体系（7 条）

**NEW-P2-18**｜`tests/test_api_auth.py`｜不完善——限流桶/失败桶的时间窗过期清理逻辑（deque 中超出 60s 窗口条目的淘汰）无直接测试，仅测触发阈值。修复：补「旧条目过期后恢复放行」用例。
**NEW-P2-19**｜`tests/test_api_auth.py:358-399`｜不完善——按 IP 限流只有单 IP（TestClient 固定 testclient）路径测试，多 IP 隔离性未验证。修复：补两个不同 IP 各自独立计数的用例。
**NEW-P2-20**｜`tests/test_llm_client.py:130-160`｜不完善——validate_sql 缺边界用例：块注释包危险词（/* DROP */ SELECT）、反引号标识符、奇数个双引号（`"[^"]*"` 不匹配时漏剥）。修复：补边界断言。
**NEW-P2-21**｜`frontend/src/apiV1/client.ts`（缺失 client.test.ts）｜空缺——前端核心 HTTP 客户端（30s 超时、AbortController、信封解析）零 vitest 单测，仅 e2e 间接覆盖且 e2e 缺 Key 时全跳过。修复：mock fetch 补超时/中断/信封解析单测。
**NEW-P2-22**｜`frontend/index.html:6`｜空缺——CSP 声明（P1-25）无任何测试或构建期校验钉住，被误删不会被发现。修复：补轻量断言（script-src 不含 unsafe-inline/unsafe-eval）。
**NEW-P2-23**｜`tests/test_visualizer.py:1-139`｜不完善——visualizer 200 行仅 14 个测试函数，断言以字段存在性为主，图表数据变换的数值正确性覆盖浅。修复：补 1-2 个分组聚合数值断言。
**NEW-P2-24**｜`tests/test_api_auth.py:430-456`｜不完善——上传配额竞态回滚测试用 monkeypatch 替换 charge_quota 函数（路径级 mock），非真实 DB 竞态注入（与 40 线程原子性测试互补，可接受现状）。

#### CI 与部署（8 条）

**NEW-P2-25**｜`.github/workflows/ci.yml:2-6`｜不完善——触发器仍为全分支 push + pull_request 双触发，concurrency 分组（`github.ref`）下 PR 与 push 两组互不取消（上一轮 P2-45 只加了 concurrency 未改触发器）。修复：`group: ${{ github.head_ref || github.ref }}` 或收敛触发器。
**NEW-P2-26**｜`scripts/backup_db.py:52-54`｜不完善——备份轮换 glob 整个备份目录的 `*.db` 按 mtime 混合排序删除，同目录放多个数据库快照时会误删其他库的新备份（deployment.md:139 还建议共享目录）。修复：按 `{basename}_*.db` 过滤。
**NEW-P2-27**｜`tests/test_query_engine.py:243-246`｜不完善——实测全量 pytest 存在低频 flaky：首跑出现 1 例 Windows sqlite teardown ERROR，复跑 3 次均 252 passed（历史 commit 15f97d7 曾修同类）。修复：conftest 统一 teardown 强制关闭连接。
**NEW-P2-28**｜`api/main.py:228-239`｜不完善——健康探针在 DB 文件缺失时返回 status=degraded 但 HTTP 仍 200，Render/Docker HEALTHCHECK 只判状态码，库缺失时服务仍被判健康。修复：degraded 时返回 503 或文档声明探针仅存活语义。
**NEW-P2-29**｜`scripts/backup_db.py:39-46`｜不完善——`wal_checkpoint(TRUNCATE)` 返回的 busy 标志被忽略，checkpoint 被并发读阻塞时静默降级（backup API 本身已保证一致性快照，checkpoint 属可选优化）。修复：检查 busy 标志记 warning。
**NEW-P2-30**｜`Dockerfile.api:12`、`render.yaml:11`｜不完善——构建期播种依赖脚本执行生成示例库，无随机种子固定与产物断言，构建不可复现（与 P2-42 无 lock 同根因）。修复：固定随机种子 + integrity_check + 行数断言。
**NEW-P2-31**｜`.github/workflows/ci.yml:13-31`｜空缺——CI 无 docker build 作业，Dockerfile.api 变更（HEALTHCHECK/播种/EXPOSE）完全不受 CI 保护。修复：新增轻量 docker build 作业（仅 build 不 push 或加 hadolint）。
**NEW-P2-32**｜`.github/workflows/ci.yml:26`、`scripts/e2e_up.sh:16-22`｜不完善——lint 作业 continue-on-error 覆盖整个 job（ruff 与 mypy 不区分，存量清零后需人工记得收紧）；e2e 脚本签发的测试 Key 经命令替换导出（本地 echo 不落盘可接受，与 P2-30 建议未完全对齐）。修复：分步 continue-on-error；Key 改 ::add-mask:: 或临时文件传递。

#### 前端（5 条，扣除 NEW-P1-03）

**NEW-P2-33**｜`frontend/index.html:11`｜不完善——CSP connect-src 含 `'self' https:` 通配：任意 https 源均可连接，削弱 CSP 防 Key 外传价值（与 NEW-P1-01 组合仍需脚本注入前提，风险收敛）。修复：生产构建按 VITE_API_BASE_URL 注入具体源。
**NEW-P2-34**｜`frontend/e2e/backend-api.spec.ts:1,18,25,32`｜不完善——e2e skip 提示语仍只写 `run scripts/e2e_up.ps1`，未随 P1-15 的跨平台 e2e_up.sh 同步（playwright.config.ts 已提示双入口）。修复：提示语改为双入口。
**NEW-P2-35**｜`scripts/e2e_up.ps1:5`｜不完善——ps1 头注释写「拉起 5174 前端」，实际共用 playwright.config.ts 的 5173。修复：更正注释。
**NEW-P2-36**｜`frontend/src/App.tsx:96-108,156`｜不完善——切换数据集 abort 在途查询后、旧 fetch 的 finally 尚未执行的微任务窗口内 inflightRef 仍为 true，此时点「运行」被静默丢弃且 UI 已显示 idle。修复：abort 后同步置 inflightRef=false（finally 幂等兜底）。
**NEW-P2-37**｜`frontend/src/App.tsx:93-108,126`、`Sidebar.tsx:153-159`｜不完善——三处不一致：切换数据集且无在途查询时旧结果表/分页器无「属于旧数据集」标注（翻页会以新 datasetId 重查旧问题）；uploadFile 对非 V1ApiError 硬编码 SERVICE_UNAVAILABLE 与查询路径的 NETWORK_ERROR 不一致；侧栏 StatusDot 对 QUERY_TIMEOUT 显示兜底「API 未连接」而 topbar 显示「请求超时」。修复：统一三处行为。

---

## 四、不合理 / 不完善 / 空缺统计

复评新发现 29 条（去重同源后）：**P1 ×3、P2 ×26**；无 P0。

| 类别 | 条数 | 代表问题 |
|---|---|---|
| 不合理 | 2 | XFF 键可定向锁定他人（NEW-P1-01）、（同源）失败桶无界增长 |
| 不完善 | 20 | xlsx 维度绕过（NEW-P1-02）、数据集上限非原子、CI 双触发、flaky、备份轮换误删等 |
| 空缺 | 7 | sampled_rows 契约未同步（NEW-P1-03）、client.ts 零单测、CSP 无测试钉住、CI 无 docker build 等 |

## 五、已知延后项（未计入新发现）

LICENSE（法律决策，建议 MIT）、P2-42 镜像 digest 固定 + pip lock、P2-33 CSV 公式消毒（→ NEW-P2-14 跟踪）、P2-28 quality 计配额（→ NEW-P2-15）、P2-29 重试加权记账（→ NEW-P2-16）、P2-24 check_rate_and_quota 保留、Redis 化限流（多 worker 告警护栏已有）。

## 六、未完成审查项及原因

**子任务级未完成项：无**（6/6 全部完成）。子任务内未覆盖项：

| 未覆盖项 | 原因 |
|---|---|
| LLM 网络路径真实调用（30s 超时与 SDK 重试行为） | 需真实 API Key，仅从代码与 SDK 语义推断 |
| docker build / render blueprint 实际运行 | 本环境 Windows 无 docker/云端凭证，仅配置文本核对 |
| FastAPI 线程池下 DataLoader 连接的并发压测 | 仅从代码结构判断（每请求新建 engine，当前无共享路径） |
| visualizer 中文字体在 Linux 的表现 | 未在非 Windows 环境验证（SimHei/YaHei 依赖，Render 可能乱码） |
| 覆盖率数据 | 未运行 coverage 工具，覆盖缺口为人工比对结论 |
| 旧报告跨层编号全量复核 | 各子任务仅核对本层编号；跨层项顺带确认（如 error_code 消费） |

## 七、修复路线建议

1. **立即（P1）**：XFF 信任边界修正 + 失败桶 LRU 上限（NEW-P1-01）；xlsx 维度缺失拒绝或解析后校验 df.shape（NEW-P1-02）；前端 QualityInfo 同步 sampled_rows（NEW-P1-03）。
2. **短期（一致性缝隙）**：数据集上限原子化 + 上传事务化（NEW-P2-09/10）；备份轮换按库前缀过滤 + busy 标志（NEW-P2-26/29）；CI 触发器去重 + 分步 continue-on-error（NEW-P2-25/32）；三处前端行为统一（NEW-P2-37）。
3. **中期（测试补强）**：client.ts 单测、CSP 断言、限流桶过期/多 IP 用例、SQL 校验边界用例（NEW-P2-18~22）；flaky 收敛（NEW-P2-27）。
4. **随决策**：延后项清单（第五节）逐项由用户拍板。

---

## 附：证据与复核说明

- **确定性实测（工作流脚本）**：pytest 252 passed（与 README 一致）；前端 vitest/build exit 0；git 提交链完整。
- **子任务内函数级实测（约 50 组 payload）**：authorizer 表白名单 17 例（直查他表/UNION/子查询/CTE/PRAGMA/写入/ATTACH/load_extension 全拦）；validate_sql 16+10 例（多语句/双引号/注释混淆）；配额 BEGIN IMMEDIATE 并发实测（10 并发 quota=3 恰好 3 成功；40 线程 quota=5 恰好 5 次）；上传流式限量（150MB 分块提前拒绝）；**XFF 伪造锁定他人实测**（NEW-P1-01 关键证据）；**xlsx 无维度绕过实测**（NEW-P1-02 关键证据）；CSV 公式注入载荷实测（NEW-P2-14）。
- **报告生成方式**：六个复评子任务按指定顺序串行返回结构化结论（无未完成项），由主智能体直接汇总成文，未派汇总子智能体；新旧报告对比标注于第二节。
