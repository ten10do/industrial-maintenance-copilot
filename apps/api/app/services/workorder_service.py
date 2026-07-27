"""工单状态机：定义合法流转与校验。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.base import WorkOrderStatusEnum as S
from app.models.workorder import WorkOrder, WorkOrderStatusHistory

# 合法状态流转表
TRANSITIONS: dict[S, set[S]] = {
    S.pending_dispatch: {S.assigned, S.cancelled},
    S.assigned: {S.accepted, S.cancelled, S.pending_dispatch},
    S.accepted: {S.in_progress, S.cancelled},
    S.in_progress: {S.pending_acceptance, S.paused, S.cancelled, S.returned},
    S.paused: {S.in_progress, S.cancelled},
    S.pending_acceptance: {S.completed, S.returned, S.in_progress},
    S.returned: {S.in_progress, S.cancelled},
    S.completed: set(),
    S.cancelled: set(),
}

# 各角色可触发的动作 -> 目标状态
ACTION_TO_STATUS = {
    "assign": S.assigned,
    "accept": S.accepted,
    "start": S.in_progress,
    "pause": S.paused,
    "resume": S.in_progress,
    "submit": S.pending_acceptance,
    "approve": S.completed,
    "reject": S.returned,
    "cancel": S.cancelled,
}


def assert_transition(current: S, target: S) -> None:
    if target not in TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法状态流转：{current.value} 不能直接变为 {target.value}",
        )


def change_status(
    db: Session,
    wo: WorkOrder,
    target: S,
    user_id: int | None,
    remark: str | None = None,
) -> None:
    assert_transition(WorkOrderStatusEnum(wo.status), target)  # type: ignore[arg-type]
    prev = wo.status
    wo.status = target
    wo.updated_by = str(user_id) if user_id else None
    now = datetime.now(timezone.utc)
    if target == S.in_progress and not wo.actual_start_at:
        wo.actual_start_at = now
    if target == S.completed:
        wo.actual_end_at = now
    if target == S.pending_acceptance:
        wo.submitted_at = now
    record = WorkOrderStatusHistory(
        work_order_id=wo.id,
        from_status=prev.value if prev else None,
        to_status=target.value,
        changed_by=user_id,
        changed_at=now,
        remark=remark,
    )
    db.add(record)
    db.flush()


from app.models.base import WorkOrderStatusEnum  # noqa: E402
