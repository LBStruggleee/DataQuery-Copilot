"""
智能查询引擎 - Query Engine

核心模块：整合 DataLoader + LLMClient + DataCleaner，
实现「自然语言 → SQL 生成 → 安全校验 → 执行 → 清洗 → 返回」全链路。
"""

import os
import json
import time
import logging
from collections import OrderedDict
from datetime import datetime
from typing import Optional
from tabulate import tabulate

from .data_loader import DataLoader
from .data_cleaner import DataCleaner
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

# 查询缓存上限（LRU 淘汰），防止长会话内存无界增长
CACHE_MAX_ENTRIES = 100
# JSONL 查询日志单文件大小上限，超过后轮转为 *.1
LOG_MAX_BYTES = 5 * 1024 * 1024


class QueryEngine:
    """智能查询引擎：自然语言 -> SQL -> 结果"""

    def __init__(
        self,
        db_path: str = "data/query.db",
        table_name: str = "orders",
        enable_cache: bool = True,
        enable_log: bool = True,
    ):
        self.loader = DataLoader(db_path)
        self.cleaner = DataCleaner()
        self.llm = LLMClient()
        self.table_name = table_name

        # 查询缓存：相同问题不重复调用 API，省成本 + 提速
        # OrderedDict 实现 LRU：命中即移到队尾，超限淘汰队首
        self.enable_cache = enable_cache
        self._cache: OrderedDict = OrderedDict()

        # 查询日志：记录每次查询到 JSONL 文件，可追溯
        self.enable_log = enable_log
        self._log_dir = "logs"
        self._log_max_bytes = LOG_MAX_BYTES
        if enable_log:
            os.makedirs(self._log_dir, exist_ok=True)
            self._log_file = os.path.join(self._log_dir, "query_log.jsonl")
        else:
            self._log_file = None

    def ask(
        self,
        question: str,
        clean_result: bool = True,
        max_retries: int = 2,
        handle_missing: bool = False,
    ) -> dict:
        """
        自然语言查询（核心方法）

        完整流程:
        1. 获取表结构
        2. 调用 LLM 生成 SQL
        3. 安全校验
        4. 执行查询
        5. 可选：清洗结果
        6. 返回结果 + 元信息

        Args:
            question: 自然语言问题
            clean_result: 是否清洗查询结果
            max_retries: SQL 执行失败时的自动重试次数（容错设计），必须 >= 0
            handle_missing: 是否对结果做缺失值填充（接入 DataCleaner，默认关闭）

        Returns:
            {
                "question": "上个月销售额最高的品类",
                "sql": "SELECT category, ...",
                "data": DataFrame,
                "row_count": 5,
                "execution_time": 0.23,
                "valid": True,
                "error": None,
                "error_code": None,  # 失败时为 SQL_GENERATION_FAILED/SQL_REJECTED/EXECUTION_FAILED/EXECUTION_TIMEOUT
                "retries": 0,
                "from_cache": False,
            }
        """
        if max_retries < 0:
            raise ValueError(f"max_retries 不能为负数，当前为: {max_retries}")

        # 0. 缓存检查：相同问题（同一张表）不重复调用 API
        # 缓存键必须包含表名：切换表后同问题的正确答案不同
        cache_key = f"{self.table_name}::{question.strip().lower()}"
        if self.enable_cache and cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            cached = self._copy_result(self._cache[cache_key])
            cached["from_cache"] = True
            logger.info("[缓存] 命中缓存，跳过 API 调用")
            return cached

        result = {
            "question": question,
            "sql": "",
            "data": None,
            "row_count": 0,
            "execution_time": 0,
            "valid": False,
            "error": None,
            "error_code": None,
            "retries": 0,
            "from_cache": False,
        }

        # 1. 获取表结构
        schema_text = self.loader.get_schema_text(self.table_name)

        # 2. 调用 LLM 生成 SQL
        try:
            sql = self.llm.generate_sql(question, schema_text)
            result["sql"] = sql
        except Exception as e:
            result["error"] = f"SQL 生成失败: {e}"
            result["error_code"] = "SQL_GENERATION_FAILED"
            self._log_query(result)
            return result

        # 3. 安全校验
        if not self.llm.validate_sql(sql):
            result["error"] = (
                f"SQL 安全校验未通过（仅允许 SELECT 语句）\n"
                f"LLM 生成的 SQL:\n{sql}\n\n"
                f"请尝试换一种方式提问，或检查 LLM 是否返回了非 SELECT 语句"
            )
            result["error_code"] = "SQL_REJECTED"
            self._log_query(result)
            return result

        result["valid"] = True

        # 4. 执行查询（带自动重试：失败时把错误回传 LLM 修正）
        # 累积失败历史：每次失败的 SQL 与错误都传给修正 prompt，避免原样重放
        # P1-09：执行窗口表白名单——只允许 SELECT 当前表与 sqlite_master，
        # LLM 引用其他表/对象时执行层返回明确错误（可据此触发修正）
        df = None
        failure_history: list = []
        for attempt in range(max_retries + 1):
            start_time = time.time()
            try:
                df = self.loader.execute_query(sql, allowed_tables=(self.table_name,))
                result["execution_time"] = round(time.time() - start_time, 3)
                break  # 执行成功，跳出重试循环
            except TimeoutError as e:
                # P1-04 收尾：执行超时（data_loader query_timeout 经 progress handler 中断）
                # 不可由 LLM 修正恢复，且每轮已耗满 query_timeout 预算——不再重试，
                # 立即返回结构化错误码，由 API 层映射为契约 §4.2 的 QUERY_TIMEOUT(504)
                result["execution_time"] = round(time.time() - start_time, 3)
                result["error"] = str(e)
                result["error_code"] = "EXECUTION_TIMEOUT"
                self._log_query(result)
                return result
            except Exception as e:
                result["execution_time"] = round(time.time() - start_time, 3)
                failure_history.append({"sql": sql, "error": str(e)})
                if attempt < max_retries:
                    logger.warning(
                        "[重试 %s/%s] SQL 执行失败，正在自动修正... 错误: %s",
                        attempt + 1,
                        max_retries,
                        e,
                    )
                    try:
                        sql = self.llm.fix_sql(
                            question,
                            schema_text,
                            sql,
                            str(e),
                            history=failure_history[:-1],
                        )
                        result["sql"] = sql
                        result["retries"] = attempt + 1
                        if not self.llm.validate_sql(sql):
                            result["error"] = "修正后的 SQL 安全校验未通过"
                            result["error_code"] = "SQL_REJECTED"
                            self._log_query(result)
                            return result
                    except Exception as fix_err:
                        result["error"] = f"SQL 自动修正失败: {fix_err}"
                        result["error_code"] = "SQL_GENERATION_FAILED"
                        self._log_query(result)
                        return result
                else:
                    result["error"] = f"SQL 执行失败（已重试 {max_retries} 次）: {e}"
                    result["error_code"] = "EXECUTION_FAILED"
                    self._log_query(result)
                    return result

        # 5. 可选：清洗结果
        if clean_result and df is not None and len(df) > 0:
            if handle_missing:
                df = self.cleaner.handle_missing_values(df, strategy="auto")
            df = self.cleaner.standardize_formats(df)

        result["data"] = df
        result["row_count"] = len(df) if df is not None else 0

        # 6. 写入缓存（DataFrame 一并复制，避免缓存与调用方共享可变对象）
        if self.enable_cache:
            self._cache[cache_key] = self._copy_result(result)
            self._cache.move_to_end(cache_key)
            while len(self._cache) > CACHE_MAX_ENTRIES:
                self._cache.popitem(last=False)

        # 7. 记录日志
        self._log_query(result)

        return result

    @staticmethod
    def _copy_result(result: dict) -> dict:
        """复制结果字典，DataFrame 深拷贝，缓存与返回结果互不共享可变对象"""
        copied = dict(result)
        data = copied.get("data")
        copied["data"] = data.copy() if data is not None else None
        return copied

    def print_result(self, result: dict, max_rows: int = 20):
        """格式化打印查询结果（控制台友好，仅 CLI 使用）"""
        print("\n" + "=" * 60)
        print(f"问题: {result['question']}")
        print(f"SQL: {result['sql']}")
        print("-" * 60)

        if result["error"]:
            print(f"错误: {result['error']}")
            print("=" * 60)
            return

        if result["data"] is not None and len(result["data"]) > 0:
            df = result["data"]
            if len(df) > max_rows:
                print(f"结果（前 {max_rows} 行，共 {len(df)} 行）:")
                print(tabulate(df.head(max_rows), headers="keys", tablefmt="grid", showindex=False))
            else:
                print(f"结果（{len(df)} 行）:")
                print(tabulate(df, headers="keys", tablefmt="grid", showindex=False))
            print(f"\n执行时间: {result['execution_time']}s")
        else:
            print("查询结果为空")
            print(f"执行时间: {result['execution_time']}s")

        print("=" * 60)

    def load_data(self, filepath: str, table_name: Optional[str] = None) -> dict:
        """加载数据文件"""
        if table_name:
            self.table_name = table_name

        if filepath.endswith(".csv"):
            info = self.loader.load_csv(filepath, self.table_name)
        elif filepath.endswith((".xlsx", ".xls")):
            info = self.loader.load_excel(filepath, self.table_name)
        else:
            raise ValueError("仅支持 CSV 和 Excel 文件")

        # 数据已更换（同表覆盖或切表），旧缓存全部作废，防止命中过期结果
        self.clear_cache()

        logger.info("数据加载成功: %s", filepath)
        logger.info("表名: %s", info["table_name"])
        logger.info("行数: %s", info["row_count"])
        logger.info("列: %s", [c["name"] for c in info["columns"]])
        return info

    def show_schema(self) -> str:
        """返回当前表结构文本（展示由调用方决定）"""
        return self.loader.get_schema_text(self.table_name)

    def quality_check(self) -> dict:
        """对全表执行数据质量检查"""
        # 复用 DataLoader 的统一表名白名单校验，不绕过核心库防护
        table_name = self.loader.validate_table_name(self.table_name)
        df = self.loader.execute_query(
            f"SELECT * FROM {table_name} LIMIT 10000", allowed_tables=(table_name,)
        )
        self.cleaner.print_quality_report(df)
        return self.cleaner.quality_report(df)

    def _rotate_log_if_needed(self):
        """JSONL 日志简单大小轮转：超过上限时更名为 *.1（旧轮转文件被覆盖）"""
        if not self._log_file or not os.path.exists(self._log_file):
            return
        if os.path.getsize(self._log_file) < self._log_max_bytes:
            return
        rotated = self._log_file + ".1"
        if os.path.exists(rotated):
            os.remove(rotated)
        os.replace(self._log_file, rotated)

    def _log_query(self, result: dict):
        """将查询记录写入 JSONL 日志文件，可追溯"""
        if not self.enable_log or not self._log_file:
            return

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "question": result["question"],
            "sql": result["sql"],
            "valid": result["valid"],
            "row_count": result["row_count"],
            "execution_time": result["execution_time"],
            "retries": result.get("retries", 0),
            "error": result["error"],
            "error_code": result.get("error_code"),
        }

        try:
            self._rotate_log_if_needed()
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 日志写入失败不影响主流程

    def clear_cache(self):
        """清空查询缓存"""
        self._cache.clear()
        logger.info("缓存已清空")

    def cache_stats(self) -> dict:
        """返回缓存统计信息"""
        return {
            "cache_size": len(self._cache),
            "cached_questions": list(self._cache.keys()),
        }

    def close(self):
        """关闭连接"""
        self.loader.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
