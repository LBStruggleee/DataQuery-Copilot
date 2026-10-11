"""
DataCleaner 单元测试
"""
import pandas as pd
import numpy as np
import pytest

from src.data_cleaner import DataCleaner


@pytest.fixture
def dirty_data():
    """带缺失值和异常值的测试数据"""
    return pd.DataFrame({
        "amount": [100.0, 200.0, np.nan, 150.0, 5000.0],  # 1个缺失 + 1个异常
        "category": ["A", "B", "A", None, "B"],           # 1个缺失
        "quantity": [1, 2, 3, 4, 5],
    })


def test_handle_missing_values_auto(dirty_data):
    """测试 auto 策略缺失值处理"""
    cleaner = DataCleaner()
    cleaned = cleaner.handle_missing_values(dirty_data, strategy="auto")
    assert cleaned.isna().sum().sum() == 0  # 无缺失值


def test_handle_missing_values_strict(dirty_data):
    """测试 strict 策略（直接删除）"""
    cleaner = DataCleaner()
    cleaned = cleaner.handle_missing_values(dirty_data, strategy="strict")
    assert len(cleaned) == 3  # 删掉2行有缺失的


def test_detect_outliers(dirty_data):
    """测试异常值检测"""
    cleaner = DataCleaner()
    # 先填充缺失值，否则检测会报错
    data = dirty_data.dropna(subset=["amount"])
    outliers = cleaner.detect_outliers(data, "amount", method="iqr")
    assert len(outliers) >= 1  # 5000.0 是异常值


def test_standardize_formats(dirty_data):
    """测试格式标准化"""
    cleaner = DataCleaner()
    cleaned = cleaner.standardize_formats(dirty_data)
    # 字符串列应该被 strip
    assert cleaned["category"].iloc[0] == "A"


def test_quality_report(dirty_data):
    """测试数据质量报告"""
    cleaner = DataCleaner()
    report = cleaner.quality_report(dirty_data)
    assert report["total_rows"] == 5
    assert report["total_columns"] == 3
    assert "amount" in report["missing_values"]
    assert report["missing_values"]["amount"] == 1


def test_clean_full_flow(dirty_data):
    """测试一键清洗完整流程"""
    cleaner = DataCleaner()
    cleaned = cleaner.clean(dirty_data, strategy="auto")
    assert cleaned.isna().sum().sum() == 0
    assert len(cleaned) == 5  # auto 策略不删除行


# ── P1-02: 缺失值不再被污染成字符串 'None' ──────────────

def test_standardize_formats_preserves_nan():
    """P1-02: astype(str) 污染修复——缺失值保留为 NaN 而非字面量 'None'"""
    cleaner = DataCleaner()
    df = pd.DataFrame({"name": [" alice ", None, " bob "]})
    cleaned = cleaner.standardize_formats(df)
    assert cleaned["name"].iloc[0] == "alice"
    assert pd.isna(cleaned["name"].iloc[1])  # NaN 保留
    assert cleaned["name"].iloc[2] == "bob"


def test_standardize_formats_keeps_non_string_values():
    """P1-02: object 列中的非字符串值不受 strip 影响"""
    cleaner = DataCleaner()
    df = pd.DataFrame({"v": pd.Series([1, " a ", None], dtype=object)})
    cleaned = cleaner.standardize_formats(df)
    assert cleaned["v"].iloc[0] == 1
    assert cleaned["v"].iloc[1] == "a"
    assert pd.isna(cleaned["v"].iloc[2])


# ── P2-06: 数值判定认 pandas 可空扩展类型 ───────────────

def test_handle_missing_values_fill_nullable_int():
    """P2-06: Int64 列走数值分支，fillna('unknown') 不再 TypeError"""
    cleaner = DataCleaner()
    df = pd.DataFrame({"amount": pd.array([1, None, 3], dtype="Int64")})
    cleaned = cleaner.handle_missing_values(df, strategy="fill")
    assert cleaned["amount"].isna().sum() == 0


def test_handle_missing_values_auto_nullable_int():
    """P2-06: Int64 列 auto 策略用中位数填充"""
    cleaner = DataCleaner()
    df = pd.DataFrame({"amount": pd.array([1, None, 3], dtype="Int64")})
    cleaned = cleaner.handle_missing_values(df, strategy="auto")
    assert cleaned["amount"].isna().sum() == 0
    assert cleaned["amount"].tolist() == [1, 2, 3]


def test_detect_outliers_nullable_int():
    """P2-06: Int64 列可正常检测异常值"""
    cleaner = DataCleaner()
    df = pd.DataFrame({"amount": pd.array([1, 2, 3, 1000], dtype="Int64")})
    outliers = cleaner.detect_outliers(df, "amount", method="iqr")
    assert len(outliers) == 1


# ── P2-07: 未知 method 显式报错 ─────────────────────────

def test_detect_outliers_unknown_method_raises():
    """P2-07: 未支持的 method 抛 ValueError，不再静默返回空表"""
    cleaner = DataCleaner()
    df = pd.DataFrame({"amount": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError):
        cleaner.detect_outliers(df, "amount", method="zscore")
