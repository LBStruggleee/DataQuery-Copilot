import type { QueryResponse } from "./types";

export const exampleQuestions = [
  "各品类的销售总额",
  "销售额前 5 的商品",
  "各地区订单数量和总金额",
];

export const demoQueryResponse: QueryResponse = {
  question: "各品类的销售总额和订单数，按销售额降序排列",
  sql: `SELECT
  category,
  COUNT(*) AS order_count,
  ROUND(SUM(amount), 2) AS total_sales
FROM orders
WHERE amount IS NOT NULL
GROUP BY category
ORDER BY total_sales DESC;`,
  columns: ["category", "order_count", "total_sales", "share"],
  rows: [
    { category: "电子产品", order_count: 826, total_sales: 3487268.4, share: 42 },
    { category: "美妆护肤", order_count: 839, total_sales: 1732018.16, share: 21 },
    { category: "服装鞋帽", order_count: 805, total_sales: 1026529.33, share: 12 },
    { category: "家居用品", order_count: 828, total_sales: 384287.5, share: 8 },
    { category: "食品饮料", order_count: 851, total_sales: 127106.28, share: 5 },
  ],
  row_count: 6,
  chart_hint: "bar",
  execution_time: 0.012,
  valid: true,
  retries: 0,
  from_cache: false,
  error: null,
};
