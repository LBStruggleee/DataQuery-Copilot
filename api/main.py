"""FastAPI entry point for the DataQuery Copilot web client."""

import logging
import os
import shutil
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import charge_quota, require_api_key
from .datasets import list_datasets, register_upload, resolve_table
from .errors import APIError
from .logjson import JsonFormatter
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


# 构建期示例库路径（render.yaml / Dockerfile.api 的 buildCommand 生成在这里）
SEED_DB_PATH = "data/query.db"


def ensure_database(db_path: str, seed_path: str = SEED_DB_PATH) -> bool:
    """库文件缺失时用构建期示例库播种（P1-20：Render 挂载盘首次启动为空）。

    返回是否执行了播种；库已存在、路径与示例库相同或无示例库可播时不动作。
    """
    if Path(db_path).is_file():
        return False
    if Path(db_path).resolve() == Path(seed_path).resolve():
        return False
    if not Path(seed_path).is_file():
        logger.warning("数据库 %s 不存在，且无示例库可播种（%s）", db_path, seed_path)
        return False
    parent = Path(db_path).parent
    parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(seed_path, db_path)
    logger.info("已从示例库播种数据库: %s -> %s", seed_path, db_path)
    return True


@asynccontextmanager
async def _lifespan(application: FastAPI):
    ensure_database(os.getenv("DB_PATH", "data/query.db"), seed_path=SEED_DB_PATH)
    yield


def _envelope(code: str, message: str, data, request_id: str) -> dict:
    return {"version": "v1", "code": code, "message": message, "data": data, "request_id": request_id}


def create_app() -> FastAPI:
    if os.getenv("DQC_JSON_LOGS") == "1":
        api_logger = logging.getLogger("api")
        if not any(isinstance(h, logging.StreamHandler) and isinstance(h.formatter, JsonFormatter)
                   for h in api_logger.handlers):
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(JsonFormatter())
            api_logger.addHandler(handler)
    # P2-16：限流/配额/指标均为单进程内存态，多 worker 属误配，启动时明确告警
    try:
        workers = int(os.getenv("WEB_CONCURRENCY", "1"))
    except ValueError:
        workers = 1
    if workers > 1:
        logger.warning(
            "检测到 WEB_CONCURRENCY=%s：限流/配额/指标为单进程内存态，"
            "多 worker 下将失效且重启归零；请保持单 worker 或迁移 Redis",
            workers,
        )
    # P2-31：生产可通过 DQC_DISABLE_DOCS=1 关闭 /docs、/redoc、/openapi.json
    disable_docs = os.getenv("DQC_DISABLE_DOCS") == "1"
    application = FastAPI(
        title="DataQuery Copilot API",
        version="0.1.0",
        description="HTTP bridge for the DataQuery Copilot frontend",
        lifespan=_lifespan,
        docs_url=None if disable_docs else "/docs",
        redoc_url=None if disable_docs else "/redoc",
        openapi_url=None if disable_docs else "/openapi.json",
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

    @application.get("/api/health", include_in_schema=False)
    def health_probe() -> dict:
        """免鉴权存活探针（P0-01）：只回报进程与库文件状态，供 Render/HEALTHCHECK 使用。

        不挂 require_api_key、不进 v1 契约（include_in_schema=False）、
        不读取数据库内容，无敏感信息。
        """
        database_ready = Path(os.getenv("DB_PATH", "data/query.db")).is_file()
        return {
            "status": "ok" if database_ready else "degraded",
            "database_ready": database_ready,
        }

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
            charge_quota(service.db_path, _key)
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
