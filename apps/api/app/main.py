"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.migrations import schema_is_ready, upgrade_schema
from app.db.session import SessionLocal, engine

logger = logging.getLogger("app")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 兼容迁移同时负责新数据库建表。
    upgrade_schema(engine)
    if settings.SEED_ON_STARTUP:
        from app.seed import run_seed_if_empty

        run_seed_if_empty()
    yield


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
        ready_status = schema_is_ready(engine)
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
