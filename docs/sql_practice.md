# SQL 刷题练习手册

> 用你自己的项目数据库练 SQL，一举两得：既练了面试题，又熟悉了项目数据

---

## 怎么连接数据库练习

### 方式一：Python 交互式（推荐）

```bash
cd dataquery-copilot
python
```

```python
import sqlite3
conn = sqlite3.connect('data/query.db')
cursor = conn.cursor()

# 写你的 SQL
cursor.execute("""
SELECT category, COUNT(*) as cnt
FROM orders
GROUP BY category
ORDER BY cnt DESC
""")

# 打印结果
for row in cursor.fetchall():
    print(row)
```

### 方式二：一行命令快速验证

```bash
python -c "import sqlite3; [print(r) for r in sqlite3.connect('data/query.db').execute('SELECT category, COUNT(*) FROM orders GROUP BY category').fetchall()]"
```

---

## 数据库表结构

```
表名: orders
列:
  - order_id        INTEGER   订单ID
  - order_date      TEXT      下单时间 (格式: 2025-10-28 01:19:32)
  - category        TEXT      品类
  - product         TEXT      商品名
  - amount          REAL      订单金额
  - quantity        INTEGER   购买数量
  - user_id         TEXT      用户ID
  - region          TEXT      地区
  - payment_method  TEXT      支付方式
  - order_status    TEXT      订单状态
```

---

## 10 道练习题（从易到难）

### Day 1：GROUP BY + HAVING + 聚合

#### 题1：每个品类的订单数量
```sql
SELECT category, COUNT(*) as order_count
FROM orders
GROUP BY category
ORDER BY order_count DESC;
```
考点：GROUP BY + COUNT + ORDER BY

#### 题2：销售额前5的商品
```sql
SELECT product, SUM(amount) as total_sales
FROM orders
GROUP BY product
ORDER BY total_sales DESC
LIMIT 5;
```
考点：GROUP BY + SUM + ORDER BY + LIMIT

#### 题3：各地区的总销售额和订单数
```sql
SELECT region,
       SUM(amount) as total_sales,
       COUNT(*) as order_count,
       ROUND(AVG(amount), 2) as avg_amount
FROM orders
GROUP BY region
ORDER BY total_sales DESC;
```
考点：多聚合函数 + ROUND

#### 题4：平均订单金额超过200的品类
```sql
SELECT category, ROUND(AVG(amount), 2) as avg_amount
FROM orders
GROUP BY category
HAVING AVG(amount) > 200
ORDER BY avg_amount DESC;
```
考点：HAVING（注意 HAVING 和 WHERE 的区别：WHERE 过滤行，HAVING 过滤分组）

---

### Day 2：子查询

#### 题5：销售额高于全场平均值的订单
```sql
SELECT order_id, category, product, amount
FROM orders
WHERE amount > (SELECT AVG(amount) FROM orders)
ORDER BY amount DESC
LIMIT 20;
```
考点：WHERE 中的标量子查询

#### 题6：每个品类中金额最高的订单
```sql
SELECT o1.category, o1.product, o1.amount
FROM orders o1
WHERE o1.amount = (
    SELECT MAX(o2.amount)
    FROM orders o2
    WHERE o2.category = o1.category
)
ORDER BY o1.amount DESC;
```
考点：相关子查询（子查询引用外层表）

#### 题7：复购用户（下单超过3次的用户）
```sql
SELECT user_id, COUNT(*) as order_count, SUM(amount) as total_spent
FROM orders
GROUP BY user_id
HAVING COUNT(*) > 3
ORDER BY total_spent DESC
LIMIT 20;
```
考点：GROUP BY + HAVING + 多聚合

---

### Day 3：综合题

#### 题8：月度销售趋势
```sql
SELECT strftime('%Y-%m', order_date) as month,
       COUNT(*) as order_count,
       ROUND(SUM(amount), 2) as total_sales
FROM orders
GROUP BY month
ORDER BY month;
```
考点：日期处理 strftime + GROUP BY

#### 题9：各品类的销售额占比
```sql
SELECT category,
       ROUND(SUM(amount), 2) as sales,
       ROUND(SUM(amount) * 100.0 / (SELECT SUM(amount) FROM orders), 2) as pct
FROM orders
GROUP BY category
ORDER BY sales DESC;
```
考点：子查询 + 数学计算 + 百分比

#### 题10：高价值用户（消费总额前10名）
```sql
SELECT user_id,
       COUNT(*) as order_count,
       ROUND(SUM(amount), 2) as total_spent,
       ROUND(AVG(amount), 2) as avg_order
FROM orders
GROUP BY user_id
ORDER BY total_spent DESC
LIMIT 10;
```
考点：GROUP BY + 多聚合 + ORDER BY + LIMIT（RFM 分析基础）

---

## 外部刷题平台推荐

| 平台 | 链接 | 特点 | 适合练什么 |
|------|------|------|-----------|
| **牛客网** | nowcoder.com → SQL 板块 | 中文、免费、校招真题多 | Day2-3 的 JOIN 和综合题 |
| **SQLZOO** | sqlzoo.net | 互动式、边学边练、英文 | Day1 入门，语法练习 |
| **LeetCode** | leetcode.com → Database | 经典题、难度分级、英文 | JOIN 和窗口函数 |

### 刷题顺序建议
1. 先用本项目数据库做完上面 10 道题（Day1-3 各做一遍）
2. 去 SQLZOO 过一遍基础语法（1小时）
3. 去牛客刷 SQL 专项（重点刷 JOIN 和窗口函数题）
4. 去 LeetCode 刷 Database 50 题中的中等难度

---

## 学习方法

### 核心原则：边刷边学，不要看完教程再开始

1. **5分钟法则**：每道题先自己想5分钟，想不出就看题解，看懂后关掉题解自己默写一遍
2. **错题本**：截图或复制做错的题，第二天先重做昨天的错题再刷新的
3. **计时练习**：简单题3分钟内、中等题8分钟内、难题15分钟内
4. **手写练习**：面试是手写 SQL，不是在电脑上敲。重点题用纸笔写一遍

### HAVING vs WHERE 速记
```
WHERE  → 过滤行（分组前过滤）  → WHERE amount > 100
HAVING → 过滤组（分组后过滤）  → HAVING COUNT(*) > 5
```

### JOIN 速记
```
INNER JOIN : 两表都有的才保留     → 交集
LEFT  JOIN : 左表全保留，右表没有的填 NULL
RIGHT JOIN : 右表全保留，左表没有的填 NULL
```
> JOIN 的题去牛客网刷，那里的题有多表数据。你自己的项目数据库只有一张表，练不了 JOIN。

---

## 刷完标准

- 10道项目题全部能独立写出
- 牛客 SQL 专项正确率 70%+
- 看到"每个品类""销售额排名""复购用户"这类关键词，能立刻想到用什么语法
- 能在纸上手写 SQL，不依赖编辑器自动补全
