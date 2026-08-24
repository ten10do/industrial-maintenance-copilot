"""高风险设备命令的超时识别与审计。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.intelligence import OperationApproval, OperationExecutionAudit


def mark_timed_out_executions(db: Session, *, now: datetime | None = None) -> int:
    """把超过命令执行期限的记录原子转为待人工核验。"""
    checked_at = now or datetime.now(UTC)
    cutoff = checked_at - timedelta(seconds=settings.EQUIPMENT_COMMAND_TIMEOUT_SECONDS)
    changed = 0
    executing = (
        db.query(OperationApproval)
        .filter(OperationApproval.status == "executing")
        .all()
    )
    for approval in executing:
        started_at = approval.execution_started_at or approval.reviewed_at
        if not started_at or _as_utc(started_at) > cutoff:
            continue
        transition = db.execute(
            update(OperationApproval)
            .where(
                OperationApproval.id == approval.id,
                OperationApproval.status == "executing",
            )
            .values(status="execution_unknown")
            .returning(OperationApproval.id)
        )
        if transition.scalar_one_or_none() is None:
            continue
        db.add(
            OperationExecutionAudit(
                approval_id=approval.id,
                event_type="execution_timed_out",
                execution_key=approval.execution_key or "legacy-missing-key",
                execution_attempt=approval.execution_attempt,
                occurred_at=checked_at,
                note="设备命令超过执行期限，转入人工核验",
                details={"timeout_seconds": settings.EQUIPMENT_COMMAND_TIMEOUT_SECONDS},
            )
        )
        changed += 1
    if changed:
        db.commit()
        db.expire_all()
    return changed


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
