# DataQuery Copilot 技术文档

## 1. 项目概述

### 1.1 背景与问题
在数据分析工作中，业务人员经常需要查询数据但不会写 SQL，工程师反复处理重复的查询请求，效率低下。传统方式的痛点：
- 业务人员依赖工程师写 SQL，沟通成本高
- 工程师时间被重复查询消耗，无法专注高价值工作
- 数据查询门槛高，从提问到拿到结果周期长

### 1.2 解决方案
DataQuery Copilot 是一个基于 LLM 的数据查询自动化工具，用户用自然语言描述需求，系统自动完成：
1. 理解自然语言意图
2. 生成对应的 SQL 查询语句
3. 安全校验（防注入/防误操作）
4. 自动执行查询
5. 数据清洗
6. 结果可视化

### 1.3 核心指标
- SQL 生成准确率：85%+（常见查询场景）
- 单次查询响应时间：< 3 秒
- 较人工查询效率提升：约 10 倍

---

## 2. 系统架构

```
用户输入（自然语言）
       |
       v
+------------------+
|   QueryEngine    |  ← 核心调度器
+------------------+
       |
       |--- 1. DataLoader.get_schema_text() → 获取表结构
       |         |
       |         v
       |    +------------------+
       |    |   SQLite 数据库   |
       |    +------------------+
       |
       |--- 2. LLMClient.generate_sql(question, schema) → 生成 SQL
       |         |
       |         v
       |    +------------------+
       |    |  DeepSeek API     |
       |    |  (Prompt 工程)    |
       |    +------------------+
       |
       |--- 3. LLMClient.validate_sql(sql) → 安全校验
       |
       |--- 4. DataLoader.execute_query(sql) → 执行查询
       |
       |--- 5. DataCleaner.standardize_formats(result) → 清洗结果
       |
       |--- 6. Visualizer.auto_visualize(result) → 生成图表
       |
       v
查询结果 + SQL + 图表
```

---

## 3. 模块设计

### 3.1 数据接入层 (data_loader.py)

**职责**：将外部数据文件导入 SQLite，提供统一的查询接口。

**设计要点**：
- 支持 CSV 和 Excel 两种格式
- 自动推断数据类型（日期、数值、字符串）
- `get_schema_text()` 方法将表结构格式化为文本，直接嵌入 LLM Prompt
- 使用 SQLite 的 WAL 模式提升并发性能

**关键技术决策**：
- 为什么选 SQLite？轻量、嵌入式、无需额外服务、适合工具型应用
- 为什么自动推断类型？LLM 需要知道准确的列类型才能生成正确的 SQL

### 3.2 LLM 客户端 (llm_client.py)

**职责**：调用 LLM API 将自然语言转为 SQL。

**Prompt 工程设计**：
- System Prompt 包含：角色设定 + 表结构 + 规则约束 + 示例
- temperature=0.1：低温度保证输出稳定性
- 输出格式约束：要求用 ```sql 代码块包裹
- 安全约束：只允许 SELECT，禁止修改数据

**SQL 提取**：
- 支持从代码块中提取
- 支持纯文本提取
- 容错处理多种 LLM 输出格式

**安全校验**：
- 关键词黑名单：INSERT/UPDATE/DELETE/DROP 等
- 必须以 SELECT 或 WITH 开头
- 双重保险：Prompt 约束 + 代码校验

### 3.3 智能查询引擎 (query_engine.py)

**职责**：核心调度器，串联所有模块。

**核心方法 `ask()`**：
1. 获取表结构 → 2. LLM 生成 SQL → 3. 安全校验 → 4. 执行查询 → 5. 清洗结果 → 6. 返回

**容错设计**：
- 每个步骤都有 try-catch
- 返回结构包含 error 字段，失败不崩溃
- 执行时间统计

### 3.4 数据清洗模块 (data_cleaner.py)

**职责**：处理缺失值、异常值、格式标准化。

**清洗策略**：
- auto 模式：数值列用中位数填充，分类列用众数填充
- IQR 方法检测异常值
- 日期统一格式、字符串去空格、浮点数统一精度

**数据质量报告**：
- 统计缺失值分布、重复行数、列类型
- 控制台友好格式输出

### 3.5 可视化模块 (visualizer.py)

**职责**：根据查询结果自动选择图表类型。

**图表选择策略**：
| 数据特征 | 图表类型 |
|---------|---------|
| 日期 + 数值 | 折线图 |
| 分类 + 数值（≤30类） | 柱状图 |
| 单列分类（≤10类） | 饼图 |
| 数值 + 数值 | 散点图 |

**技术决策**：
- 使用 matplotlib Agg 后端，适合服务端无界面环境
- 中文显示支持（SimHei/Microsoft YaHei）
- 自动保存到 output 目录

---

## 4. 数据流程

### 4.1 数据接入流程
```
CSV/Excel → pandas.read_csv → 类型推断 → SQLite.to_sql → 表结构信息
```

### 4.2 查询流程
```
自然语言问题
    → schema_text（表结构）
    → LLM generate_sql（Prompt 工程）
    → SQL 字符串
    → validate_sql（安全校验）
    → execute_query（SQLite 执行）
    → DataFrame
    → standardize_formats（清洗）
    → auto_visualize（可视化）
    → 结果 + SQL + 图表
```

---

## 5. 技术选型说明

| 技术 | 选型 | 理由 |
|------|------|------|
| 语言 | Python 3.10+ | 数据科学生态成熟，LLM SDK 支持好 |
| 数据库 | SQLite | 轻量、嵌入式、无需部署 |
| LLM | DeepSeek API | 性价比高、兼容 OpenAI 接口、中文理解强 |
| 数据处理 | pandas | 行业标准，面试必考 |
| 可视化 | matplotlib | 通用性强，面试认可度高 |
| 配置管理 | python-dotenv | API Key 安全管理 |

---

## 6. 已知局限性

1. **多表 JOIN 准确率下降**：复杂多表关联查询的 SQL 生成准确率会降低，当前版本主要支持单表查询
2. **不支持事务操作**：安全考虑，只允许 SELECT
3. **数据量限制**：SQLite 适合中小规模数据（百万级以内），大数据量需迁移到 MySQL/PostgreSQL
4. **Prompt 依赖**：SQL 生成质量依赖 Prompt 设计，不同模型表现可能不同
5. **无缓存机制**：相同问题会重复调用 API，可加查询缓存优化

---

## 7. 后续优化方向

- [ ] 多表关联查询支持（通过 schema 扩展）
- [ ] 查询结果缓存（减少 API 调用）
- [ ] SQL 自动重试机制（生成失败时自动修正）
- [ ] 批量查询 CLI（支持文件输入）
- [ ] Web 界面（Flask/Streamlit）
- [ ] 支持更多数据库（MySQL/PostgreSQL）
