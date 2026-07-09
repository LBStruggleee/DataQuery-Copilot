"""
命令行入口 - CLI

支持三种模式:
- interactive: 交互式查询（推荐）
- query: 单次查询
- load: 加载数据文件
- schema: 查看表结构
- report: 数据质量报告
"""

import argparse
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/query.db")
DATA_FILE = os.getenv("DATA_FILE", "data/sample_ecommerce.csv")


def _is_valid_query(text: str) -> tuple[bool, str]:
    """
    输入校验，过滤明显不是查询的输入（如误粘贴的错误日志）

    Returns:
        (是否合法, 拒绝原因或空字符串)
    """
    # 1. 长度检查：太长的输入很可能是误粘贴
    if len(text) > 500:
        return False, f"输入过长（{len(text)} 字符），疑似误粘贴。请重新输入你的查询问题"

    # 2. 换行符过多：正常提问不会有多行
    if text.count("\n") > 5:
        return False, "输入包含太多换行，疑似误粘贴了日志。请重新输入"

    # 3. 疑似误粘贴了工具自身的错误输出
    tool_patterns = [
        "SQL 安全校验未通过",
        "SQL 生成失败",
        "SQL 执行失败",
        "[DEBUG] LLM 原始返回",
        "执行时间:",
        "LLM 生成的 SQL:",
    ]
    for pattern in tool_patterns:
        if pattern in text:
            return False, f'输入看起来像是工具的错误输出（匹配: [{pattern}]），请重新输入你的查询问题'

    # 4. 太短，不像一个有效问题
    if len(text) < 2:
        return False, "输入太短，请输入完整的问题"

    return True, ""


def cmd_interactive(args):
    """交互式查询模式"""
    from .query_engine import QueryEngine
    from .visualizer import Visualizer

    print("=" * 60)
    print("  DataQuery Copilot - 智能数据查询工具")
    print("  输入自然语言问题，自动生成 SQL 并查询")
    print("  输入 'quit' 或 'exit' 退出，'schema' 查看表结构")
    print("=" * 60)

    engine = QueryEngine(db_path=DB_PATH)
    viz = Visualizer()

    # 如果数据库不存在，自动加载数据
    if not os.path.exists(DB_PATH) and os.path.exists(DATA_FILE):
        print(f"\n首次运行，自动加载数据: {DATA_FILE}")
        engine.load_data(DATA_FILE)

    engine.show_schema()

    while True:
        print()
        try:
            question = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not question:
            continue

        if question.lower() in ["quit", "exit", "q"]:
            print("再见！")
            break

        if question.lower() == "schema":
            engine.show_schema()
            continue

        if question.lower() == "report":
            engine.quality_check()
            continue

        # 输入校验：过滤误粘贴的日志/错误信息
        valid, reason = _is_valid_query(question)
        if not valid:
            print(f"\n⚠️  输入已拦截: {reason}")
            continue

        # 执行查询
        result = engine.ask(question)

        # 打印结果
        engine.print_result(result)

        # 自动可视化（≥2行数据才有图表价值，单值不画）
        if result["data"] is not None and len(result["data"]) >= 2:
            try:
                viz.auto_visualize(result["data"], title=question[:30])
            except Exception as e:
                print(f"可视化生成失败（不影响查询结果）: {e}")

    engine.close()


def cmd_query(args):
    """单次查询模式"""
    from .query_engine import QueryEngine
    from .visualizer import Visualizer

    engine = QueryEngine(db_path=DB_PATH)
    viz = Visualizer()

    if args.load:
        engine.load_data(args.load)

    result = engine.ask(args.question)
    engine.print_result(result)

    # 自动可视化（≥2行数据才有图表价值）
    if result["data"] is not None and len(result["data"]) >= 2 and not args.no_viz:
        viz.auto_visualize(result["data"], title=args.question[:30])

    engine.close()


def cmd_load(args):
    """加载数据模式"""
    from .data_loader import DataLoader

    loader = DataLoader(DB_PATH)
    if args.file.endswith(".csv"):
        info = loader.load_csv(args.file, args.table)
    elif args.file.endswith((".xlsx", ".xls")):
        info = loader.load_excel(args.file, args.table)
    else:
        print("仅支持 CSV 和 Excel 文件")
        sys.exit(1)

    print(f"\n加载完成!")
    print(f"表名: {info['table_name']}")
    print(f"行数: {info['row_count']}")
    print(f"列: {[(c['name'], c['type']) for c in info['columns']]}")
    loader.close()


def cmd_schema(args):
    """查看表结构"""
    from .data_loader import DataLoader

    loader = DataLoader(DB_PATH)
    schema = loader.get_schema_text(args.table)
    print(schema)
    loader.close()


def cmd_report(args):
    """数据质量报告"""
    from .query_engine import QueryEngine

    engine = QueryEngine(db_path=DB_PATH)
    engine.quality_check()
    engine.close()


