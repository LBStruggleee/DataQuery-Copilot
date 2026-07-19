"""FastAPI entry point for the DataQuery Copilot web client."""

import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
    QualityResponse,
    SchemaResponse,
)
from .services import DataQueryService

load_dotenv()


def get_query_service() -> DataQueryService:
    return DataQueryService(
        db_path=os.getenv("DB_PATH", "data/query.db"),
        table_name=os.getenv("TABLE_NAME", "orders"),
    )


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

    @application.get("/api/health", response_model=HealthResponse)
    def health(service: DataQueryService = Depends(get_query_service)):
        return service.health()

    @application.get("/api/schema", response_model=SchemaResponse)
    def schema(service: DataQueryService = Depends(get_query_service)):
        try:
            return service.schema()
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @application.get("/api/quality", response_model=QualityResponse)
    def quality(service: DataQueryService = Depends(get_query_service)):
        try:
            return service.quality()
        except Exception as error:
            raise HTTPException(status_code=500, detail="数据质量检查失败") from error

    @application.post("/api/query", response_model=QueryResponse)
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

    return application


app = create_app()
