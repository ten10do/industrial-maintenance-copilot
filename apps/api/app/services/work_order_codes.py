"""并发安全的工单编号生成。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


def generate_work_order_code(now: datetime | None = None) -> str:
    """生成不依赖数据库计数的全局唯一工单编号。"""

    year = (now or datetime.now(UTC)).year
    return f"WO-{year}-{uuid4().hex.upper()}"
