"""Phase 5: JSON 日志格式。"""
import json
import logging


def test_json_formatter_emits_structured_log():
    from api.logjson import JsonFormatter

    record = logging.LogRecord("api.main", logging.WARNING, __file__, 10, "v1 query failed", (), None)
    record.request_id = "req_abc"
    record.code = "SQL_REJECTED"
    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "WARNING"
    assert payload["logger"] == "api.main"
    assert payload["message"] == "v1 query failed"
    assert payload["request_id"] == "req_abc"
    assert payload["code"] == "SQL_REJECTED"


def test_json_formatter_without_extras():
    from api.logjson import JsonFormatter

    record = logging.LogRecord("api.main", logging.INFO, __file__, 10, "plain", (), None)
    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "plain"
    assert "request_id" not in payload


def test_json_formatter_emits_client_ip_for_auth_audit():
    """P2-27：鉴权失败审计日志的 client_ip 需要进入 JSON 输出。"""
    from api.logjson import JsonFormatter

    record = logging.LogRecord("api.auth", logging.WARNING, __file__, 10, "auth failure audit", (), None)
    record.request_id = "req_abc"
    record.client_ip = "203.0.113.7"
    payload = json.loads(JsonFormatter().format(record))

    assert payload["client_ip"] == "203.0.113.7"
    assert payload["request_id"] == "req_abc"
