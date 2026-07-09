"""
数据清洗模块 - Data Cleaner

负责缺失值处理、异常值检测、格式标准化，
以及生成数据质量报告。
"""

import pandas as pd
import numpy as np
from typing import Optional, Literal


class DataCleaner:
    """数据清洗：缺失值、异常值、格式标准化"""

    def clean(self, df: pd.DataFrame, strategy: str = "auto") -> pd.DataFrame:
        """
        一键清洗：按默认策略执行完整清洗流程

        Args:
            df: 原始 DataFrame
            strategy: "auto" 自动处理 / "strict" 严格模式（只删除，不填充）

        Returns:
            清洗后的 DataFrame
        """
        df = df.copy()
        df = self.handle_missing_values(df, strategy=strategy)
        df = self.standardize_formats(df)
        return df

    def handle_missing_values(
        self,
        df: pd.DataFrame,
        strategy: Literal["auto", "strict", "fill"] = "auto",
    ) -> pd.DataFrame:
        """
        处理缺失值

        - auto: 数值列用中位数填充，分类列用众数填充
        - strict: 直接删除含缺失值的行
        - fill: 全部用默认值填充（数值=0，分类="unknown"）
        """
        df = df.copy()

        if strategy == "strict":
            return df.dropna()

        for col in df.columns:
            if df[col].isna().sum() == 0:
                continue

            if df[col].dtype in [np.float64, np.int64, float, int]:
                if strategy == "auto":
                    fill_val = df[col].median()
                else:
                    fill_val = 0
                df[col] = df[col].fillna(fill_val)
            else:
                if strategy == "auto":
                    mode_val = df[col].mode()
                    fill_val = mode_val[0] if len(mode_val) > 0 else "unknown"
                else:
                    fill_val = "unknown"
                df[col] = df[col].fillna(fill_val)

        return df

    def detect_outliers(
        self, df: pd.DataFrame, column: str, method: str = "iqr"
    ) -> pd.DataFrame:
        """
        检测异常值（IQR 方法）

        Args:
            df: DataFrame
            column: 要检测的列名
            method: 目前支持 "iqr"

        Returns:
            只包含异常行的 DataFrame
        """
        if column not in df.columns:
            raise ValueError(f"列不存在: {column}")

        if df[column].dtype not in [np.float64, np.int64, float, int]:
            raise ValueError(f"列 {column} 不是数值类型，无法检测异常值")

        if method == "iqr":
            Q1 = df[column].quantile(0.25)
            Q3 = df[column].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR

            outliers = df[(df[column] < lower_bound) | (df[column] > upper_bound)]
            return outliers

        return pd.DataFrame()

    def standardize_formats(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        格式标准化
        - 日期列统一格式
        - 字符串列去除首尾空格
        - 数值列统一精度
        """
        df = df.copy()

        for col in df.columns:
            # 字符串列去空格
            if df[col].dtype == "object":
                df[col] = df[col].astype(str).str.strip()

            # 日期列统一格式
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = pd.to_datetime(df[col], errors="coerce")

            # 浮点数列保留2位小数
            if df[col].dtype == np.float64:
                df[col] = df[col].round(2)

        return df

    def quality_report(self, df: pd.DataFrame) -> dict:
        """
        生成数据质量报告

        Returns:
            {
                "total_rows": 5000,
                "total_columns": 8,
                "missing_values": {"amount": 12, "category": 0, ...},
                "duplicates": 3,
                "column_types": {"order_id": "int64", ...},
            }
        """
        report = {
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "missing_values": {},
            "duplicates": int(df.duplicated().sum()),
            "column_types": {col: str(dtype) for col, dtype in df.dtypes.items()},
        }

        for col in df.columns:
            missing = int(df[col].isna().sum())
            if missing > 0:
                report["missing_values"][col] = missing

        return report

    def print_quality_report(self, df: pd.DataFrame):
        """打印数据质量报告（控制台友好格式）"""
        report = self.quality_report(df)

        print("=" * 50)
        print("         数据质量报告")
        print("=" * 50)
        print(f"总行数:     {report['total_rows']}")
        print(f"总列数:     {report['total_columns']}")
        print(f"重复行数:   {report['duplicates']}")

        if report["missing_values"]:
            print("\n缺失值分布:")
            for col, count in report["missing_values"].items():
                pct = count / report["total_rows"] * 100
                print(f"  {col}: {count} 条 ({pct:.1f}%)")
        else:
            print("\n缺失值: 无")

        print("\n列类型:")
        for col, dtype in report["column_types"].items():
            print(f"  {col}: {dtype}")
        print("=" * 50)
