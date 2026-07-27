"""工单管理接口：状态流转、检查清单、维修记录、工时、备件、完工验收。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, supervisor_or_admin, technician_or_above
from app.core.exceptions import bad_request, conflict, not_found, paginate
from app.db.session import get_db
from app.models.base import (
    MaintenanceLogTypeEnum,
    PriorityEnum,
    WorkOrderStatusEnum,
    WorkOrderTypeEnum,
)
from app.models.equipment import Equipment, FaultCode, SparePart
from app.models.maintenance import Attachment, LaborEntry, MaintenanceLog, WorkOrderSparePart
from app.models.user import User
from app.models.workorder import (
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderChecklistItem,
    WorkOrderStatusHistory,
)
from app.schemas.common import OkResponse, PageOut
from app.schemas.workorder import (
    AssignRequest,
    ChecklistItemOut,
    ChecklistItemUpdate,
    LaborEntryCreate,
    LaborEntryOut,
    MaintenanceLogCreate,
    MaintenanceLogOut,
    RejectRequest,
    SparePartUsageCreate,
    SparePartUsageOut,
    SubmitRequest,
    WorkOrderCreate,
    WorkOrderDetail,
    WorkOrderOut,
    WorkOrderUpdate,
)
from app.services.workorder_service import change_status
from app.storage.backend import get_storage

router = APIRouter(prefix="/work-orders", tags=["work-orders"])

DEFAULT_CHECKLIST = [
    "确认设备已停机",
    "执行断电操作",
    "执行上锁挂牌（LOTO）",
    "确认残余能量已释放",
    "读取并记录故障代码",
    "检查相关部件状态",
    "执行维修或更换",
    "恢复供电",
    "空载测试",
    "负载测试",
    "确认设备恢复正常",
]

_HIGH_RISK_KEYWORDS = ["高压", "电气", "液压", "气压", "高温", "旋转"]


def _gen_code(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    count = db.query(WorkOrder).filter(WorkOrder.code.like(f"WO-{year}-%")).count()
    return f"WO-{year}-{count + 1:04d}"


def _safety_text(wo: WorkOrder) -> str:
    base = wo.safety_risk or ""
    if wo.equipment_id:
        eq = db_get_eq_risk(wo.equipment_id)
        if eq:
            base = (base + "；" if base else "") + eq
    return base or None


def db_get_eq_risk(eq_id: int) -> str | None:
    # 独立函数避免循环依赖，运行时由调用方持有 db
    return None


def _to_out(wo: WorkOrder) -> WorkOrderOut:
    eq_name = eq_code = None
    if wo.equipment_id:
        eq = wo.equipment
        if eq:
            eq_name, eq_code = eq.name, eq.code
    fault_code = None
    if wo.fault_code_id:
        fc = wo.fault_code if hasattr(wo, "fault_code") else None
        # 关系未建立时通过 id 查不到，这里简化处理
    creator_name = wo.creator.full_name if wo.creator else None
    assignee_name = wo.assignee.full_name if wo.assignee else None
    return WorkOrderOut(
        id=wo.id,
        code=wo.code,
        title=wo.title,
        equipment_id=wo.equipment_id,
        equipment_name=eq_name,
        equipment_code=eq_code,
        fault_report_id=wo.fault_report_id,
        fault_description=wo.fault_description,
        fault_code_id=wo.fault_code_id,
        fault_code=fault_code,
        order_type=wo.order_type,
        priority=wo.priority,
        status=wo.status,
        created_by_id=wo.created_by_id,
        creator_name=creator_name,
        assignee_id=wo.assignee_id,
        assignee_name=assignee_name,
        planned_start_at=wo.planned_start_at,
        planned_end_at=wo.planned_end_at,
        actual_start_at=wo.actual_start_at,
        actual_end_at=wo.actual_end_at,
        safety_risk=wo.safety_risk,
        ai_diagnosis_summary=wo.ai_diagnosis_summary,
        maintenance_steps=wo.maintenance_steps,
        acceptance_criteria=wo.acceptance_criteria,
        root_cause=wo.root_cause,
        action_taken=wo.action_taken,
        replaced_parts=wo.replaced_parts,
        test_result=wo.test_result,
        equipment_status_after=wo.equipment_status_after,
        follow_up_advice=wo.follow_up_advice,
        needs_observation=wo.needs_observation,
        completion_photos=wo.completion_photos,
        rejection_reason=wo.rejection_reason,
        submitted_at=wo.submitted_at,
        created_at=wo.created_at,
        updated_at=wo.updated_at,
    )


def _to_detail(db: Session, wo: WorkOrder) -> WorkOrderDetail:
    out = _to_out(wo)
    fc = None
    if wo.fault_code_id:
        f = db.get(FaultCode, wo.fault_code_id)
        fc = f.code if f else None
    out.fault_code = fc
    out.checklist_items = [ChecklistItemOut.model_validate(c) for c in wo.checklist_items]
    out.logs = [MaintenanceLogOut.model_validate(l) for l in wo.logs]
    out.labor_entries = [LaborEntryOut.model_validate(e) for e in wo.labor_entries]
    out.spare_parts = [SparePartUsageOut.model_validate(s) for s in wo.spare_parts]
    out.status_history = [
        {
            "id": h.id,
            "from_status": h.from_status,
            "to_status": h.to_status,
            "changed_by": h.changed_by,
            "changed_at": h.changed_at.isoformat() if h.changed_at else None,
            "remark": h.remark,
        }
        for h in wo.status_history
    ]
    return out


@router.get("", response_model=PageOut[WorkOrderOut])
def list_work_orders(
    status_filter: str | None = None,
    priority: str | None = None,
    assignee_id: int | None = None,
    equipment_id: int | None = None,
    keyword: str | None = None,
    mine: bool = False,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    q = db.query(WorkOrder)
    if status_filter:
        q = q.filter(WorkOrder.status == status_filter)
    if priority:
        q = q.filter(WorkOrder.priority == priority)
    if assignee_id:
        q = q.filter(WorkOrder.assignee_id == assignee_id)
    if equipment_id:
        q = q.filter(WorkOrder.equipment_id == equipment_id)
    if mine:
        q = q.filter(WorkOrder.assignee_id == user.id)
    if keyword:
        q = q.filter(WorkOrder.title.contains(keyword) | WorkOrder.code.contains(keyword))
    q = q.order_by(WorkOrder.created_at.desc())
    items, total = paginate(q, page, page_size)
    return PageOut(items=[_to_out(w) for w in items], total=total, page=page, page_size=page_size)


@router.post("", response_model=WorkOrderDetail)
def create_work_order(payload: WorkOrderCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    wo = WorkOrder(
        code=_gen_code(db),
        **payload.model_dump(),
        status=WorkOrderStatusEnum.pending_dispatch,
        created_by_id=user.id,
        created_by=str(user.id),
    )
    # 安全风险识别
    risk_text = (payload.fault_description or "") + (payload.safety_risk or "")
    if any(k in risk_text for k in _HIGH_RISK_KEYWORDS):
        wo.safety_risk = (wo.safety_risk or "") + "（注意：涉及高危风险，维修前必须确认安全措施）"
    db.add(wo)
    db.flush()
    # 生成默认检查清单
    for i, content in enumerate(DEFAULT_CHECKLIST):
        db.add(WorkOrderChecklistItem(work_order_id=wo.id, content=content, order=i, is_required=True))
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


@router.get("/{wo_id}", response_model=WorkOrderDetail)
def get_work_order(wo_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    return _to_detail(db, wo)


@router.put("/{wo_id}", response_model=WorkOrderDetail)
def update_work_order(wo_id: int, payload: WorkOrderUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    # 已完成工单默认不可编辑业务字段
    if wo.status == WorkOrderStatusEnum.completed:
        raise bad_request("已完成的工单不可编辑")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(wo, k, v)
    wo.updated_by = str(user.id)
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


@router.post("/{wo_id}/assign", response_model=WorkOrderDetail)
def assign(wo_id: int, payload: AssignRequest, db: Session = Depends(get_db), user=Depends(supervisor_or_admin)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    tech = db.get(User, payload.assignee_id)
    if not tech or tech.role.value != "technician":
        raise bad_request("只能分派给维修工程师")
    change_status(db, wo, WorkOrderStatusEnum.assigned, user.id, remark=f"分派给 {tech.full_name}")
    wo.assignee_id = payload.assignee_id
    if payload.priority:
        wo.priority = payload.priority
    if payload.planned_end_at:
        wo.planned_end_at = payload.planned_end_at
    # 记录分派历史
    db.add(WorkOrderAssignment(work_order_id=wo.id, assignee_id=payload.assignee_id, assigned_by=user.id, assigned_at=datetime.now(timezone.utc), is_current=True))
    # 旧分派置为非当前
    db.query(WorkOrderAssignment).filter(WorkOrderAssignment.work_order_id == wo.id, WorkOrderAssignment.id != None).update({WorkOrderAssignment.is_current: False})  # noqa: E711
    db.flush()
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


@router.post("/{wo_id}/accept", response_model=WorkOrderDetail)
def accept(wo_id: int, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    if wo.assignee_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能接受分派给自己的工单")
    change_status(db, wo, WorkOrderStatusEnum.accepted, user.id)
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


@router.post("/{wo_id}/start", response_model=WorkOrderDetail)
def start(wo_id: int, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    # 高风险工单必须确认安全措施（通过请求头 X-Safety-Confirmed）
    change_status(db, wo, WorkOrderStatusEnum.in_progress, user.id)
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


@router.post("/{wo_id}/pause", response_model=WorkOrderDetail)
def pause(wo_id: int, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    change_status(db, wo, WorkOrderStatusEnum.paused, user.id)
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


@router.post("/{wo_id}/resume", response_model=WorkOrderDetail)
def resume(wo_id: int, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    change_status(db, wo, WorkOrderStatusEnum.in_progress, user.id)
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


@router.post("/{wo_id}/submit", response_model=WorkOrderDetail)
def submit(wo_id: int, payload: SubmitRequest, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    # 完工校验
    required_items = [c for c in wo.checklist_items if c.is_required]
    unfinished = [c for c in required_items if not c.is_completed]
    if unfinished:
        raise bad_request(f"必填维修步骤未完成：{', '.join(c.content for c in unfinished)}")
    if not payload.root_cause:
        raise bad_request("必须填写根本原因")
    if not payload.action_taken:
        raise bad_request("必须填写处理措施")
    if not payload.test_result:
        raise bad_request("必须填写测试结果")
    if not wo.logs:
        raise bad_request("至少需要一条维修过程记录")
    wo.root_cause = payload.root_cause
    wo.action_taken = payload.action_taken
    wo.replaced_parts = payload.replaced_parts
    wo.test_result = payload.test_result
    wo.equipment_status_after = payload.equipment_status_after
    wo.follow_up_advice = payload.follow_up_advice
    wo.needs_observation = payload.needs_observation
    wo.completion_photos = payload.completion_photos
    change_status(db, wo, WorkOrderStatusEnum.pending_acceptance, user.id)
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


@router.post("/{wo_id}/approve", response_model=WorkOrderDetail)
def approve(wo_id: int, db: Session = Depends(get_db), user=Depends(supervisor_or_admin)):
    from app.models.equipment import Equipment
    from app.models.base import EquipmentStatusEnum
    from app.models.knowledge import AcceptanceRecord

    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    change_status(db, wo, WorkOrderStatusEnum.completed, user.id, remark="验收通过")
    # 设备状态恢复
    if wo.equipment_id:
        eq = db.get(Equipment, wo.equipment_id)
        if eq:
            eq.status = EquipmentStatusEnum.running
            eq.last_maintenance_at = datetime.now(timezone.utc).date()
    db.add(AcceptanceRecord(work_order_id=wo.id, result="approved", reviewer_id=user.id, remark="验收通过"))
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


@router.post("/{wo_id}/reject", response_model=WorkOrderDetail)
def reject(wo_id: int, payload: RejectRequest, db: Session = Depends(get_db), user=Depends(supervisor_or_admin)):
    from app.models.knowledge import AcceptanceRecord

    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    change_status(db, wo, WorkOrderStatusEnum.returned, user.id, remark=f"验收退回：{payload.remark}")
    wo.rejection_reason = payload.remark
    db.add(AcceptanceRecord(work_order_id=wo.id, result="rejected", reviewer_id=user.id, remark=payload.remark))
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


@router.post("/{wo_id}/cancel", response_model=WorkOrderDetail)
def cancel(wo_id: int, db: Session = Depends(get_db), user=Depends(supervisor_or_admin)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    change_status(db, wo, WorkOrderStatusEnum.cancelled, user.id)
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


# ---------- 检查清单 ----------


@router.put("/{wo_id}/checklist/{item_id}", response_model=WorkOrderDetail)
def update_checklist_item(wo_id: int, item_id: int, payload: ChecklistItemUpdate, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    item = db.get(WorkOrderChecklistItem, item_id)
    if not item or item.work_order_id != wo_id:
        raise not_found("检查项不存在")
    if payload.is_completed is not None:
        item.is_completed = payload.is_completed
        item.completed_at = datetime.now(timezone.utc) if payload.is_completed else None
        item.completed_by = user.id if payload.is_completed else None
    if payload.remark is not None:
        item.remark = payload.remark
    db.commit()
    wo = db.get(WorkOrder, wo_id)
    return _to_detail(db, wo)


# ---------- 维修记录 ----------


@router.post("/{wo_id}/logs", response_model=MaintenanceLogOut)
def add_log(wo_id: int, payload: MaintenanceLogCreate, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    if wo.status == WorkOrderStatusEnum.completed:
        raise bad_request("已完成的工单不可继续添加维修记录")
    log = MaintenanceLog(
        work_order_id=wo_id,
        log_type=payload.log_type,
        content=payload.content,
        raw_content=payload.raw_content or payload.content,
        photos=payload.photos,
        operator_id=user.id,
        operator_name=user.full_name,
        logged_at=payload.logged_at or datetime.now(timezone.utc),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return MaintenanceLogOut.model_validate(log)


# ---------- 工时 ----------


@router.post("/{wo_id}/labor", response_model=LaborEntryOut)
def add_labor(wo_id: int, payload: LaborEntryCreate, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    entry = LaborEntry(
        work_order_id=wo_id,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        hours=payload.hours,
        is_downtime=payload.is_downtime,
        operator_id=user.id,
        operator_name=payload.operator_name or user.full_name,
        remark=payload.remark,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return LaborEntryOut.model_validate(entry)


# ---------- 备件 ----------


@router.post("/{wo_id}/spare-parts", response_model=SparePartUsageOut)
def add_spare_part(wo_id: int, payload: SparePartUsageCreate, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    code = name = None
    if payload.spare_part_id:
        sp = db.get(SparePart, payload.spare_part_id)
        if sp:
            code, name = sp.code, sp.name
    usage = WorkOrderSparePart(
        work_order_id=wo_id,
        spare_part_id=payload.spare_part_id,
        spare_part_code=payload.spare_part_code or code,
        spare_part_name=payload.spare_part_name or name,
        quantity=payload.quantity,
        unit=payload.unit,
        remark=payload.remark,
    )
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return SparePartUsageOut.model_validate(usage)


# ---------- 附件 ----------


@router.post("/{wo_id}/attachments")
def upload_attachment(wo_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    storage = get_storage()
    try:
        rel_path, url, size, ftype = storage.save(file, subdir=f"workorders/{wo_id}")
    except ValueError as e:
        raise bad_request(str(e))
    att = Attachment(
        work_order_id=wo_id,
        file_name=file.filename,
        file_path=rel_path,
        file_url=url,
        file_type=ftype,
        file_size=size,
        uploaded_by=user.id,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return {"id": att.id, "url": att.file_url, "file_name": att.file_name}
