"""
LLM 客户端 - LLM Client

封装 DeepSeek API 调用（兼容 OpenAI 接口格式），
负责 Prompt 工程和 SQL 生成。

支持模型:
- DeepSeek (deepseek-chat) — 默认，性价比高
- 也可替换为任何兼容 OpenAI 接口的模型
"""

import os
import re
import json
from typing import Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    """LLM 客户端：自然语言 -> SQL"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: str = "https://api.deepseek.com/v1",
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.model = model or os.getenv("MODEL_NAME", "deepseek-chat")
        self.base_url = base_url

        if not self.api_key or self.api_key == "your_api_key_here":
            raise ValueError(
                "请先配置 API Key！\n"
                "1. 复制 .env.example 为 .env\n"
                "2. 在 .env 中填入你的 DEEPSEEK_API_KEY\n"
                "3. 注册地址: https://platform.deepseek.com"
            )

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate_sql(self, question: str, schema_text: str) -> str:
        """
        根据自然语言问题和数据库 schema 生成 SQL

        Args:
            question: 用户的自然语言问题，如"上个月销售额最高的品类"
            schema_text: 数据库表结构描述（来自 DataLoader.get_schema_text）

        Returns:
            SQL 查询语句字符串
        """
        system_prompt = self._build_system_prompt(schema_text)
        user_prompt = self._build_user_prompt(question)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,  # 低温度保证输出稳定
            max_tokens=2000,
        )

        raw_output = response.choices[0].message.content.strip()
        sql = self._extract_sql(raw_output)

        # 调试：打印 LLM 原始返回和提取结果，方便排查问题
        print(f"\n[DEBUG] LLM 原始返回:\n{raw_output}\n")
        print(f"[DEBUG] 提取的 SQL:\n{sql}\n")

        return sql

    def _build_system_prompt(self, schema_text: str) -> str:
        """
        构建 System Prompt — Prompt 工程的核心

        设计要点:
        1. 明确角色：你是一个 SQL 专家
        2. 提供完整的表结构信息
        3. 约束输出格式：只返回 SQL，不要多余解释
        4. 安全约束：只允许 SELECT，禁止修改数据
        """
        return f"""你是一个专业的 SQL 数据分析师。

数据库表结构如下：
{schema_text}

请根据用户的问题，生成对应的 SQLite 查询语句。

规则：
1. 只生成 SELECT 语句，禁止使用 INSERT/UPDATE/DELETE/DROP 等修改数据的操作
2. 使用标准 SQLite 语法
3. 日期处理使用 strftime() 或 date() 函数
4. 重要：先写完整的 SQL 语句，注释放在 SQL 后面（不要先写注释再写 SQL）
5. 只返回 SQL 语句，用 ```sql 代码块包裹，不要其他解释

示例：
用户问题: 各品类的销售总额
回复:
```sql
SELECT category, SUM(amount) as total_sales
FROM orders
GROUP BY category
ORDER BY total_sales DESC
```"""

    def _build_user_prompt(self, question: str) -> str:
        """构建用户消息"""
        return f"问题: {question}"

    def _extract_sql(self, raw_output: str) -> str:
        """
        从 LLM 输出中提取 SQL 语句

        支持:
        - ```sql ... ``` 代码块
        - 纯 SQL 文本
        """
        # 尝试匹配 ```sql ... ``` 代码块
        pattern = r"```sql\s*(.*?)\s*```"
        match = re.search(pattern, raw_output, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 尝试匹配 ``` ... ``` 代码块
        pattern = r"```\s*(.*?)\s*```"
        match = re.search(pattern, raw_output, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 如果没有代码块，尝试直接提取 SELECT 语句
        lines = raw_output.strip().split("\n")
        sql_lines = []
        in_sql = False
        for line in lines:
            stripped = line.strip()
            if stripped.upper().startswith("SELECT") or stripped.startswith("--"):
                in_sql = True
            if in_sql:
                sql_lines.append(line)
                if stripped.endswith(";"):
                    break

        if sql_lines:
            return "\n".join(sql_lines).strip().rstrip(";")

        # 最后兜底：返回原始输出
        return raw_output.strip()

    def validate_sql(self, sql: str) -> bool:
        """
        SQL 安全校验 — 防止非查询语句执行

        Returns:
            True 如果是安全的 SELECT 语句
        """
        sql_upper = sql.upper().strip()

        # 移除字符串字面量和注释，避免误判
        sql_clean = re.sub(r"'[^']*'", "''", sql_upper)  # 移除单引号字符串
        sql_clean = re.sub(r"--[^\n]*", "", sql_clean)    # 移除单行注释
        sql_clean = re.sub(r"/\*.*?\*/", "", sql_clean, flags=re.DOTALL)  # 移除多行注释

        # 禁止的关键词（用词边界匹配，避免 "created_at" 误命中 "CREATE"）
        forbidden = [
            r"\bINSERT\b", r"\bUPDATE\b", r"\bDELETE\b", r"\bDROP\b",
            r"\bALTER\b", r"\bCREATE\b", r"\bTRUNCATE\b", r"\bATTACH\b", r"\bDETACH\b",
        ]

        for pattern in forbidden:
            if re.search(pattern, sql_clean):
                return False

        # 必须以 SELECT 开头（允许前面有注释或 WITH）
        lines = sql_clean.split("\n")
        code_lines = [l for l in lines if not l.strip().startswith("--")]
        sql_clean = "\n".join(code_lines).strip()

        if not (sql_clean.startswith("SELECT") or sql_clean.startswith("WITH")):
            return False

        return True

    def fix_sql(
        self, question: str, schema_text: str, failed_sql: str, error_message: str
    ) -> str:
        """
        SQL 自动修正 — 当执行失败时，把错误信息回传给 LLM 让它修正

        这是容错设计的核心：不依赖人工介入，系统自动从错误中恢复。

        Args:
            question: 原始自然语言问题
            schema_text: 表结构描述
            failed_sql: 执行失败的 SQL
            error_message: 数据库返回的错误信息

        Returns:
            修正后的 SQL 字符串
        """
        system_prompt = self._build_system_prompt(schema_text)

        fix_prompt = f"""问题: {question}

之前生成的 SQL 执行失败了，请根据错误信息修正 SQL。

失败的 SQL:
```sql
{failed_sql}
```

错误信息:
{error_message}

请分析错误原因，返回修正后的 SQL。只返回 SQL 语句，用 ```sql 代码块包裹。"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": fix_prompt},
            ],
            temperature=0.1,
            max_tokens=2000,
        )

        raw_output = response.choices[0].message.content.strip()
        sql = self._extract_sql(raw_output)

        print(f"\n[DEBUG] LLM 修正后的 SQL:\n{sql}\n")
        return sql
