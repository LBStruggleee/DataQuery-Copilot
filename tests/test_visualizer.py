"""
Visualizer 单元测试 — 图表类型检测 + 图表生成
"""
import os
import tempfile

import pandas as pd
import pytest

from src.visualizer import Visualizer


@pytest.fixture
def viz():
    """输出到临时目录的 Visualizer"""
    tmp_dir = tempfile.mkdtemp(prefix="test_viz_")
    v = Visualizer(output_dir=tmp_dir)
    yield v
    import shutil
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)


# ── 图表类型检测 ────────────────────────────────────────

def test_detect_bar_chart(viz):
    """分类+数值 → 柱状图"""
    df = pd.DataFrame({"category": ["A", "B", "C"], "amount": [100, 200, 150]})
    assert viz._detect_chart_type(df) == "bar"


def test_detect_line_chart(viz):
    """日期+数值 → 折线图"""
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
        "amount": [100, 200, 150],
    })
    assert viz._detect_chart_type(df) == "line"


def test_detect_scatter_chart(viz):
    """数值+数值 → 散点图"""
    df = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [10, 20, 15, 25, 30]})
    assert viz._detect_chart_type(df) == "scatter"


def test_detect_pie_chart(viz):
    """单列分类（少量）→ 饼图"""
    df = pd.DataFrame({"category": ["A", "B", "A", "C", "B", "A"]})
    assert viz._detect_chart_type(df) == "pie"


def test_detect_table(viz):
    """不适合图表的 → table"""
    df = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
    assert viz._detect_chart_type(df) == "table"


def test_detect_bar_too_many_categories(viz):
    """超过30个类别不生成柱状图"""
    df = pd.DataFrame({
        "cat": [f"C{i}" for i in range(35)],
        "val": range(35),
    })
    assert viz._detect_chart_type(df) != "bar"


def test_detect_multi_col_bar(viz):
    """多列数值+分类 → 分组柱状图"""
    df = pd.DataFrame({
        "category": ["A", "B", "C"],
        "sales": [100, 200, 150],
        "profit": [30, 50, 40],
    })
    assert viz._detect_chart_type(df) == "bar"


# ── 图表生成 ────────────────────────────────────────────

def test_bar_chart_generation(viz):
    """测试柱状图生成并保存"""
    df = pd.DataFrame({"category": ["A", "B", "C"], "amount": [100, 200, 150]})
    path = viz.bar_chart(df, "测试柱状图", save=True)
    assert path is not None
    assert os.path.exists(path)


def test_line_chart_generation(viz):
    """测试折线图生成"""
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
        "amount": [100, 200, 150],
    })
    path = viz.line_chart(df, "测试折线图", save=True)
    assert path is not None
    assert os.path.exists(path)


def test_pie_chart_generation(viz):
    """测试饼图生成"""
    df = pd.DataFrame({"category": ["A", "B", "A", "C", "B"]})
    path = viz.pie_chart(df, "测试饼图", save=True)
    assert path is not None
    assert os.path.exists(path)


def test_scatter_plot_generation(viz):
    """测试散点图生成"""
    df = pd.DataFrame({"x": [1, 2, 3, 4], "y": [10, 20, 15, 25]})
    path = viz.scatter_plot(df, "测试散点图", save=True)
    assert path is not None
    assert os.path.exists(path)


def test_auto_visualize_empty(viz):
    """测试空数据"""
    df = pd.DataFrame()
    path = viz.auto_visualize(df, "空数据")
    assert path is None


def test_auto_visualize_bar(viz):
    """测试自动识别+生成柱状图"""
    df = pd.DataFrame({"cat": ["A", "B", "C"], "val": [10, 20, 30]})
    path = viz.auto_visualize(df, "自动柱状图", save=True)
    assert path is not None
    assert os.path.exists(path)


def test_save_filename_generation(viz):
    """测试文件名生成（时间戳+安全字符）"""
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    path = viz.scatter_plot(df, "测试/文件名:特殊字符?", save=True)
    assert path is not None
    # 文件名不应包含特殊字符
    basename = os.path.basename(path)
    assert "/" not in basename
    assert ":" not in basename
    assert "?" not in basename
