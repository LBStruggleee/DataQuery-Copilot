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

# 示例查询：
# > 上个月销售额最高的品类是什么？
# > 各地区的订单数量分布
# > 用户复购率排名前10的商品
```

## 功能模块

| 模块 | 文件 | 说明 |
|------|------|------|
| 数据接入层 | `src/data_loader.py` | CSV/Excel 导入 SQLite，自动类型推断 |
| 数据清洗 | `src/data_cleaner.py` | 缺失值处理、异常值检测、格式标准化 |
| 智能查询 | `src/query_engine.py` | 自然语言 → SQL → 执行 → 返回 |
| LLM 封装 | `src/llm_client.py` | DeepSeek API 调用 + Prompt 工程 |
| 可视化 | `src/visualizer.py` | 根据查询结果自动生成图表 |
| 命令行 | `src/cli.py` | 交互式 + 批量查询 |

## 技术栈

- Python 3.10+
- SQLite（数据存储）
- DeepSeek API（LLM，兼容 OpenAI 接口格式）
- pandas（数据处理）
- matplotlib（可视化）

## 项目结构

```
dataquery-copilot/
├── src/
│   ├── __init__.py
│   ├── data_loader.py     # 数据接入层
│   ├── data_cleaner.py    # 数据清洗模块
│   ├── llm_client.py      # LLM 封装 + Prompt 工程 + SQL 修正
│   ├── query_engine.py    # 查询引擎（缓存 + 重试 + 日志）
│   ├── visualizer.py      # 可视化输出
│   └── cli.py             # 命令行（交互式 + 单次 + 批量）
├── scripts/
│   └── generate_sample_data.py
├── tests/                 # 单元测试（pytest，53 个用例）
│   ├── conftest.py
│   ├── test_data_loader.py
│   ├── test_data_cleaner.py
│   └── test_llm_client.py
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
- [x] 单元测试（pytest，53 个测试用例）
- [x] 性能优化（查询缓存 + SQL 自动重试 + 查询日志）

## 高级功能

### SQL 自动重试（容错设计）
SQL 执行失败时，自动把错误信息回传给 LLM 让它修正 SQL，最多重试 2 次。
无需人工介入，系统自动从错误中恢复。

### 查询缓存
相同问题不重复调用 API，省成本 + 提速。
```python
engine.cache_stats()   # 查看缓存统计
engine.clear_cache()   # 清空缓存
```

### 查询日志
每次查询自动记录到 `logs/query_log.jsonl`，包含时间、问题、SQL、结果、耗时、错误信息，可追溯。

### 批量查询
```bash
# 创建问题文件（每行一个问题，# 开头为注释）
python -m src.cli batch questions.txt --output report.txt
```

### 单元测试
```bash
python -m pytest tests/ -v   # 53 个测试用例
```
