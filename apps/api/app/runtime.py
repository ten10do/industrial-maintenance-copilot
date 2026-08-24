"""Worker 与 Scheduler 的轻量运行时和可验证心跳。"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import UTC, datetime
from typing import Literal

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.alembic import database_is_at_head
from app.db.session import SessionLocal, engine
from app.services.approval_service import mark_timed_out_executions

Role = Literal["worker", "scheduler"]
logger = logging.getLogger("app.runtime")
logging.basicConfig(level=logging.INFO)


def _redis_client() -> Redis:
    if not settings.REDIS_URL:
        raise RuntimeError("REDIS_URL is required for worker and scheduler")
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _heartbeat_key(role: Role) -> str:
    return f"intelligent-maintenance:{role}:heartbeat"


def _dependencies_ready(redis_client: Redis) -> None:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    if not database_is_at_head(engine):
        raise RuntimeError("database schema is not at Alembic head")
    redis_client.ping()


def run(role: Role) -> None:
    redis_client = _redis_client()
    interval = 5 if role == "worker" else 15
    logger.info("%s runtime started", role)
    while True:
        try:
            _dependencies_ready(redis_client)
            redis_client.set(
                _heartbeat_key(role),
                datetime.now(UTC).isoformat(),
                ex=max(interval * 4, 60),
            )
            if role == "scheduler":
                with SessionLocal() as db:
                    marked = mark_timed_out_executions(db)
                if marked:
                    logger.warning(
                        "%s high-risk command(s) require reconciliation", marked
                    )
        except (RedisError, RuntimeError, SQLAlchemyError) as exc:
            logger.error("%s dependency check failed: %s", role, exc)
        time.sleep(interval)


def check(role: Role) -> bool:
    try:
        value = _redis_client().get(_heartbeat_key(role))
        if not isinstance(value, str):
            return False
        heartbeat = datetime.fromisoformat(value)
        return (datetime.now(UTC) - heartbeat).total_seconds() < 60
    except (RedisError, RuntimeError, ValueError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["worker", "scheduler"])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    role: Role = args.role
    if args.check:
        return 0 if check(role) else 1
    run(role)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
