"""v1 契约测试：错误码、分页服务、v1 路由、OpenAPI 契约。"""


def test_error_codes_are_stable():
    from api.errors import APIError, ErrorCode

    assert ErrorCode.SQL_REJECTED.value == "SQL_REJECTED"
    err = APIError(ErrorCode.TABLE_NOT_FOUND, 404, "数据表不存在: orders")
    assert err.code is ErrorCode.TABLE_NOT_FOUND
    assert err.status == 404
    assert err.message == "数据表不存在: orders"
