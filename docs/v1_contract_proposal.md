# v1 API 契约技术方案

> 状态：方案评审中（配套有一个可交互的 mock 演示：前端 `?contract=v1`，实现见 `frontend/src/contractV1/`）
> 目标：以后端分层 + 统一契约为核心，理顺 API 与前后端边界；性能与独立演进只做最小闭环。

## 1. 背景与目标

DataQuery-Copilot 已打通「自然语言 → SQL → 执行 → 清洗 → 可视化」，具备 CLI、FastAPI、React 工作台三端。
当前 API 层是薄适配（`api/services.py` 直接拼装 `DataLoader / QueryEngine / Visualizer`），
前后端靠手写两份类型对齐（`api/models.py` + `frontend/src/types.ts`），随功能增加，边界会越来越模糊。

本次优化目标：

- 后端职责分层，路由 / 服务 / 领域各归其位；
- 所有接口统一响应信封 + 错误码，前端按码展示；
- 接口版本化，前后端可独立演进；
- 查询结果分页 + 行数上限，消除大结果内存风险；
- TS 类型由 OpenAPI 生成，辅以契约测试，杜绝两边漂移。

## 2. 现状问题

| # | 位置 | 问题 |
|---|------|------|
| 1 | `api/main.py` | 同步端点 + 每次请求新建 `DataQueryService / QueryEngine`，`services.query` 写死 `enable_cache=False`，HTTP 侧吃不到缓存 |
| 2 | `api/main.py` | 错误处理不统一：schema 404、quality/query 统一 500 兜底且吞掉细节，前端只能展示自由文本 |
| 3 | `api/services.py` | `query` 全量 `to_dict(orient="records")`，大结果直接打满内存；`quality` 一次读 10000 行 |
| 4 | `api/models.py` vs `frontend/src/types.ts` | 同一份契约手写两遍，`mockData.ts` 是第三份形状，必然漂移 |
| 5 | 前端 `api.ts` | `loadWorkspaceOverview` 并发打 3 个接口，每个都在后端单独开一次 DB 连接 |
| 6 | 全局 | 无版本号（`/api/*`），无分页，无请求 ID，日志落 `logs/` 相对路径 |

## 3. 总体方案

```
                ┌─────────────────────────────────┐
                │        Frontend (React)         │
                │ 消费 codegen 类型 + 契约测试     │
                └───────────────┬─────────────────┘
                                │  /api/v1/* 统一信封
                ┌───────────────▼─────────────────┐
                │      API 层 (FastAPI)           │
                │ 路由: 校验 / 版本 / 错误映射     │
                │ 服务: 编排 loader/engine/viz    │
                └───────────────┬─────────────────┘
                                │
                ┌───────────────▼─────────────────┐
                │   领域层 (src/, 保持不动)        │
                │ DataLoader / QueryEngine / ...  │
                └─────────────────────────────────┘
```

三条线：方向 1（分层 + 契约统一）为主线；方向 2 并入分页/行数上限 + 错误统一；
方向 3 只做 OpenAPI 生成 TS 类型 + 契约测试。鉴权、限流、多数据源、缓存共享、同步改异步本次不做。

## 4. 详细设计

### 4.1 统一响应信封

所有 v1 接口返回同一信封（已在演示中定稿，见 `frontend/src/contractV1/types.ts`）：

```json
{
  "version": "v1",
  "code": "OK",
  "message": "ok",
  "data": { },
  "request_id": "req_m7x2ab1q"
}
```

- `code = "OK"` 表示成功；否则为错误码，`data` 为 `null`；
- `message` 给人看，`code` 给程序看——前端一律按 `code` 分支展示；
- `request_id` 全链路透传，用于定位问题。

### 4.2 错误码表

| 错误码 | HTTP 状态 | 场景 |
|--------|-----------|------|
| `INVALID_QUESTION` | 422 | 问题为空 / 超长 / 非法字符 |
| `SQL_REJECTED` | 422 | 安全校验未通过（非 SELECT） |
| `TABLE_NOT_FOUND` | 404 | 表不存在 |
| `QUERY_TIMEOUT` | 504 | 执行超时 |
| `RESULT_TRUNCATED` | 200 | 成功但结果被截断（`data.truncated = true`，属警告而非失败） |
| `SERVICE_UNAVAILABLE` | 503 | LLM 未配置 / DB 未就绪等依赖缺失 |

映射规则集中放在路由层，服务层只抛领域异常，不直接写 HTTP 状态。

### 4.3 版本化

- 新接口挂 `/api/v1/*`，旧 `/api/*` 保留一个版本并标记 deprecated；
- 破坏性变更只发生在新版本号下，前端按版本升级。

### 4.4 分页与行数上限

- `POST /api/v1/query` 新增参数：`page`（默认 1）、`page_size`（默认 10，上限 50）；
- 服务端硬上限 `MAX_ROWS = 100`：超限只返回前 100 行，`data.truncated = true`，`code` 仍为 `OK`，
  `message` 注明"结果超过 100 行上限，仅返回前 100 行"；
- 返回 `rows`（当前页）、`row_count`（截断后总量）、`page`、`total_pages`；
- 前端表格底部加分页条（演示已实现，见 `ResultsPanel` 的 `paging` 属性）。

### 4.5 OpenAPI 生成 TS 类型

- 后端以 Pydantic 模型为唯一契约源，FastAPI 原生导出 OpenAPI 描述；
- 前端类型由 OpenAPI 生成，替换手写 `frontend/src/types.ts`；
- 生成产物提交到仓库（而不是每次构建时生成），diff 可 review；
- `mockData.ts` 与生成类型同源，演示数据不再是"第三份形状"。

### 4.6 契约测试

- 后端：OpenAPI 快照测试——契约变更必须显式更新快照，防止无意破坏；
- 前端：contract test——用录制的 v1 信封样本校验解析、分页、错误码分支；
- mock 客户端（`contractV1/mockClient.ts`）保留，作为前端独立开发 / 联调前的替身。

## 5. 前端改造点

- `api.ts` 收敛为 v1 客户端：统一解信封、按 `code` 抛错、支持取消与分页参数；
- `ResultsPanel`：分页条 + 截断提示 + 错误码展示（演示已实现，为可选 props，v0 行为不变）；
- `QueryComposer`：示例问题可配置（演示已实现）；
- 类型引用全部切到生成产物，删除手写重复定义。

## 6. 非目标

鉴权、限流、多数据源、缓存共享策略、同步端点改异步、前端视觉大改。

## 7. 实施步骤（建议顺序）

1. 后端：统一信封 + 错误码 + 路由层错误映射（不改 URL，前端无感）；
2. 后端：`/api/v1/*` + 分页/上限，老接口标记 deprecated；
3. 前端：接入 codegen 类型 + v1 客户端，表格分页、错误码展示转正（去掉 mock）；
4. 契约测试：后端快照 + 前端 contract test；
5. 老 `/api/*` 下线（另行排期）。

## 8. 验收标准

- `api/models.py` 是唯一契约源，`types.ts` 为生成产物；
- 错误响应全局一致，前端按码处理；
- 大查询有上限 / 分页保护；
- 契约测试覆盖核心接口；
- 现有 66 个后端用例全绿（领域层不动，默认应直接通过）。
