"""FastAPI entry point for the DataQuery Copilot web client."""

import os
import uuid

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

    @application.get("/api/health", response_model=HealthResponse, deprecated=True)
    def health(service: DataQueryService = Depends(get_query_service)):
        return service.health()

    @application.get("/api/schema", response_model=SchemaResponse, deprecated=True)
    def schema(service: DataQueryService = Depends(get_query_service)):
        try:
            return service.schema()
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @application.get("/api/quality", response_model=QualityResponse, deprecated=True)
    def quality(service: DataQueryService = Depends(get_query_service)):
        try:
            return service.quality()
        except Exception as error:
            raise HTTPException(status_code=500, detail="数据质量检查失败") from error

    @application.post("/api/query", response_model=QueryResponse, deprecated=True)
    def query(
        request: QueryRequest,
        service: DataQueryService = Depends(get_query_service),
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
    def health_v1(service: DataQueryService = Depends(get_query_service)):
        return _envelope("OK", "ok", service.health(), new_request_id())

    @application.get("/api/v1/schema", response_model=ApiEnvelope[SchemaResponse])
    def schema_v1(service: DataQueryService = Depends(get_query_service)):
        request_id = new_request_id()
        try:
            return _envelope("OK", "ok", service.schema(), request_id)
        except ValueError as error:
            return JSONResponse(status_code=404, content=_envelope("TABLE_NOT_FOUND", str(error), None, request_id))
        except Exception:
            return JSONResponse(status_code=500, content=_envelope("QUERY_FAILED", "表结构查询失败", None, request_id))

    @application.get("/api/v1/quality", response_model=ApiEnvelope[QualityResponse])
    def quality_v1(service: DataQueryService = Depends(get_query_service)):
        request_id = new_request_id()
        try:
            return _envelope("OK", "ok", service.quality(), request_id)
        except Exception as error:
            return JSONResponse(status_code=500, content=_envelope("QUERY_FAILED", "数据质量检查失败", None, request_id))

    @application.post("/api/v1/query", response_model=ApiEnvelope[QueryDataV1])
    def query_v1(request: QueryRequestV1, service: DataQueryService = Depends(get_query_service)):
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
