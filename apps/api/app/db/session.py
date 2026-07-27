"""数据库引擎与会话工厂。"""
from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

from app.core.config import settings

connect_args: dict[str, Any] = {}
url = settings.effective_database_url
if url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(url, connect_args=connect_args, future=True, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