def cmd_batch(args):
    """
    批量查询模式 — 从文件读取多个问题，逐个执行

    文件格式：每行一个自然语言问题，# 开头为注释
    """
    from .query_engine import QueryEngine
    from .visualizer import Visualizer

    if not os.path.exists(args.file):
        print(f"文件不存在: {args.file}")
        sys.exit(1)

    # 读取问题列表
    with open(args.file, "r", encoding="utf-8") as f:
        questions = []
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                questions.append(line)

    if not questions:
        print("文件中没有有效问题（# 开头为注释，已跳过）")
        sys.exit(1)

    print(f"共读取 {len(questions)} 个问题，开始批量查询...\n")

    engine = QueryEngine(db_path=DB_PATH)
    viz = Visualizer()

    # 汇总统计
    results_summary = []
    success_count = 0
    fail_count = 0
    cache_count = 0

    for i, question in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] {question}")
        print("-" * 60)

        result = engine.ask(question)
        engine.print_result(result)

        if result["from_cache"]:
            cache_count += 1

        if result["error"]:
            fail_count += 1
            status = "FAIL"
        else:
            success_count += 1
            status = "OK"
            if result["data"] is not None and len(result["data"]) >= 2 and not args.no_viz:
                try:
                    viz.auto_visualize(result["data"], title=question[:30])
                except Exception:
                    pass

        results_summary.append({
            "index": i,
            "question": question,
            "status": status,
            "rows": result["row_count"],
            "time": result["execution_time"],
            "retries": result.get("retries", 0),
            "error": result["error"],
        })

    engine.close()

    # 打印汇总报告
    print("\n" + "=" * 60)
    print("  批量查询汇总报告")
    print("=" * 60)
    print(f"总查询数:   {len(questions)}")
    print(f"成功:       {success_count}")
    print(f"失败:       {fail_count}")
    print(f"缓存命中:   {cache_count}")
    print(f"成功率:     {success_count / len(questions) * 100:.1f}%")
    print("-" * 60)

    for item in results_summary:
        status_icon = "OK" if item["status"] == "OK" else "FAIL"
        print(f"  [{status_icon}] #{item['index']} {item['question'][:30]}  "
              f"({item['rows']}行, {item['time']}s, 重试{item['retries']}次)")

    # 可选：保存结果到文件
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("DataQuery Copilot 批量查询报告\n")
            f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总查询数: {len(questions)}, 成功: {success_count}, 失败: {fail_count}\n")
            f.write("=" * 60 + "\n\n")
            for item in results_summary:
                f.write(f"[{item['status']}] {item['question']}\n")
                f.write(f"  行数: {item['rows']}, 耗时: {item['time']}s, 重试: {item['retries']}\n")
                if item["error"]:
                    f.write(f"  错误: {item['error']}\n")
                f.write("\n")
        print(f"\n报告已保存: {args.output}")


def main():
    parser = argparse.ArgumentParser(
        description="DataQuery Copilot - 基于 LLM 的数据查询自动化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 交互式查询（推荐）
  python -m src.cli interactive

  # 单次查询
  python -m src.cli query "各品类的销售总额"

  # 批量查询（从文件读取问题）
  python -m src.cli batch questions.txt --output report.txt

  # 加载数据
  python -m src.cli load data/my_data.csv

  # 查看表结构
  python -m src.cli schema

  # 数据质量报告
  python -m src.cli report
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # interactive
    p_interactive = subparsers.add_parser("interactive", help="交互式查询模式")

    # query
    p_query = subparsers.add_parser("query", help="单次查询")
    p_query.add_argument("question", help="自然语言问题")
    p_query.add_argument("--load", help="查询前加载的数据文件")
    p_query.add_argument("--no-viz", action="store_true", help="不生成图表")

    # load
    p_load = subparsers.add_parser("load", help="加载数据文件")
    p_load.add_argument("file", help="数据文件路径 (CSV/Excel)")
    p_load.add_argument("--table", default="orders", help="表名 (默认: orders)")

    # schema
    p_schema = subparsers.add_parser("schema", help="查看表结构")
    p_schema.add_argument("--table", default="orders", help="表名 (默认: orders)")

    # report
    p_report = subparsers.add_parser("report", help="数据质量报告")

    # batch
    p_batch = subparsers.add_parser("batch", help="批量查询（从文件读取问题）")
    p_batch.add_argument("file", help="问题文件路径（每行一个问题，# 开头为注释）")
    p_batch.add_argument("--output", help="将汇总报告保存到指定文件")
    p_batch.add_argument("--no-viz", action="store_true", help="不生成图表")

    args = parser.parse_args()

    if args.command == "interactive":
        cmd_interactive(args)
    elif args.command == "query":
        cmd_query(args)
    elif args.command == "load":
        cmd_load(args)
    elif args.command == "schema":
        cmd_schema(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "batch":
        cmd_batch(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
