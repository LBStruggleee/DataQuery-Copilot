# DataQuery Copilot

> 基于 LLM 的数据查询自动化工具 — 用自然语言查数据，自动生成 SQL 并执行

## 这是什么

一个把「自然语言 → SQL 生成 → 自动执行 → 数据清洗 → 可视化输出」打通的工具。
业务人员不用写 SQL，工程师不用反复处理重复查询，降低数据使用门槛。

## 快速开始

```bash
# 1. 安装运行依赖
pip install -r requirements.txt

# 开发/运行测试时，改用开发依赖
pip install -r requirements-dev.txt

# 也可以通过 pyproject.toml 以可编辑模式安装
pip install -e ".[dev]"

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env 填入你的 DeepSeek API Key（https://platform.deepseek.com 注册获取）

# 3. 生成示例数据
python scripts/generate_sample_data.py

# 4. 启动交互式查询
python -m src.cli interactive

# 或启动前端使用的 HTTP API
uvicorn api.main:app --reload
# API 文档: http://127.0.0.1:8000/docs

# 另开一个终端启动 React v0 页面
cd frontend
npm install
npm run dev
# 页面地址: http://127.0.0.1:5173

# 示例查询：
# > 上个月销售额最高的品类是什么？
# > 各地区的订单数量分布
# > 用户复购率排名前10的商品
```

## 在线展示与部署

当前仓库已提供前后端分离部署配置，但尚未绑定线上账号或发布虚构地址。部署步骤和环境变量说明见 [docs/deployment.md](docs/deployment.md)。

部署完成后，作品集演示建议固定使用以下真实问题：

- 各品类的销售总额
- 销售额前 5 的商品
- 各地区订单数量和总金额
- 平均订单金额超过 200 的品类

前端页面包含桌面、平板和手机响应式布局；生产构建命令为 `cd frontend && npm ci && npm run build`。

## 功能模块

| 模块 | 文件 | 说明 |
|------|------|------|
| 数据接入层 | `src/data_loader.py` | CSV / Excel(.xlsx) 导入 SQLite，自动类型推断 |
| 数据清洗 | `src/data_cleaner.py` | 缺失值处理、异常值检测、格式标准化 |
| 智能查询 | `src/query_engine.py` | 自然语言 → SQL → 执行 → 返回 |
| LLM 封装 | `src/llm_client.py` | DeepSeek API 调用 + Prompt 工程 |
| 可视化 | `src/visualizer.py` | 根据查询结果自动生成图表 |
| 命令行 | `src/cli.py` | 交互式 + 批量查询 |
| HTTP API | `api/main.py` | 为 Web 前端提供结构化查询接口 |

## 技术栈

- Python 3.10+
- SQLite（数据存储）
- DeepSeek API（LLM，兼容 OpenAI 接口格式）
- pandas（数据处理）
- matplotlib（可视化）
- FastAPI（HTTP 服务）
- React + TypeScript + Vite（Web 工作台）

## 项目结构

```
dataquery-copilot/
├── api/
│   ├── main.py             # FastAPI HTTP 入口（路由 + 免鉴权健康探针）
│   ├── models.py           # API 响应模型
│   ├── services.py         # 现有核心模块的 HTTP 适配层
│   ├── auth.py             # API Key 鉴权 / 限流 / 日配额
│   ├── datasets.py         # 数据集上传入库与多数据集作用域
│   ├── errors.py           # 统一错误码
│   ├── logjson.py          # 结构化 JSON 日志格式
│   ├── metrics.py          # 内存态请求指标（/api/v1/metrics）
│   └── request_context.py  # request_id 中间件
├── src/
│   ├── __init__.py
│   ├── data_loader.py     # 数据接入层
│   ├── data_cleaner.py    # 数据清洗模块
│   ├── llm_client.py      # LLM 封装 + Prompt 工程 + SQL 修正
│   ├── query_engine.py    # 查询引擎（缓存 + 重试 + 日志）
│   ├── visualizer.py      # 可视化输出
│   └── cli.py             # 命令行（交互式 + 单次 + 批量）
├── scripts/
│   ├── generate_sample_data.py
│   ├── prepare_demo_db.py
│   ├── manage_keys.py      # API Key 签发 / 列表 / 吊销
│   ├── backup_db.py        # SQLite 在线备份（含 WAL，可轮换保留）
│   ├── e2e_up.sh           # E2E 一键入口（bash，Linux/macOS/Git Bash）
│   └── e2e_up.ps1          # E2E 一键入口（Windows PowerShell）
├── frontend/               # React + TypeScript 工作台
│   ├── src/
│   ├── .env.example        # 前端 API 地址配置示例
│   └── package.json
├── Dockerfile.api          # API 生产镜像
├── render.yaml             # Render 前后端 Blueprint
├── .github/workflows/      # CI：全量后端测试 / lint / 前端构建 / 密钥清扫
├── load/                  # 负载压测脚本（load/soak.py）与说明（load/README.md）
├── tests/                 # 单元测试（pytest，245 个用例）
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_api_auth.py
│   ├── test_api_v1.py
│   ├── test_backup_db.py
│   ├── test_cli.py
│   ├── test_data_cleaner.py
│   ├── test_data_loader.py
│   ├── test_datasets.py
│   ├── test_llm_client.py
│   ├── test_logjson.py
│   ├── test_ops_health.py
│   ├── test_query_engine.py
│   ├── test_soak.py
│   └── test_visualizer.py
├── data/                  # 数据文件
├── output/                # 输出图表 + 批量报告
├── logs/                  # 查询日志（JSONL）
├── docs/                  # 技术文档
├── questions.txt          # 批量查询示例
├── practice.py            # SQL 刷题练习
├── pyproject.toml         # 项目元数据 + 标准依赖入口
├── requirements.txt
├── requirements-dev.txt  # 开发/测试依赖
├── .env.example
└── README.md
```

