"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.trace import reset_request_id, set_request_id
from app.db.alembic import database_is_at_head, ensure_database_at_head
from app.db.migrations import schema_is_ready
from app.db.session import SessionLocal, engine

logger = logging.getLogger("app")


class TraceLogFilter(logging.Filter):
    """把 trace/request 上下文注入日志记录（缺省以 - 占位）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        from app.core.trace import current_request_id, current_trace_id

        record.trace_id = current_trace_id() or "-"
        record.request_id = current_request_id() or "-"
        return True


_handler = logging.StreamHandler()
_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s "
        "[trace=%(trace_id)s req=%(request_id)s] %(message)s"
    )
)
_handler.addFilter(TraceLogFilter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求分配 request_id（可复用外部传入值）。

    request_id 只用于 HTTP 层排障关联；工业业务链路 trace_id 由
    领域入口（网关同步/订阅 flush/遥测摄入/报警分析）独立管理。
    """

    async def dispatch(self, request: Request, call_next):
        external = request.headers.get("x-request-id", "").strip()
        rid = external[:64] if external else uuid.uuid4().hex
        token = set_request_id(rid)
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers["X-Request-ID"] = rid
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_database_at_head(
        engine,
        auto_migrate=settings.auto_migrate_on_startup,
    )
    if settings.SEED_ON_STARTUP:
        from app.seed import run_seed_if_empty

        run_seed_if_empty()

    # 工业协议网关（OPC UA，只读）：默认关闭，开启后随 API 进程轮询。
    gateway_runtime = None
    if settings.GATEWAY_ENABLED:
        from app.industrial_gateway.opcua.service import get_gateway_runtime

        gateway_runtime = get_gateway_runtime()
        gateway_runtime.start()
        logger.info("Industrial gateway started (mode=%s)", settings.GATEWAY_MODE)
    try:
        yield
    finally:
        if gateway_runtime is not None:
            gateway_runtime.stop()
            await gateway_runtime.wait_stopped()
            logger.info("Industrial gateway stopped")


app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    description="基于 AI Agent 的工业设备智能运维与预测性维护平台 API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["health"])
def root():
    return {"app": settings.APP_NAME, "status": "running", "docs": "/docs"}


@app.get("/health", tags=["health"])
def health():
    db_status = "ok"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db_status = "unavailable"
    return {
        "status": "ok",
        "database": db_status,
        "ai_enabled": settings.ai_actually_enabled,
    }


@app.get("/ready", tags=["health"])
def ready(response: Response):
    redis_status = "disabled"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        ready_status = schema_is_ready(engine) and database_is_at_head(engine)
        if settings.REDIS_URL:
            Redis.from_url(settings.REDIS_URL).ping()
            redis_status = "ok"
    except (SQLAlchemyError, RedisError):
        ready_status = False
    if not ready_status:
        response.status_code = 503
    return {
        "status": "ready" if ready_status else "not_ready",
        "database": "ok" if ready_status else "unavailable",
        "schema": "head" if ready_status else "incomplete",
        "redis": redis_status,
        "ai_provider": "configured" if settings.ai_actually_enabled else "mock",
    }


@app.get("/metrics", tags=["observability"], include_in_schema=False)
def metrics():
    """Prometheus 抓取端点（低基数标签，不含任何敏感数据）。"""
    from app.core.metrics import render_metrics

    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)
