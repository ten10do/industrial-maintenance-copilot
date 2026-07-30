"""FastAPI 应用入口。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import Base, engine

logger = logging.getLogger("app")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表
    Base.metadata.create_all(bind=engine)
    if settings.SEED_ON_STARTUP:
        from app.seed import run_seed_if_empty

        run_seed_if_empty()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="工业设备运维工单 Copilot MVP 后端 API",
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
        from app.db.session import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:
        db_status = "unavailable"
    return {"status": "ok", "database": db_status, "ai_enabled": settings.ai_actually_enabled}
