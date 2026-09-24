"""FastAPI entry point for the DataQuery Copilot web client."""

import os
import uuid

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import require_api_key
from .errors import APIError
from .models import (
    ApiEnvelope,
    HealthResponse,
    QualityResponse,
    QueryDataV1,
    QueryRequest,
    QueryRequestV1,
    QueryResponse,
    SchemaResponse,
)
from .services import DataQueryService

load_dotenv()


def get_query_service() -> DataQueryService:
    return DataQueryService(
        db_path=os.getenv("DB_PATH", "data/query.db"),
        table_name=os.getenv("TABLE_NAME", "orders"),
    )


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:12]}"


def _envelope(code: str, message: str, data, request_id: str) -> dict:
    return {"version": "v1", "code": code, "message": message, "data": data, "request_id": request_id}


def create_app() -> FastAPI:
    application = FastAPI(
        title="DataQuery Copilot API",
        version="0.1.0",
        description="HTTP bridge for the DataQuery Copilot frontend",
    )

    origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @application.exception_handler(APIError)
    async def api_error_handler(request, exc):
        """领域异常统一包信封（含鉴权依赖抛出的，路由 try/except 覆盖不到）。"""
        return JSONResponse(
            status_code=exc.status,
            content=_envelope(exc.code.value, exc.message, None, new_request_id()),
        )

    @application.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        """v1 路径的 Pydantic 校验失败包信封；非 v1 路径保持默认行为（v0 字节级兼容）。"""
        if not request.url.path.startswith("/api/v1"):
            return await request_validation_exception_handler(request, exc)
        # 直接调 API 传非法分页等场景与问题校验共用 INVALID_QUESTION 422
        errors = exc.errors() if hasattr(exc, "errors") else []
        detail = errors[0].get("msg", "请求参数校验失败") if errors else "请求参数校验失败"
        return JSONResponse(
            status_code=422,
            content=_envelope("INVALID_QUESTION", f"请求参数校验失败: {detail}", None, new_request_id()),
        )

    @application.get("/api/health", response_model=HealthResponse, deprecated=True)
    def health(service: DataQueryService = Depends(get_query_service),
               _key: str = Depends(require_api_key)):
        return service.health()

    @application.get("/api/schema", response_model=SchemaResponse, deprecated=True)
    def schema(service: DataQueryService = Depends(get_query_service),
               _key: str = Depends(require_api_key)):
        try:
            return service.schema()
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @application.get("/api/quality", response_model=QualityResponse, deprecated=True)
    def quality(service: DataQueryService = Depends(get_query_service),
                _key: str = Depends(require_api_key)):
        try:
            return service.quality()
        except Exception as error:
            raise HTTPException(status_code=500, detail="数据质量检查失败") from error

    @application.post("/api/query", response_model=QueryResponse, deprecated=True)
    def query(
        request: QueryRequest,
        service: DataQueryService = Depends(get_query_service),
        _key: str = Depends(require_api_key),
    ):
        try:
            return service.query(
                question=request.question.strip(),
                clean_result=request.clean_result,
                max_retries=request.max_retries,
            )
        except Exception as error:
            raise HTTPException(status_code=500, detail="查询服务执行失败") from error

    @application.get("/api/v1/health", response_model=ApiEnvelope[HealthResponse])
    def health_v1(service: DataQueryService = Depends(get_query_service),
                  _key: str = Depends(require_api_key)):
        request_id = new_request_id()
        try:
            return _envelope("OK", "ok", service.health(), request_id)
        except Exception:
            return JSONResponse(status_code=500, content=_envelope("QUERY_FAILED", "健康检查失败", None, request_id))

    @application.get("/api/v1/schema", response_model=ApiEnvelope[SchemaResponse])
    def schema_v1(service: DataQueryService = Depends(get_query_service),
                  _key: str = Depends(require_api_key)):
        request_id = new_request_id()
        try:
            return _envelope("OK", "ok", service.schema(), request_id)
        except ValueError as error:
            return JSONResponse(status_code=404, content=_envelope("TABLE_NOT_FOUND", str(error), None, request_id))
        except Exception:
            return JSONResponse(status_code=500, content=_envelope("QUERY_FAILED", "表结构查询失败", None, request_id))

    @application.get("/api/v1/quality", response_model=ApiEnvelope[QualityResponse])
    def quality_v1(service: DataQueryService = Depends(get_query_service),
                   _key: str = Depends(require_api_key)):
        request_id = new_request_id()
        try:
            return _envelope("OK", "ok", service.quality(), request_id)
        except Exception as error:
            return JSONResponse(status_code=500, content=_envelope("QUERY_FAILED", "数据质量检查失败", None, request_id))

    @application.post("/api/v1/query", response_model=ApiEnvelope[QueryDataV1])
    def query_v1(request: QueryRequestV1, service: DataQueryService = Depends(get_query_service),
                 _key: str = Depends(require_api_key)):
        request_id = new_request_id()
        question = request.question.strip()
        if not question:
            return JSONResponse(status_code=422, content=_envelope("INVALID_QUESTION", "问题不能为空", None, request_id))
        try:
            data = service.query_page(question, request.clean_result, request.max_retries, request.page, request.page_size)
        except APIError as error:
            return JSONResponse(status_code=error.status, content=_envelope(error.code.value, error.message, None, request_id))
        except Exception:
            return JSONResponse(status_code=500, content=_envelope("QUERY_FAILED", "查询服务执行失败", None, request_id))
        message = "结果超过 100 行上限，仅返回前 100 行" if data["truncated"] else "ok"
        return _envelope("OK", message, data, request_id)

    return application


app = create_app()
