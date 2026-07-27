"""仪表盘接口。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, supervisor_or_admin
from app.db.session import get_db
from app.models.base import PriorityEnum, WorkOrderStatusEnum
from app.models.fault import FaultReport
from app.models.workorder import WorkOrder
from app.schemas.dashboard import SupervisorDashboard, TechnicianDashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/supervisor", response_model=SupervisorDashboard)
def supervisor_dashboard(db: Session = Depends(get_db), _=Depends(supervisor_or_admin)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    pending_dispatch = db.query(WorkOrder).filter(WorkOrder.status == WorkOrderStatusEnum.pending_dispatch).count()
    in_progress = db.query(WorkOrder).filter(WorkOrder.status.in_([WorkOrderStatusEnum.assigned, WorkOrderStatusEnum.accepted, WorkOrderStatusEnum.in_progress])).count()
    pending_acceptance = db.query(WorkOrder).filter(WorkOrder.status == WorkOrderStatusEnum.pending_acceptance).count()
    overdue = db.query(WorkOrder).filter(WorkOrder.planned_end_at < func.now()).filter(WorkOrder.status.notin_([WorkOrderStatusEnum.completed, WorkOrderStatusEnum.cancelled])).count()
    today_new_faults = db.query(FaultReport).filter(FaultReport.created_at >= today_start).count()
    today_completed = db.query(WorkOrder).filter(WorkOrder.status == WorkOrderStatusEnum.completed, WorkOrder.actual_end_at >= today_start).count()
    # 平均修复时长
    completed = db.query(WorkOrder).filter(WorkOrder.status == WorkOrderStatusEnum.completed, WorkOrder.actual_start_at.isnot(None), WorkOrder.actual_end_at.isnot(None)).all()
    avg_hours = None
    if completed:
        total_h = sum((w.actual_end_at - w.actual_start_at).total_seconds() / 3600 for w in completed)
        avg_hours = round(total_h / len(completed), 1)

    # 优先级分布
    prio_rows = db.query(WorkOrder.priority, func.count(WorkOrder.id)).filter(WorkOrder.status.notin_([WorkOrderStatusEnum.completed, WorkOrderStatusEnum.cancelled])).group_by(WorkOrder.priority).all()
    by_priority = [{"priority": p.value if p else "P3", "count": c} for p, c in prio_rows]
    # 设备类型分布
    from app.models.equipment import Equipment, EquipmentType

    type_rows = (
        db.query(EquipmentType.name, func.count(WorkOrder.id))
        .join(Equipment, Equipment.id == WorkOrder.equipment_id)
        .join(EquipmentType, EquipmentType.id == Equipment.equipment_type_id)
        .filter(WorkOrder.status.notin_([WorkOrderStatusEnum.completed, WorkOrderStatusEnum.cancelled]))
        .group_by(EquipmentType.name)
        .all()
    )
    by_eq_type = [{"equipment_type": n or "未分类", "count": c} for n, c in type_rows]
    recent = db.query(WorkOrder).order_by(WorkOrder.created_at.desc()).limit(8).all()
    recent_list = [{"id": w.id, "code": w.code, "title": w.title, "status": w.status.value, "priority": w.priority.value, "assignee": w.assignee.full_name if w.assignee else None, "created_at": w.created_at.isoformat() if w.created_at else None} for w in recent]
    return SupervisorDashboard(
        pending_dispatch=pending_dispatch,
        in_progress=in_progress,
        pending_acceptance=pending_acceptance,
        overdue=overdue,
        today_new_faults=today_new_faults,
        today_completed=today_completed,
        avg_repair_hours=avg_hours,
        total_downtime_hours=0.0,
        by_priority=by_priority,
        by_equipment_type=by_eq_type,
        recent_work_orders=recent_list,
    )


@router.get("/technician", response_model=TechnicianDashboard)
def technician_dashboard(db: Session = Depends(get_db), user=Depends(get_current_user)):
    mine = db.query(WorkOrder).filter(WorkOrder.assignee_id == user.id)
    assigned_to_me = mine.filter(WorkOrder.status.in_([WorkOrderStatusEnum.assigned, WorkOrderStatusEnum.accepted, WorkOrderStatusEnum.in_progress])).count()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_todo = mine.filter(WorkOrder.status.in_([WorkOrderStatusEnum.assigned, WorkOrderStatusEnum.accepted])).count()
    high_priority = mine.filter(WorkOrder.priority.in_([PriorityEnum.P1, PriorityEnum.P2])).filter(WorkOrder.status.notin_([WorkOrderStatusEnum.completed, WorkOrderStatusEnum.cancelled])).count()
    overdue = mine.filter(WorkOrder.planned_end_at < func.now()).filter(WorkOrder.status.notin_([WorkOrderStatusEnum.completed, WorkOrderStatusEnum.cancelled])).count()
    my_wos = mine.filter(WorkOrder.status.notin_([WorkOrderStatusEnum.completed, WorkOrderStatusEnum.cancelled])).order_by(WorkOrder.priority, WorkOrder.created_at.desc()).limit(10).all()
    my_list = [{"id": w.id, "code": w.code, "title": w.title, "status": w.status.value, "priority": w.priority.value, "equipment_name": w.equipment.name if w.equipment else None} for w in my_wos]
    from app.models.maintenance import MaintenanceLog

    recent_logs = db.query(MaintenanceLog).filter(MaintenanceLog.operator_id == user.id).order_by(MaintenanceLog.created_at.desc()).limit(5).all()
    log_list = [{"id": l.id, "work_order_id": l.work_order_id, "content": l.content, "log_type": l.log_type.value, "created_at": l.created_at.isoformat() if l.created_at else None} for l in recent_logs]
    return TechnicianDashboard(
        assigned_to_me=assigned_to_me,
        today_todo=today_todo,
        high_priority=high_priority,
        overdue=overdue,
        my_work_orders=my_list,
        recent_logs=log_list,
    )
