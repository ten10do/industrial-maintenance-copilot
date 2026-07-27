"""模型基类、混入与全局枚举。"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_utcnow, onupdate=_utcnow
    )


class AuditMixin(TimestampMixin):
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


# ---------------- 枚举 ----------------


class RoleEnum(str, enum.Enum):
    admin = "admin"
    supervisor = "supervisor"
    technician = "technician"


class EquipmentStatusEnum(str, enum.Enum):
    running = "running"
    fault = "fault"
    under_repair = "under_repair"
    stopped = "stopped"
    scrapped = "scrapped"


class RiskLevelEnum(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class UrgencyEnum(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class FaultReportStatusEnum(str, enum.Enum):
    pending = "pending"
    converted = "converted"
    closed = "closed"


class WorkOrderTypeEnum(str, enum.Enum):
    fault_repair = "fault_repair"
    preventive = "preventive"
    inspection = "inspection"
    temporary = "temporary"


class PriorityEnum(str, enum.Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class WorkOrderStatusEnum(str, enum.Enum):
    pending_dispatch = "pending_dispatch"
    assigned = "assigned"
    accepted = "accepted"
    in_progress = "in_progress"
    pending_acceptance = "pending_acceptance"
    completed = "completed"
    cancelled = "cancelled"
    returned = "returned"
    paused = "paused"


class MaintenanceLogTypeEnum(str, enum.Enum):
    inspect = "inspect"
    diagnose = "diagnose"
    repair = "repair"
    replace = "replace"
    test = "test"
    note = "note"


class KnowledgeCategoryEnum(str, enum.Enum):
    manual = "manual"
    sop = "sop"
    safety = "safety"
    case = "case"
    fault_code = "fault_code"
    experience = "experience"


class AIInteractionTypeEnum(str, enum.Enum):
    parse_fault = "parse_fault"
    diagnose = "diagnose"
    rewrite_log = "rewrite_log"
    generate_report = "generate_report"
    ask = "ask"
    history_summary = "history_summary"


class AIStatusEnum(str, enum.Enum):
    success = "success"
    failed = "failed"
    mock = "mock"


def gen_uuid() -> str:
    return uuid.uuid4().hex
