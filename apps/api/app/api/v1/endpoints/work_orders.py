"""工单管理接口：状态流转、检查清单、维修记录、工时、备件、完工验收、报告。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.ai.copilot import generate_report as ai_generate_report
from app.core.deps import get_current_user, supervisor_or_admin, technician_or_above
from app.core.exceptions import bad_request, conflict, not_found, paginate
from app.db.session import get_db
from app.models.base import (
    EquipmentStatusEnum,
    FaultReportStatusEnum,
    KnowledgeCategoryEnum,
    MaintenanceLogTypeEnum,
    PriorityEnum,
    WorkOrderStatusEnum,
    WorkOrderTypeEnum,
)
from app.models.equipment import Equipment, FaultCode, SparePart
from app.models.knowledge import AcceptanceRecord, KnowledgeArticle
from app.models.maintenance import (
    Attachment,
    LaborEntry,
    MaintenanceLog,
    WorkOrderReport,
    WorkOrderSparePart,
)
from app.models.user import User
from app.models.workorder import (
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderChecklistItem,
    WorkOrderStatusHistory,
)
from app.schemas.common import OkResponse, PageOut
from app.schemas.workorder import (
    AcceptRequest,
    AssignRequest,
    ChecklistItemOut,
    ChecklistItemUpdate,
    CompletionValidationError,
    LaborEntryCreate,
    LaborEntryOut,
    LaborEntryUpdate,
    MaintenanceLogCreate,
    MaintenanceLogOut,
    MaintenanceLogUpdate,
    RejectRequest,
    ReportGenerateResponse,
    ReportOut,
    ReportSectionOut,
    SparePartUsageCreate,
    SparePartUsageOut,
    SparePartUsageUpdate,
    SubmitRequest,
    WorkOrderCreate,
    WorkOrderDetail,
    WorkOrderOut,
    WorkOrderUpdate,
)
from app.services.workorder_service import change_status
from app.storage.backend import get_storage

router = APIRouter(prefix="/work-orders", tags=["work-orders"])

# 默认检查清单 — 按类别分组
DEFAULT_CHECKLIST: list[dict] = [
    {"category": "safety", "content": "设备已停机", "is_required": True},
    {"category": "safety", "content": "相关能源已切断", "is_required": True},
    {"category": "safety", "content": "已执行上锁挂牌（LOTO）", "is_required": True},
    {"category": "safety", "content": "残余能量已释放", "is_required": True},
    {"category": "safety", "content": "安全联锁状态已确认", "is_required": True},
    {"category": "safety", "content": "现场警示已设置", "is_required": True},
    {"category": "safety", "content": "个人防护用品已佩戴", "is_required": True},
    {"category": "diagnosis", "content": "读取并记录故障代码", "is_required": True},
    {"category": "diagnosis", "content": "检查相关部件状态", "is_required": True},
    {"category": "repair", "content": "执行维修或更换", "is_required": True},
    {"category": "repair", "content": "恢复供电", "is_required": True},
    {"category": "testing", "content": "空载测试", "is_required": False},
    {"category": "testing", "content": "负载测试", "is_required": True},
    {"category": "testing", "content": "确认设备恢复正常", "is_required": True},
]

_HIGH_RISK_KEYWORDS = [
    "高压", "电气", "液压", "气压", "高温", "旋转",
    "带电", "短接", "短路", "绕过", "联锁",
]

# 危险操作禁止提示
_PROHIBITED_KEYWORDS = ["带电", "短接", "短路", "绕过"]

_EXECUTION_EDITABLE_STATUSES = {
    WorkOrderStatusEnum.accepted,
    WorkOrderStatusEnum.in_progress,
    WorkOrderStatusEnum.paused,
    WorkOrderStatusEnum.returned,
}


def _require_assignee(wo: WorkOrder, user: User) -> None:
    if wo.assignee_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有被分派工程师可以执行此操作",
        )


def _require_execution_access(wo: WorkOrder, user: User) -> None:
    _require_assignee(wo, user)
    if wo.status not in _EXECUTION_EDITABLE_STATUSES:
        raise bad_request("当前工单状态不可修改维修执行记录")


def _gen_code(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    count = db.query(WorkOrder).filter(WorkOrder.code.like(f"WO-{year}-%")).count()
    return f"WO-{year}-{count + 1:04d}"


def _safety_text(wo: WorkOrder) -> str | None:
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
    base = _to_out(wo).model_dump()
    fc = None
    if wo.fault_code_id:
        f = db.get(FaultCode, wo.fault_code_id)
        fc = f.code if f else None
    base["fault_code"] = fc
    base["checklist_items"] = [ChecklistItemOut.model_validate(c) for c in wo.checklist_items]
    base["logs"] = [MaintenanceLogOut.model_validate(l) for l in wo.logs]
    base["labor_entries"] = [LaborEntryOut.model_validate(e) for e in wo.labor_entries]
    base["spare_parts"] = [SparePartUsageOut.model_validate(s) for s in wo.spare_parts]
    base["status_history"] = [
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
    return WorkOrderDetail(**base)


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
def create_work_order(payload: WorkOrderCreate, db: Session = Depends(get_db), user=Depends(supervisor_or_admin)):
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
    db.add(
        WorkOrderStatusHistory(
            work_order_id=wo.id,
            from_status=None,
            to_status=WorkOrderStatusEnum.pending_dispatch.value,
            changed_by=user.id,
            changed_at=datetime.now(timezone.utc),
            remark="手工创建工单",
        )
    )
    # 生成默认检查清单（按类别）
    for i, item in enumerate(DEFAULT_CHECKLIST):
        db.add(WorkOrderChecklistItem(
            work_order_id=wo.id,
            category=item["category"],
            content=item["content"],
            order=i,
            is_required=item["is_required"],
        ))
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
def update_work_order(wo_id: int, payload: WorkOrderUpdate, db: Session = Depends(get_db), user=Depends(supervisor_or_admin)):
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
    if wo.status not in {
        WorkOrderStatusEnum.pending_dispatch,
        WorkOrderStatusEnum.assigned,
    }:
        raise bad_request("只能分派待分派或已分派状态的工单")
    if wo.status == WorkOrderStatusEnum.pending_dispatch:
        change_status(
            db,
            wo,
            WorkOrderStatusEnum.assigned,
            user.id,
            remark=f"分派给 {tech.full_name}",
        )
    else:
        wo.updated_by = str(user.id)
    wo.assignee_id = payload.assignee_id
    if payload.priority:
        wo.priority = payload.priority
    if payload.planned_end_at:
        wo.planned_end_at = payload.planned_end_at
    # 旧分派置为非当前
    db.query(WorkOrderAssignment).filter(
        WorkOrderAssignment.work_order_id == wo.id,
        WorkOrderAssignment.is_current.is_(True),
    ).update({WorkOrderAssignment.is_current: False})
    # 记录分派历史
    db.add(
        WorkOrderAssignment(
            work_order_id=wo.id,
            assignee_id=payload.assignee_id,
            assigned_by=user.id,
            assigned_at=datetime.now(timezone.utc),
            is_current=True,
        )
    )
    db.flush()
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


@router.post("/{wo_id}/accept", response_model=WorkOrderDetail)
def accept(wo_id: int, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    _require_assignee(wo, user)
    change_status(db, wo, WorkOrderStatusEnum.accepted, user.id)
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


@router.post("/{wo_id}/start", response_model=WorkOrderDetail)
def start(wo_id: int, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    _require_assignee(wo, user)
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
    _require_assignee(wo, user)
    change_status(db, wo, WorkOrderStatusEnum.paused, user.id)
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


@router.post("/{wo_id}/resume", response_model=WorkOrderDetail)
def resume(wo_id: int, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    _require_assignee(wo, user)
    change_status(db, wo, WorkOrderStatusEnum.in_progress, user.id)
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


def _validate_completion(wo: WorkOrder, payload: SubmitRequest, db: Session) -> list[str]:
    """验证完工条件，返回缺失项列表。"""
    missing: list[str] = []

    if not payload.root_cause or not payload.root_cause.strip():
        missing.append("root_cause")
    if not payload.action_taken or not payload.action_taken.strip():
        missing.append("action_taken")
    if not payload.test_result or not payload.test_result.strip():
        missing.append("test_result")

    # 必做检查项
    required_items = [c for c in wo.checklist_items if c.is_required]
    unfinished = [c.content for c in required_items if not c.is_completed]
    if unfinished:
        missing.append("required_checklist_items")

    # 至少一条维修过程记录
    if not wo.logs:
        missing.append("maintenance_log")

    # 至少一条工时记录
    if not wo.labor_entries:
        missing.append("labor_entry")

    # 至少一项 testing 类别检查项已完成
    test_items = [c for c in wo.checklist_items if c.category == "testing"]
    if not test_items or not any(c.is_completed for c in test_items):
        missing.append("test_step")

    # 高风险工单至少一张完工/测试照片
    has_risk = (wo.safety_risk and any(k in (wo.safety_risk or "") for k in _HIGH_RISK_KEYWORDS)) or \
               (wo.fault_description and any(k in (wo.fault_description or "") for k in _HIGH_RISK_KEYWORDS))
    if has_risk:
        photos = payload.completion_photos or wo.completion_photos or []
        # 也从维修日志中检查照片
        log_photos: list[str] = []
        for log in wo.logs:
            if log.photos:
                log_photos.extend(log.photos)
        if not photos and not log_photos:
            missing.append("completion_photo")

    return missing


@router.post("/{wo_id}/submit", response_model=WorkOrderDetail)
def submit(wo_id: int, payload: SubmitRequest, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    if wo.status == WorkOrderStatusEnum.pending_acceptance:
        raise conflict("工单已提交，请等待验收")
    if wo.assignee_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有被分派工程师可以提交完工")
    # 完工校验
    missing = _validate_completion(wo, payload, db)
    if missing:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=CompletionValidationError(missing_requirements=missing).model_dump(),
        )
    wo.root_cause = payload.root_cause
    wo.action_taken = payload.action_taken
    wo.replaced_parts = payload.replaced_parts
    wo.test_result = payload.test_result
    wo.equipment_status_after = payload.equipment_status_after
    wo.follow_up_advice = payload.follow_up_advice
    wo.needs_observation = payload.needs_observation
    if payload.completion_photos is not None:
        wo.completion_photos = payload.completion_photos
    change_status(db, wo, WorkOrderStatusEnum.pending_acceptance, user.id)
    # 故障上报状态保持 converted（处理中）
    if wo.fault_report_id:
        _sync_fault_report_status(db, wo.fault_report_id, "converted")
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


def _sync_fault_report_status(db: Session, fault_report_id: int, status: str) -> None:
    """同步故障上报状态。"""
    from app.models.fault import FaultReport
    fr = db.get(FaultReport, fault_report_id)
    if fr:
        fr.status = FaultReportStatusEnum(status)


def _create_knowledge_candidate(db: Session, wo: WorkOrder) -> None:
    """验收通过后自动生成知识库候选条目。"""
    # 防止重复生成
    existing = db.query(KnowledgeArticle).filter(
        KnowledgeArticle.source == f"work_order_{wo.id}",
    ).first()
    if existing:
        return
    eq_name = ""
    if wo.equipment_id:
        eq = db.get(Equipment, wo.equipment_id)
        if eq:
            eq_name = eq.name
    fault_code_str = None
    if wo.fault_code_id:
        fc = db.get(FaultCode, wo.fault_code_id)
        if fc:
            fault_code_str = fc.code
    title = f"[{eq_name or '设备'}] {wo.title}"
    if fault_code_str:
        title += f" ({fault_code_str})"
    content_parts = [
        f"## 故障现象\n{wo.fault_description or '未记录'}",
        f"## 故障代码\n{fault_code_str or '无'}",
        f"## 根本原因\n{wo.root_cause or '未记录'}",
        f"## 处理措施\n{wo.action_taken or '未记录'}",
        f"## 使用备件\n{wo.replaced_parts or '无'}",
        f"## 测试方法\n{wo.test_result or '未记录'}",
        f"## 后续建议\n{wo.follow_up_advice or '建议持续观察设备运行状态'}",
    ]
    # 剔除联系方式等敏感信息
    import re
    cleaned = "\n\n".join(content_parts)
    cleaned = re.sub(r"1[3-9]\d{9}", "***", cleaned)
    cleaned = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "***", cleaned)
    article = KnowledgeArticle(
        title=title[:255],
        category=KnowledgeCategoryEnum.case,
        content=cleaned,
        summary=f"来源于工单 {wo.code} 的维修案例。{wo.root_cause or ''}"[:500],
        source=f"work_order_{wo.id}",
        equipment_type_id=wo.equipment.equipment_type_id if wo.equipment else None,
        fault_code_id=wo.fault_code_id,
        status="draft",
    )
    db.add(article)


@router.post("/{wo_id}/approve", response_model=WorkOrderDetail)
def approve(wo_id: int, payload: AcceptRequest = AcceptRequest(), db: Session = Depends(get_db), user=Depends(supervisor_or_admin)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    # 幂等保护：已完成工单返回冲突
    if wo.status == WorkOrderStatusEnum.completed:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"code": "WORK_ORDER_ALREADY_ACCEPTED", "message": "该工单已完成验收", "work_order_id": wo_id},
        )
    if wo.status != WorkOrderStatusEnum.pending_acceptance:
        raise bad_request("只能验收待验收状态的工单")
    change_status(db, wo, WorkOrderStatusEnum.completed, user.id, remark=payload.acceptance_notes or "验收通过")
    # 设备状态联动
    if wo.equipment_id:
        eq = db.get(Equipment, wo.equipment_id)
        if eq:
            eq.status = EquipmentStatusEnum.running
            eq.last_maintenance_at = datetime.now(timezone.utc).date()
    # 验收记录
    db.add(AcceptanceRecord(work_order_id=wo.id, result="approved", reviewer_id=user.id, remark=payload.acceptance_notes or "验收通过"))
    # 故障上报状态联动
    if wo.fault_report_id:
        _sync_fault_report_status(db, wo.fault_report_id, "closed")
    # 生成维修报告（AI 版本 + 模板降级）
    db.flush()
    try:
        report = ai_generate_report(db, wo_id, user.id)
        generation_method = "template" if report.is_mock else "ai"
    except Exception:
        report = ai_generate_report(db, wo_id, user.id, force_template=True)
        generation_method = "template"
    # 持久化报告
    # 旧版本标记为非当前
    db.query(WorkOrderReport).filter(
        WorkOrderReport.work_order_id == wo_id,
        WorkOrderReport.is_current == True,  # noqa: E712
    ).update({WorkOrderReport.is_current: False})
    persisted = WorkOrderReport(
        work_order_id=wo_id,
        version=_next_report_version(db, wo_id),
        generation_method=generation_method,
        summary=report.summary,
        sections=[s.model_dump() for s in report.sections] if report.sections else None,
        is_current=True,
        generated_by=user.id,
    )
    db.add(persisted)
    # 知识库候选条目
    _create_knowledge_candidate(db, wo)
    db.commit()
    db.refresh(wo)
    return _to_detail(db, wo)


def _next_report_version(db: Session, wo_id: int) -> int:
    max_v = db.query(WorkOrderReport).filter(WorkOrderReport.work_order_id == wo_id).count()
    return max_v + 1


@router.post("/{wo_id}/reject", response_model=WorkOrderDetail)
def reject(wo_id: int, payload: RejectRequest, db: Session = Depends(get_db), user=Depends(supervisor_or_admin)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    if wo.status == WorkOrderStatusEnum.completed:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"code": "WORK_ORDER_ALREADY_ACCEPTED", "message": "该工单已完成验收", "work_order_id": wo_id},
        )
    if not payload.remark or not payload.remark.strip():
        raise bad_request("退回原因不能为空")
    change_status(db, wo, WorkOrderStatusEnum.returned, user.id, remark=f"验收退回：{payload.remark}")
    wo.rejection_reason = payload.remark
    db.add(AcceptanceRecord(work_order_id=wo.id, result="rejected", reviewer_id=user.id, remark=payload.remark))
    # 故障上报状态保持处理中
    if wo.fault_report_id:
        _sync_fault_report_status(db, wo.fault_report_id, "converted")
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
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    _require_execution_access(wo, user)
    if payload.is_completed is not None:
        item.is_completed = payload.is_completed
        item.completed_at = datetime.now(timezone.utc) if payload.is_completed else None
        item.completed_by = user.id if payload.is_completed else None
    if payload.remark is not None:
        item.remark = payload.remark
    db.commit()
    return _to_detail(db, wo)


# ---------- 维修记录 ----------


@router.post("/{wo_id}/logs", response_model=MaintenanceLogOut)
def add_log(wo_id: int, payload: MaintenanceLogCreate, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    _require_execution_access(wo, user)
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


@router.put("/{wo_id}/logs/{log_id}", response_model=MaintenanceLogOut)
def update_log(wo_id: int, log_id: int, payload: MaintenanceLogUpdate, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    log = db.get(MaintenanceLog, log_id)
    if not log or log.work_order_id != wo_id:
        raise not_found("维修记录不存在")
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    _require_execution_access(wo, user)
    if payload.content is not None:
        log.content = payload.content
    if payload.log_type is not None:
        log.log_type = payload.log_type
    if payload.photos is not None:
        log.photos = payload.photos
    if payload.logged_at is not None:
        log.logged_at = payload.logged_at
    db.commit()
    db.refresh(log)
    return MaintenanceLogOut.model_validate(log)


# ---------- 工时 ----------


@router.post("/{wo_id}/labor", response_model=LaborEntryOut)
def add_labor(wo_id: int, payload: LaborEntryCreate, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    _require_execution_access(wo, user)
    # 工时校验
    if payload.hours is not None and payload.hours <= 0:
        raise bad_request("工时必须大于 0")
    if payload.started_at and payload.ended_at and payload.ended_at <= payload.started_at:
        raise bad_request("结束时间不得早于开始时间")
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


@router.put("/{wo_id}/labor/{entry_id}", response_model=LaborEntryOut)
def update_labor(wo_id: int, entry_id: int, payload: LaborEntryUpdate, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    entry = db.get(LaborEntry, entry_id)
    if not entry or entry.work_order_id != wo_id:
        raise not_found("工时记录不存在")
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    _require_execution_access(wo, user)
    if payload.started_at is not None:
        entry.started_at = payload.started_at
    if payload.ended_at is not None:
        entry.ended_at = payload.ended_at
    if payload.hours is not None:
        if payload.hours <= 0:
            raise bad_request("工时必须大于 0")
        entry.hours = payload.hours
    if payload.is_downtime is not None:
        entry.is_downtime = payload.is_downtime
    if payload.remark is not None:
        entry.remark = payload.remark
    # 交叉校验
    if entry.started_at and entry.ended_at and entry.ended_at <= entry.started_at:
        raise bad_request("结束时间不得早于开始时间")
    db.commit()
    db.refresh(entry)
    return LaborEntryOut.model_validate(entry)


@router.delete("/{wo_id}/labor/{entry_id}", response_model=OkResponse)
def delete_labor(wo_id: int, entry_id: int, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    entry = db.get(LaborEntry, entry_id)
    if not entry or entry.work_order_id != wo_id:
        raise not_found("工时记录不存在")
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    _require_execution_access(wo, user)
    db.delete(entry)
    db.commit()
    return OkResponse(message="工时记录已删除")


# ---------- 备件 ----------


@router.post("/{wo_id}/spare-parts", response_model=SparePartUsageOut)
def add_spare_part(wo_id: int, payload: SparePartUsageCreate, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    _require_execution_access(wo, user)
    if payload.quantity <= 0:
        raise bad_request("备件数量必须大于 0")
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


@router.put("/{wo_id}/spare-parts/{record_id}", response_model=SparePartUsageOut)
def update_spare_part(wo_id: int, record_id: int, payload: SparePartUsageUpdate, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    record = db.get(WorkOrderSparePart, record_id)
    if not record or record.work_order_id != wo_id:
        raise not_found("备件记录不存在")
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    _require_execution_access(wo, user)
    if payload.spare_part_id is not None:
        record.spare_part_id = payload.spare_part_id
    if payload.spare_part_code is not None:
        record.spare_part_code = payload.spare_part_code
    if payload.spare_part_name is not None:
        record.spare_part_name = payload.spare_part_name
    if payload.quantity is not None:
        if payload.quantity <= 0:
            raise bad_request("备件数量必须大于 0")
        record.quantity = payload.quantity
    if payload.unit is not None:
        record.unit = payload.unit
    if payload.remark is not None:
        record.remark = payload.remark
    db.commit()
    db.refresh(record)
    return SparePartUsageOut.model_validate(record)


@router.delete("/{wo_id}/spare-parts/{record_id}", response_model=OkResponse)
def delete_spare_part(wo_id: int, record_id: int, db: Session = Depends(get_db), user=Depends(technician_or_above)):
    record = db.get(WorkOrderSparePart, record_id)
    if not record or record.work_order_id != wo_id:
        raise not_found("备件记录不存在")
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    _require_execution_access(wo, user)
    db.delete(record)
    db.commit()
    return OkResponse(message="备件记录已删除")


# ---------- 附件 ----------


@router.post("/{wo_id}/attachments")
def upload_attachment(wo_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(technician_or_above)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    _require_execution_access(wo, user)
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


# ---------- 维修报告 ----------


@router.get("/{wo_id}/report", response_model=ReportGenerateResponse)
def get_report(wo_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    report = db.query(WorkOrderReport).filter(
        WorkOrderReport.work_order_id == wo_id,
        WorkOrderReport.is_current == True,  # noqa: E712
    ).order_by(WorkOrderReport.created_at.desc()).first()
    if not report:
        # 如果没有已持久化报告，尝试实时生成
        try:
            result = ai_generate_report(db, wo_id)
            return ReportGenerateResponse(
                work_order_id=wo.id,
                work_order_code=wo.code,
                summary=result.summary,
                sections=[ReportSectionOut(title=s.title, content=s.content) for s in result.sections],
                generation_method="template" if result.is_mock else "ai",
                version=1,
                is_mock=result.is_mock,
            )
        except Exception:
            raise not_found("该工单暂无报告，请先验收完成")
    sections_out = [ReportSectionOut(title=s.get("title", ""), content=s.get("content", "")) for s in (report.sections or [])]
    return ReportGenerateResponse(
        work_order_id=wo.id,
        work_order_code=wo.code,
        summary=report.summary,
        sections=sections_out,
        generation_method=report.generation_method,
        version=report.version,
        is_mock=report.generation_method == "template",
    )


@router.post("/{wo_id}/report/regenerate", response_model=ReportGenerateResponse)
def regenerate_report(wo_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        raise not_found("工单不存在")
    # 重新生成不修改已有业务数据，只生成新报告版本
    try:
        result = ai_generate_report(db, wo_id, user.id)
        gen_method = "template" if result.is_mock else "ai"
    except Exception:
        result = ai_generate_report(db, wo_id, user.id, force_template=True)
        gen_method = "template"
    # 旧版本标记为非当前
    db.query(WorkOrderReport).filter(
        WorkOrderReport.work_order_id == wo_id,
        WorkOrderReport.is_current == True,  # noqa: E712
    ).update({WorkOrderReport.is_current: False})
    version = _next_report_version(db, wo_id)
    persisted = WorkOrderReport(
        work_order_id=wo_id,
        version=version,
        generation_method=gen_method,
        summary=result.summary,
        sections=[s.model_dump() for s in result.sections] if result.sections else None,
        is_current=True,
        generated_by=user.id,
    )
    db.add(persisted)
    db.commit()
    sections_out = [ReportSectionOut(title=s.title, content=s.content) for s in result.sections]
    return ReportGenerateResponse(
        work_order_id=wo.id,
        work_order_code=wo.code,
        summary=result.summary,
        sections=sections_out,
        generation_method=gen_method,
        version=version,
        is_mock=result.is_mock,
    )
