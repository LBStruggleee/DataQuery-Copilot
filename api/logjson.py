"""Phase 5: JSON 日志格式（DQC_JSON_LOGS=1 时启用，见 api/main.py）。"""

import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """单行 JSON 日志；request_id/code/detail 等 extra 字段 presence-dependent."""

    EXTRA_KEYS = ("request_id", "code", "detail")

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in self.EXTRA_KEYS:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)
