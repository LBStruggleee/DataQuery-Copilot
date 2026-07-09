"""
可视化模块 - Visualizer

根据查询结果自动选择合适的图表类型并生成图表。
支持柱状图、折线图、饼图、散点图。
"""

import os
from pathlib import Path
from typing import Optional
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # 非交互式后端，适合保存文件
import matplotlib.pyplot as plt

# 中文显示支持
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


class Visualizer:
    """自动可视化：根据数据特征选择图表"""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def auto_visualize(
        self,
        df: pd.DataFrame,
        title: str = "查询结果",
        save: bool = True,
    ) -> Optional[str]:
        """
        根据数据特征自动选择图表类型

        策略:
        - 1列分类 + 1列数值 -> 柱状图
        - 1列日期 + 1列数值 -> 折线图
        - 1列分类（少量） -> 饼图
        - 2列数值 -> 散点图
        - 其他 -> 表格输出

        Returns:
            保存的文件路径，或 None
        """
        if df is None or len(df) == 0:
            print("数据为空，无法生成图表")
            return None

        chart_type = self._detect_chart_type(df)

        if chart_type == "bar":
            return self.bar_chart(df, title, save)
        elif chart_type == "line":
            return self.line_chart(df, title, save)
        elif chart_type == "pie":
            return self.pie_chart(df, title, save)
        elif chart_type == "scatter":
            return self.scatter_plot(df, title, save)
        else:
            print(f"数据特征不适合自动生成图表（{len(df.columns)}列），建议查看表格数据")
            return None

    def _detect_chart_type(self, df: pd.DataFrame) -> str:
        """根据列数和数据类型推断图表类型"""
        num_cols = len(df.columns)

        if num_cols == 2:
            col1, col2 = df.columns[0], df.columns[1]
            dtypes = df.dtypes

            # 日期 + 数值 -> 折线图
            if pd.api.types.is_datetime64_any_dtype(df[col1]) and self._is_numeric(df[col2]):
                return "line"

            # 分类 + 数值 -> 柱状图
            if not self._is_numeric(df[col1]) and self._is_numeric(df[col2]):
                if len(df) <= 30:  # 类别太多柱状图不好看
                    return "bar"

            # 数值 + 数值 -> 散点图
            if self._is_numeric(df[col1]) and self._is_numeric(df[col2]):
                return "scatter"

        if num_cols == 1:
            col = df.columns[0]
            if not self._is_numeric(df[col]) and len(df) <= 10:
                return "pie"

        # 多列数值，第一列是分类 -> 分组柱状图
        if num_cols > 2 and not self._is_numeric(df.iloc[:, 0]):
            return "bar"

        return "table"

    def _is_numeric(self, series) -> bool:
        """判断是否为数值类型"""
        return pd.api.types.is_numeric_dtype(series)

    def bar_chart(self, df: pd.DataFrame, title: str, save: bool = True) -> Optional[str]:
        """生成柱状图"""
        fig, ax = plt.subplots(figsize=(10, 6))

        x_col = df.columns[0]
        y_cols = [c for c in df.columns[1:] if self._is_numeric(df[c])]

        if not y_cols:
            # 单列：计数柱状图
            df.set_index(x_col).plot(kind="bar", ax=ax, color="#378ADD", edgecolor="#185FA5")
        else:
            df.plot(x=x_col, y=y_cols, kind="bar", ax=ax, edgecolor="white", width=0.7)

        ax.set_title(title, fontsize=14, fontweight="medium", pad=15)
        ax.set_xlabel(x_col, fontsize=12)
        ax.set_ylabel("数值", fontsize=12)
        ax.legend(fontsize=10)
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()

        return self._save_or_show(fig, title, save)

    def line_chart(self, df: pd.DataFrame, title: str, save: bool = True) -> Optional[str]:
        """生成折线图"""
        fig, ax = plt.subplots(figsize=(10, 6))

        x_col = df.columns[0]
        y_cols = [c for c in df.columns[1:] if self._is_numeric(df[c])]

        for y_col in y_cols:
            ax.plot(df[x_col], df[y_col], marker="o", markersize=4, linewidth=2, label=y_col)

        ax.set_title(title, fontsize=14, fontweight="medium", pad=15)
        ax.set_xlabel(x_col, fontsize=12)
        ax.set_ylabel("数值", fontsize=12)
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3, linestyle="--")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()

        return self._save_or_show(fig, title, save)

    def pie_chart(self, df: pd.DataFrame, title: str, save: bool = True) -> Optional[str]:
        """生成饼图"""
        fig, ax = plt.subplots(figsize=(8, 8))

        col = df.columns[0]
        counts = df[col].value_counts()

        colors = ["#378ADD", "#1D9E75", "#D85A30", "#534AB7", "#EF9F27", "#D4537E", "#639922"]
        ax.pie(
            counts.values,
            labels=counts.index,
            autopct="%1.1f%%",
            startangle=90,
            colors=colors[: len(counts)],
            textprops={"fontsize": 11},
        )
        ax.set_title(title, fontsize=14, fontweight="medium", pad=15)

        return self._save_or_show(fig, title, save)

    def scatter_plot(self, df: pd.DataFrame, title: str, save: bool = True) -> Optional[str]:
        """生成散点图"""
        fig, ax = plt.subplots(figsize=(10, 6))

        x_col, y_col = df.columns[0], df.columns[1]
        ax.scatter(df[x_col], df[y_col], alpha=0.6, s=30, color="#378ADD", edgecolors="#185FA5")

        ax.set_title(title, fontsize=14, fontweight="medium", pad=15)
        ax.set_xlabel(x_col, fontsize=12)
        ax.set_ylabel(y_col, fontsize=12)
        ax.grid(True, alpha=0.3, linestyle="--")
        plt.tight_layout()

        return self._save_or_show(fig, title, save)

    def _save_or_show(self, fig, title: str, save: bool) -> Optional[str]:
        """保存图表或显示"""
        if save:
            # 文件名：标题转安全格式 + 时间戳
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:50]
            import time
            filepath = os.path.join(self.output_dir, f"{safe_name}_{int(time.time())}.png")
            fig.savefig(filepath, dpi=150, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            print(f"图表已保存: {filepath}")
            return filepath
        else:
            plt.show()
            return None
