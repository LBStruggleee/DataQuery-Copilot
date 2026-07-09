"""
SQL 刷题练习文件

用法:
  1. 在 PyCharm 中打开此文件
  2. 在每个 task 函数的 sql 里填写你的 SQL（替换掉提示注释）
  3. 运行整个文件，或右键单个函数 -> Run
  4. 对比结果，写不出就去看 docs/sql_practice.md 的参考答案

表结构:
  orders(order_id, order_date, category, product, amount,
         quantity, user_id, region, payment_method, order_status)
"""

import sqlite3

DB_PATH = "data/query.db"


def run_sql(sql: str, description: str = ""):
    """执行 SQL 并打印结果"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description] if cursor.description else []

        print(f"\n{'='*60}")
        if description:
            print(f"题目: {description}")
        print(f"SQL: {sql.strip()}")
        print(f"结果 ({len(rows)} 行):")
        if col_names:
            print(f"  {col_names}")
        for row in rows[:20]:
            print(f"  {row}")
        if len(rows) > 20:
            print(f"  ... 还有 {len(rows)-20} 行")
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"题目: {description}")
        print(f"SQL: {sql.strip()}")
        print(f"错误: {e}")
    finally:
        conn.close()


# ============================================
#  Day 1: GROUP BY + HAVING + 聚合函数
# ============================================

def task1():
    """题1: 每个品类的订单数量，按数量降序"""
    sql = """
    -- 在这里写你的 SQL
    -- 提示: SELECT category, COUNT(*) ... FROM orders GROUP BY ... ORDER BY ...
    """
    run_sql(sql, "题1: 每个品类的订单数量")


def task2():
    """题2: 销售额前5的商品"""
    sql = """
    -- 在这里写你的 SQL
    -- 提示: 需要按商品分组求 SUM(amount)，再排序取前5
    """
    run_sql(sql, "题2: 销售额前5的商品")


def task3():
    """题3: 各地区的总销售额、订单数、平均订单金额"""
    sql = """
    -- 在这里写你的 SQL
    -- 提示: 一个 GROUP BY 可以有多个聚合函数 SUM/COUNT/AVG
    """
    run_sql(sql, "题3: 各地区销售概览")


def task4():
    """题4: 平均订单金额超过 200 的品类（用 HAVING）"""
    sql = """
    -- 在这里写你的 SQL
    -- 提示: HAVING 是分组后过滤，WHERE 是分组前过滤
    """
    run_sql(sql, "题4: 平均金额超过200的品类")


# ============================================
#  Day 2: 子查询
# ============================================

def task5():
    """题5: 销售额高于全场平均值的订单"""
    sql = """
    -- 在这里写你的 SQL
    -- 提示: WHERE amount > (SELECT AVG(amount) FROM orders)
    """
    run_sql(sql, "题5: 高于平均值的订单")


def task6():
    """题6: 每个品类中金额最高的那笔订单"""
    sql = """
    -- 在这里写你的 SQL
    -- 提示: 相关子查询，子查询里要关联外层的 category
    """
    run_sql(sql, "题6: 每个品类最高金额订单")


def task7():
    """题7: 复购用户（下单超过 3 次的用户），按消费总额降序"""
    sql = """
    -- 在这里写你的 SQL
    -- 提示: GROUP BY user_id HAVING COUNT(*) > 3
    """
    run_sql(sql, "题7: 复购用户")


# ============================================
#  Day 3: 综合题
# ============================================

def task8():
    """题8: 月度销售趋势（按月统计订单数和销售额）"""
    sql = """
    -- 在这里写你的 SQL
    -- 提示: SQLite 用 strftime('%Y-%m', order_date) 提取年月
    """
    run_sql(sql, "题8: 月度销售趋势")


def task9():
    """题9: 各品类的销售额占比（百分比）"""
    sql = """
    -- 在这里写你的 SQL
    -- 提示: 占比 = SUM(amount) / (SELECT SUM(amount) FROM orders) * 100
    """
    run_sql(sql, "题9: 各品类销售额占比")


def task10():
    """题10: 高价值用户（消费总额前 10 名）"""
    sql = """
    -- 在这里写你的 SQL
    -- 提示: GROUP BY user_id，按 SUM(amount) 降序取前10
    """
    run_sql(sql, "题10: 高价值用户TOP10")


# ============================================
#  运行入口
# ============================================

if __name__ == "__main__":
    # 想练哪题就取消注释哪行，或者全部运行
    task1()
    # task2()
    # task3()
    # task4()
    # task5()
    # task6()
    # task7()
    # task8()
    # task9()
    # task10()

    print("\n" + "=" * 60)
    print("练习完成！写不出的题去看 docs/sql_practice.md 的参考答案")
    print("=" * 60)
