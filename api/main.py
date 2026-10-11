"""FastAPI entry point for the DataQuery Copilot web client."""

import logging
import os
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import anyio.to_thread
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import (
    charge_quota,
    ensure_quota_available,
    init_auth_tables,
    require_api_key,
)
from .datasets import (
    MAX_UPLOAD_BYTES,
    init_dataset_tables,
    list_datasets,
    register_upload,
    remove_dataset,
    resolve_table,
)
from .errors import APIError, ErrorCode
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
from .request_context import RequestContextMiddleware, get_request_id
from .services import DataQueryService

load_dotenv()

logger = logging.getLogger(__name__)

# engine 原文只进服务端日志；客户端一律收通用文案（request_id 关联两端）
_SAFE_MESSAGES = {
    "SQL_REJECTED": "SQL 安全校验未通过",
    "SERVICE_UNAVAILABLE": "服务暂不可用，请稍后重试",
    "QUERY_FAILED": "查询服务执行失败",
    # P2-19/P2-23：上传校验细节（含 pandas 报错原文）不出服务端
    "UPLOAD_REJECTED": "文件未通过上传校验，请检查格式与大小",
}


def _public_message(code: str, detail: str) -> str:
    return _SAFE_MESSAGES.get(code, detail)


# P1-07：上传分块大小（流式限量读取）
_UPLOAD_CHUNK_BYTES = 1024 * 1024


def get_query_service() -> DataQueryService:
    return DataQueryService(
        db_path=os.getenv("DB_PATH", "data/query.db"),
        table_name=os.getenv("TABLE_NAME", "orders"),
    )


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
    db_path = os.getenv("DB_PATH", "data/query.db")
    ensure_database(db_path, seed_path=SEED_DB_PATH)
    # P1-06：鉴权/数据集表在启动期初始化一次，请求路径不再执行 DDL
    init_auth_tables(db_path)
    init_dataset_tables(db_path)
    yield


def _envelope(code: str, message: str, data, request_id: str) -> dict:
    return {"version": "v1", "code": code, "message": message, "data": data, "request_id": request_id}


def _content_length_exceeds(request: Request, max_bytes: int) -> bool:
    """P1-07：读取前的 Content-Length 预检（头缺失或非数字时放行，交给分块计数兜底）。"""
    declared = request.headers.get("content-length")
    if not declared:
        return False
    try:
        return int(declared) > max_bytes
    except ValueError:
        return False


