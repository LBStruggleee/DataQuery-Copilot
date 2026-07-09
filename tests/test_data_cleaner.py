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
