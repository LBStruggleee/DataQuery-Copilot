"""
示例数据生成脚本

生成 5000 条电商订单数据，用于 DataQuery Copilot 的演示和测试。
数据包含真实的业务场景特征，适合做数据分析。

用法:
    python scripts/generate_sample_data.py
"""

import os
import random
from datetime import datetime, timedelta

import pandas as pd
import numpy as np


def generate_ecommerce_data(rows: int = 5000) -> pd.DataFrame:
    """
    生成电商订单数据

    列:
    - order_id: 订单ID（唯一）
    - order_date: 下单日期（近一年内随机）
    - category: 商品品类
    - product: 商品名称
    - amount: 订单金额（元）
    - quantity: 购买数量
    - user_id: 用户ID
    - region: 收货地区
    - payment_method: 支付方式
    - order_status: 订单状态
    """
    random.seed(42)
    np.random.seed(42)

    # 品类和商品映射
    categories = {
        "电子产品": ["手机", "耳机", "充电器", "平板", "智能手表", "数据线"],
        "服装鞋帽": ["T恤", "牛仔裤", "运动鞋", "外套", "帽子", "袜子"],
        "家居用品": ["台灯", "收纳盒", "抱枕", "水杯", "垃圾桶", "衣架"],
        "食品饮料": ["零食大礼包", "咖啡豆", "茶叶", "坚果", "牛奶", "饼干"],
        "美妆护肤": ["面霜", "口红", "防晒霜", "面膜", "洗面奶", "香水"],
        "图书文具": ["笔记本", "钢笔", "小说", "考试用书", "便签纸", "计算器"],
    }

    regions = ["华北", "华东", "华南", "华中", "西南", "西北", "东北"]
    payment_methods = ["微信支付", "支付宝", "银行卡", "信用卡", "货到付款"]
    order_statuses = ["已完成", "已发货", "待发货", "已取消", "退款中"]

    # 生成日期（近365天）
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    data = []
    for i in range(rows):
        category = random.choice(list(categories.keys()))
        product = random.choice(categories[category])

        # 金额根据品类有不同的价格区间
        price_ranges = {
            "电子产品": (50, 8000),
            "服装鞋帽": (30, 1500),
            "家居用品": (10, 500),
            "食品饮料": (5, 300),
            "美妆护肤": (20, 2000),
            "图书文具": (5, 200),
        }
        min_price, max_price = price_ranges[category]
        amount = round(random.uniform(min_price, max_price), 2)

        quantity = random.choices([1, 2, 3, 4, 5], weights=[60, 20, 10, 5, 5])[0]

        order_date = start_date + timedelta(
            days=random.randint(0, 364),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )

        # 订单状态概率分布
        status = random.choices(
            order_statuses, weights=[55, 20, 15, 5, 5]
        )[0]

        data.append({
            "order_id": 100000 + i,
            "order_date": order_date.strftime("%Y-%m-%d %H:%M:%S"),
            "category": category,
            "product": product,
            "amount": amount,
            "quantity": quantity,
            "user_id": f"U{random.randint(1000, 9999)}",
            "region": random.choice(regions),
            "payment_method": random.choice(payment_methods),
            "order_status": status,
        })

    df = pd.DataFrame(data)

    # 故意制造少量缺失值和异常值（用于演示数据清洗）
    # 随机置空 1% 的 amount
    missing_idx = random.sample(range(rows), int(rows * 0.01))
    df.loc[missing_idx, "amount"] = np.nan

    # 制造少量异常值
    outlier_idx = random.sample(range(rows), 5)
    df.loc[outlier_idx, "amount"] = df.loc[outlier_idx, "amount"] * 20

    return df


def main():
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)

    print("正在生成电商示例数据...")
    df = generate_ecommerce_data(5000)

    output_path = os.path.join(output_dir, "sample_ecommerce.csv")
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"\n数据生成完成!")
    print(f"文件: {output_path}")
    print(f"行数: {len(df)}")
    print(f"列: {list(df.columns)}")
    print(f"\n品类分布:")
    print(df["category"].value_counts())
    print(f"\n地区分布:")
    print(df["region"].value_counts())
    print(f"\n注意: 数据中包含约 1% 缺失值和少量异常值，用于演示数据清洗功能")


if __name__ == "__main__":
    main()