## 开发计划

- [x] 项目骨架搭建
- [x] 数据接入层
- [x] LLM API 对接
- [x] 核心查询闭环
- [x] 数据清洗模块
- [x] 可视化输出
- [x] SQL 安全校验增强（词边界匹配 + 字符串/注释过滤）
- [x] 批量查询 CLI（从文件读取 + 汇总报告）
- [x] 单元测试（pytest，245 个测试用例）
- [x] 性能优化（查询缓存 + SQL 自动重试 + 查询日志）
- [x] React 工作台 v0 与核心交互
- [x] 深浅主题、响应式和键盘交互
- [x] 部署配置、健康检查和 CI 构建验证

## 高级功能

### SQL 自动重试（容错设计）
SQL 执行失败时，自动把错误信息回传给 LLM 让它修正 SQL，最多重试 2 次。
无需人工介入，系统自动从错误中恢复。

### 查询缓存
相同问题不重复调用 LLM API，省成本 + 提速。缓存作用于核心库 `QueryEngine`（CLI / 直接调用场景）；
HTTP API（`/api/v1/query`）为避免跨请求返回陈旧结果，固定 `enable_cache=False`：响应中 `from_cache` 恒为 `false`。
```python
engine.cache_stats()   # 查看缓存统计
engine.clear_cache()   # 清空缓存
```

### 查询日志
CLI / 核心库直接调用时，每次查询自动记录到 `logs/query_log.jsonl`，包含时间、问题、SQL、结果、耗时、错误信息，可追溯。
HTTP API 查询路径默认关闭该逐条日志（`enable_log=False`）：用户问题与生成的 SQL 属潜在敏感业务信息，不落盘；
服务端仅保留结构化运行日志（不含问题/SQL 原文）。

### 结果清洗开关
查询结果的清洗默认开启（auto 填充缺失值 + 格式标准化），可按需关闭：
核心库 `engine.ask(question, clean_result=False)`；HTTP API 请求体传 `"clean_result": false`。

### LLM 超时
单次 LLM 调用超时默认 30 秒，环境变量 `LLM_TIMEOUT_SECONDS` 可覆盖（非法取值在构造 LLM 客户端时直接报错，见 `src/llm_client.py`）。

### 批量查询
```bash
# 创建问题文件（每行一个问题，# 开头为注释）
python -m src.cli batch questions.txt --output report.txt
```

### 单元测试
```bash
python -m pytest tests/ -v   # 后端测试
```

### 访问控制（API Key）
除免鉴权存活探针 `GET /api/health`（只回报进程与库文件状态，供部署平台/容器健康检查使用）外，
所有 `/api/*` 接口要求 `X-API-Key` 请求头。签发与吊销在服务器上执行：
```bash
python scripts/manage_keys.py create --name <用途> [--quota 200]  # 明文只显示一次
python scripts/manage_keys.py list
python scripts/manage_keys.py revoke <明文Key>
```
前端在左侧栏底部「访问密钥」处填入 Key（存浏览器本地）。无 Key 调接口返回 401 `AUTH_REQUIRED`，
超频/配额耗尽返回 429 `RATE_LIMITED`。限流为单进程内存实现（默认单 worker 足够）。
查询与上传均计入 Key 的当日配额（默认 200 次/天，`manage_keys.py create --quota` 可调），成功后才记账。

### 数据集与备份
- 前端左侧栏可下拉切换数据集，上传 CSV / Excel(.xlsx)（≤50MB，.xls 已不再支持）后自动入库并出现在列表中；
  上传计入当日配额，数据集数量上限 50 个，超出返回 429。
- 备份与恢复演练：
```bash
python scripts/backup_db.py --db data/query.db --dir backups --keep 7
cp backups/query_<timestamp>.db /tmp/restored.db
python -c "import sqlite3; print(sqlite3.connect('/tmp/restored.db').execute('SELECT COUNT(*) FROM orders').fetchone())"
```

### CI 检查

GitHub Actions 会执行全量后端测试（`pytest tests/ -q`）、非阻塞 ruff lint、React 生产构建与密钥清扫，配置文件为 `.github/workflows/ci.yml`。
