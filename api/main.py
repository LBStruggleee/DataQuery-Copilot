"""FastAPI entry point for the DataQuery Copilot web client."""

import logging
import os
import uuid

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import require_api_key
from .datasets import list_datasets, register_upload, resolve_table
from .errors import APIError
from .metrics import MetricsMiddleware, record_query, snapshot
from .models import (
    ApiEnvelope,
    DatasetInfo,
    HealthResponse,
    MetricsData,
    QualityResponse,
    QueryDataV1,
    QueryRequestV1,
    SchemaResponse,
)
from .services import DataQueryService

load_dotenv()

logger = logging.getLogger(__name__)

# engine 原文只进服务端日志；客户端一律收通用文案（request_id 关联两端）
_SAFE_MESSAGES = {
    "SQL_REJECTED": "SQL 安全校验未通过",
    "SERVICE_UNAVAILABLE": "服务暂不可用，请稍后重试",
    "QUERY_FAILED": "查询服务执行失败",
}


def _public_message(code: str, detail: str) -> str:
    return _SAFE_MESSAGES.get(code, detail)


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
    application.add_middleware(MetricsMiddleware)

    @application.exception_handler(APIError)
    async def api_error_handler(request, exc):
        """领域异常统一包信封（含鉴权依赖抛出的，路由 try/except 覆盖不到）。"""
        return JSONResponse(
            status_code=exc.status,
            content=_envelope(exc.code.value, exc.message, None, new_request_id()),
        )

    @application.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        """Pydantic 校验失败包信封。"""
        # 直接调 API 传非法分页等场景与问题校验共用 INVALID_QUESTION 422
        errors = exc.errors() if hasattr(exc, "errors") else []
        detail = errors[0].get("msg", "请求参数校验失败") if errors else "请求参数校验失败"
        return JSONResponse(
            status_code=422,
            content=_envelope("INVALID_QUESTION", f"请求参数校验失败: {detail}", None, new_request_id()),
        )

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
                  _key: str = Depends(require_api_key),
                  dataset: str | None = Query(default=None)):
        request_id = new_request_id()
        try:
            table = resolve_table(service.db_path, dataset)
            return _envelope("OK", "ok", service.schema(table), request_id)
        except ValueError as error:
            return JSONResponse(status_code=404, content=_envelope("TABLE_NOT_FOUND", str(error), None, request_id))
        except APIError as error:
            return JSONResponse(status_code=error.status, content=_envelope(error.code.value, error.message, None, request_id))
        except Exception:
            return JSONResponse(status_code=500, content=_envelope("QUERY_FAILED", "表结构查询失败", None, request_id))

    @application.get("/api/v1/quality", response_model=ApiEnvelope[QualityResponse])
    def quality_v1(service: DataQueryService = Depends(get_query_service),
                   _key: str = Depends(require_api_key),
                   dataset: str | None = Query(default=None)):
        request_id = new_request_id()
        try:
            table = resolve_table(service.db_path, dataset)
            return _envelope("OK", "ok", service.quality(table), request_id)
        except APIError as error:
            return JSONResponse(status_code=error.status, content=_envelope(error.code.value, error.message, None, request_id))
        except Exception as error:
            return JSONResponse(status_code=500, content=_envelope("QUERY_FAILED", "数据质量检查失败", None, request_id))

    @application.post("/api/v1/query", response_model=ApiEnvelope[QueryDataV1])
    def query_v1(request: QueryRequestV1, service: DataQueryService = Depends(get_query_service),
                 _key: str = Depends(require_api_key)):
        request_id = new_request_id()
        question = request.question.strip()
        if not question:
            return JSONResponse(status_code=422, content=_envelope("INVALID_QUESTION", "问题不能为空", None, request_id))
        record_query()
        try:
            table = resolve_table(service.db_path, request.dataset)
            data = service.query_page(question, request.clean_result, request.max_retries, request.page, request.page_size, table_name=table)
        except APIError as error:
            logger.warning("v1 query failed", extra={"request_id": request_id, "code": error.code.value, "detail": error.message})
            return JSONResponse(status_code=error.status, content=_envelope(error.code.value, _public_message(error.code.value, error.message), None, request_id))
        except Exception:
            logger.warning("v1 query failed", extra={"request_id": request_id, "code": "QUERY_FAILED"})
            return JSONResponse(status_code=500, content=_envelope("QUERY_FAILED", "查询服务执行失败", None, request_id))
        message = "结果超过 100 行上限，仅返回前 100 行" if data["truncated"] else "ok"
        return _envelope("OK", message, data, request_id)

    @application.get("/api/v1/datasets", response_model=ApiEnvelope[list[DatasetInfo]])
    def datasets_v1(service: DataQueryService = Depends(get_query_service),
                    _key: str = Depends(require_api_key)):
        request_id = new_request_id()
        try:
            return _envelope("OK", "ok", list_datasets(service.db_path), request_id)
        except Exception:
            return JSONResponse(status_code=500, content=_envelope("QUERY_FAILED", "数据集列表查询失败", None, request_id))

    @application.get("/api/v1/metrics", response_model=ApiEnvelope[MetricsData])
    def metrics_v1(_key: str = Depends(require_api_key)):
        return _envelope("OK", "ok", snapshot(), new_request_id())

    @application.post("/api/v1/datasets", response_model=ApiEnvelope[DatasetInfo])
    async def upload_dataset_v1(service: DataQueryService = Depends(get_query_service),
                                _key: str = Depends(require_api_key),
                                file: UploadFile = File(...)):
        request_id = new_request_id()
        try:
            content = await file.read()
            info = register_upload(service.db_path, file.filename or "upload.csv", content)
            return _envelope("OK", "ok", info, request_id)
        except APIError as error:
            return JSONResponse(status_code=error.status, content=_envelope(error.code.value, error.message, None, request_id))
        except Exception:
            return JSONResponse(status_code=500, content=_envelope("QUERY_FAILED", "文件上传失败", None, request_id))

    return application


app = create_app()