async def _read_upload_bounded(file: UploadFile, max_bytes: int) -> bytes:
    """P1-07：分块流式读取，边读边计数，超限立即拒绝——不再全量 read() 后才检查。

    Starlette 对超过 1MB 已落盘的 UploadFile 分块读取走线程池，不阻塞事件循环；
    ≤1MB 的内存态分块读取本身为微秒级小拷贝，可接受。
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise APIError(ErrorCode.UPLOAD_REJECTED, 422, "文件超过 50MB 上限")
        chunks.append(chunk)
    return b"".join(chunks)


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
    # P2-18：request_id 中间件最后添加 → 最先执行，保证后续所有环节都能读到
    application.add_middleware(RequestContextMiddleware)

    @application.exception_handler(APIError)
    async def api_error_handler(request, exc):
        """领域异常统一包信封（含鉴权依赖抛出的，路由 try/except 覆盖不到）。"""
        request_id = get_request_id(request)
        logger.warning(
            "api error response",
            extra={"request_id": request_id, "code": exc.code.value, "detail": exc.message},
        )
        return JSONResponse(
            status_code=exc.status,
            content=_envelope(exc.code.value, _public_message(exc.code.value, exc.message), None, request_id),
        )

    @application.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        """Pydantic 校验失败包信封。"""
        # 直接调 API 传非法分页等场景与问题校验共用 INVALID_QUESTION 422
        errors = exc.errors() if hasattr(exc, "errors") else []
        detail = errors[0].get("msg", "请求参数校验失败") if errors else "请求参数校验失败"
        return JSONResponse(
            status_code=422,
            content=_envelope("INVALID_QUESTION", f"请求参数校验失败: {detail}", None, get_request_id(request)),
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc):
        """P2-17：兜底包信封（如 TABLE_NAME 非法时依赖内抛 ValueError），
        不再漏出 Starlette 裸 500 {"detail": "Internal Server Error"}。"""
        request_id = get_request_id(request)
        logger.exception("unhandled exception", extra={"request_id": request_id, "code": "QUERY_FAILED"})
        return JSONResponse(
            status_code=500,
            content=_envelope("QUERY_FAILED", _public_message("QUERY_FAILED", "服务内部错误"), None, request_id),
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
    def health_v1(request: Request,
                  service: DataQueryService = Depends(get_query_service),
                  _key: str = Depends(require_api_key)):
        request_id = get_request_id(request)
        try:
            return _envelope("OK", "ok", service.health(), request_id)
        except Exception:
            # P1-08：意外异常必须留服务端日志（含 request_id 与堆栈），不再静默吞掉
            logger.exception("v1 health failed", extra={"request_id": request_id, "code": "QUERY_FAILED"})
            return JSONResponse(
                status_code=500,
                content=_envelope("QUERY_FAILED", _public_message("QUERY_FAILED", "健康检查失败"), None, request_id),
            )

    @application.get("/api/v1/schema", response_model=ApiEnvelope[SchemaResponse])
    def schema_v1(request: Request,
                  service: DataQueryService = Depends(get_query_service),
                  _key: str = Depends(require_api_key),
                  dataset: str | None = Query(default=None)):
        request_id = get_request_id(request)
        try:
            table = resolve_table(service.db_path, dataset)
            return _envelope("OK", "ok", service.schema(table), request_id)
        except ValueError as error:
            return JSONResponse(
                status_code=404,
                content=_envelope("TABLE_NOT_FOUND", _public_message("TABLE_NOT_FOUND", str(error)), None, request_id),
            )
        except APIError as error:
            return JSONResponse(
                status_code=error.status,
                content=_envelope(error.code.value, _public_message(error.code.value, error.message), None, request_id),
            )
        except Exception:
            logger.exception("v1 schema failed", extra={"request_id": request_id, "code": "QUERY_FAILED"})
            return JSONResponse(
                status_code=500,
                content=_envelope("QUERY_FAILED", _public_message("QUERY_FAILED", "表结构查询失败"), None, request_id),
            )

    @application.get("/api/v1/quality", response_model=ApiEnvelope[QualityResponse])
    def quality_v1(request: Request,
                   service: DataQueryService = Depends(get_query_service),
                   _key: str = Depends(require_api_key),
                   dataset: str | None = Query(default=None)):
        request_id = get_request_id(request)
        try:
            table = resolve_table(service.db_path, dataset)
            return _envelope("OK", "ok", service.quality(table), request_id)
        except APIError as error:
            return JSONResponse(
                status_code=error.status,
                content=_envelope(error.code.value, _public_message(error.code.value, error.message), None, request_id),
            )
        except Exception:
            logger.exception("v1 quality failed", extra={"request_id": request_id, "code": "QUERY_FAILED"})
            return JSONResponse(
                status_code=500,
                content=_envelope("QUERY_FAILED", _public_message("QUERY_FAILED", "数据质量检查失败"), None, request_id),
            )

    @application.post("/api/v1/query", response_model=ApiEnvelope[QueryDataV1])
    def query_v1(request: Request,
                 payload: QueryRequestV1,
                 service: DataQueryService = Depends(get_query_service),
                 key_hash: str = Depends(require_api_key)):
        request_id = get_request_id(request)
        question = payload.question.strip()
        if not question:
            return JSONResponse(status_code=422, content=_envelope("INVALID_QUESTION", "问题不能为空", None, request_id))
        record_query()
        try:
            table = resolve_table(service.db_path, payload.dataset)
            # SUP-01 配套：配额已尽提前 429，不白付一次 LLM 成本
            ensure_quota_available(service.db_path, key_hash)
            data = service.query_page(question, payload.clean_result, payload.max_retries, payload.page, payload.page_size, table_name=table)
            # SUP-01：查询成功后才记账，失败不扣；P2-15：记账为 BEGIN IMMEDIATE 原子事务
            charge_quota(service.db_path, key_hash)
        except APIError as error:
            logger.warning("v1 query failed", extra={"request_id": request_id, "code": error.code.value, "detail": error.message})
            return JSONResponse(status_code=error.status, content=_envelope(error.code.value, _public_message(error.code.value, error.message), None, request_id))
        except Exception:
            logger.exception("v1 query failed", extra={"request_id": request_id, "code": "QUERY_FAILED"})
            return JSONResponse(status_code=500, content=_envelope("QUERY_FAILED", _public_message("QUERY_FAILED", "查询服务执行失败"), None, request_id))
        message = "结果超过 100 行上限，仅返回前 100 行" if data["truncated"] else "ok"
        return _envelope("OK", message, data, request_id)

    @application.get("/api/v1/datasets", response_model=ApiEnvelope[list[DatasetInfo]])
    def datasets_v1(request: Request,
                    service: DataQueryService = Depends(get_query_service),
                    _key: str = Depends(require_api_key)):
        request_id = get_request_id(request)
        try:
            return _envelope("OK", "ok", list_datasets(service.db_path), request_id)
        except Exception:
            logger.exception("v1 datasets failed", extra={"request_id": request_id, "code": "QUERY_FAILED"})
            return JSONResponse(
                status_code=500,
                content=_envelope("QUERY_FAILED", _public_message("QUERY_FAILED", "数据集列表查询失败"), None, request_id),
            )

    @application.get("/api/v1/metrics", response_model=ApiEnvelope[MetricsData])
    def metrics_v1(request: Request, _key: str = Depends(require_api_key)):
        return _envelope("OK", "ok", snapshot(), get_request_id(request))

    @application.post("/api/v1/datasets", response_model=ApiEnvelope[DatasetInfo])
    async def upload_dataset_v1(request: Request,
                                service: DataQueryService = Depends(get_query_service),
                                key_hash: str = Depends(require_api_key),
                                file: UploadFile = File(...)):
        request_id = get_request_id(request)
        db_path = service.db_path
        try:
            # P1-10：上传计入日配额——已尽则提前 429（sqlite 下沉线程池，不阻塞事件循环）
            await anyio.to_thread.run_sync(ensure_quota_available, db_path, key_hash)
            # P1-07：先做 Content-Length 预检，再分块流式读取，超限立即拒绝
            if _content_length_exceeds(request, MAX_UPLOAD_BYTES):
                raise APIError(ErrorCode.UPLOAD_REJECTED, 422, "文件超过 50MB 上限")
            content = await _read_upload_bounded(file, MAX_UPLOAD_BYTES)
            # P1-06：pandas 解析 + to_sql 重活下沉线程池，不阻塞事件循环
            info = await anyio.to_thread.run_sync(
                register_upload, db_path, file.filename or "upload.csv", content)
            try:
                # P1-10：上传成功后才记账（与 SUP-01 同口径）
                await anyio.to_thread.run_sync(charge_quota, db_path, key_hash)
            except APIError:
                # 并发竞态下配额恰在注册后耗尽：回滚注册，不留下未计费的数据集
                remove_dataset(db_path, info["id"], info["table_name"])
                raise
            return _envelope("OK", "ok", info, request_id)
        except APIError as error:
            logger.warning("v1 upload rejected", extra={"request_id": request_id, "code": error.code.value, "detail": error.message})
            return JSONResponse(status_code=error.status, content=_envelope(error.code.value, _public_message(error.code.value, error.message), None, request_id))
        except Exception:
            logger.exception("v1 upload failed", extra={"request_id": request_id, "code": "QUERY_FAILED"})
            return JSONResponse(
                status_code=500,
                content=_envelope("QUERY_FAILED", _public_message("QUERY_FAILED", "文件上传失败"), None, request_id),
            )

    return application


app = create_app()
