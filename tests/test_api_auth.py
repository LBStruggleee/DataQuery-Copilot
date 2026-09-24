"""Phase 1: API Key 鉴权、限流、配额。"""


def test_auth_error_codes_are_stable():
    from api.errors import ErrorCode

    assert ErrorCode.AUTH_REQUIRED.value == "AUTH_REQUIRED"
    assert ErrorCode.RATE_LIMITED.value == "RATE_LIMITED"
