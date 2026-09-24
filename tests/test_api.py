"""Service-level unit tests that never call the real LLM service."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from api.services import DataQueryService


def test_records_are_json_safe():
    df = pd.DataFrame(
        {
            "created_at": [datetime(2026, 7, 20, 10, 30)],
            "amount": [np.float64(12.5)],
            "optional": [np.nan],
        }
    )

    records = DataQueryService._records(df)

    assert records == [
        {
            "created_at": "2026-07-20T10:30:00",
            "amount": 12.5,
            "optional": None,
        }
    ]


@pytest.mark.parametrize("table_name", ["orders; DROP TABLE orders", "order-items", ""])
def test_service_rejects_unsafe_table_names(table_name):
    with pytest.raises(ValueError, match="无效的数据表名"):
        DataQueryService("data/query.db", table_name)
