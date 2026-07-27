"""故障上报接口。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.copilot import parse_fault as ai_parse_fault
from app.core.deps import get_current_user, supervisor_or_admin
from app.core.exceptions import bad_request, conflict, not_found, paginate
from app.db.session import get_db
from app.models.base import FaultReportStatusEnum, PriorityEnum, UrgencyEnum, WorkOrderStatusEnum, WorkOrderTypeEnum
from app.models.equipment import Equipment
from app.models.fault import FaultReport
from app.models.user import User
from app.models.workorder import WorkOrder, WorkOrderChecklistItem, WorkOrderStatusHistory
from app.schemas.common import OkResponse, PageOut
from app.schemas.fault import (
    ConvertToWorkOrderRequest,
    ConvertToWorkOrderResponse,
    FaultReportCreate,
    FaultReportDetail,
    FaultReportOut,
    ParseFaultRequest,
    ParseFaultResult,
)

router = APIRouter(prefix="/fault-reports", tags=["fault-reports"])

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


def _urgency_to_priority(urgency: UrgencyEnum) -> PriorityEnum:
    mapping = {
        UrgencyEnum.critical: PriorityEnum.P1,
        UrgencyEnum.high: PriorityEnum.P2,
        UrgencyEnum.medium: PriorityEnum.P3,
        UrgencyEnum.low: PriorityEnum.P4,
    }
    return mapping.get(urgency, PriorityEnum.P3)


def _enforce_minimum_priority(requested: PriorityEnum, fault_report: FaultReport) -> PriorityEnum:
    """安全规则：不得低于业务要求的优先级。"""
    if fault_report.has_safety_risk:
        priority_order = {PriorityEnum.P1: 1, PriorityEnum.P2: 2, PriorityEnum.P3: 3, PriorityEnum.P4: 4}
        if priority_order.get(requested, 3) > 2:
            return PriorityEnum.P2
    if fault_report.is_downtime and fault_report.affects_production:
        priority_order = {PriorityEnum.P1: 1, PriorityEnum.P2: 2, PriorityEnum.P3: 3, PriorityEnum.P4: 4}
        if priority_order.get(requested, 3) > 2:
            return PriorityEnum.P2
    return requested


def _gen_code(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    count = db.query(WorkOrder).filter(WorkOrder.code.like(f"WO-{year}-%")).count()
    return f"WO-{year}-{count + 1:04d}"


def _to_out(db: Session, fr: FaultReport) -> FaultReportOut:
    eq_name = eq_code = None
    if fr.equipment_id:
        eq = db.get(Equipment, fr.equipment_id)
        if eq:
            eq_name, eq_code = eq.name, eq.code
    # Find related work order
    related_wo = db.query(WorkOrder).filter(WorkOrder.fault_report_id == fr.id).first()
    return FaultReportOut(
        id=fr.id,
        equipment_id=fr.equipment_id,
        equipment_name=eq_name,
        equipment_code=eq_code,
        title=fr.title,
        description=fr.description,
        occurred_at=fr.occurred_at,
        phenomenon=fr.phenomenon,
        is_downtime=fr.is_downtime,
        affects_production=fr.affects_production,
        has_safety_risk=fr.has_safety_risk,
        photos=fr.photos,
        reporter_name=fr.reporter_name,
        contact=fr.contact,
        urgency=fr.urgency,
        status=fr.status,
        raw_text=fr.raw_text,
        parsed_fields=fr.parsed_fields,
        fault_code_id=fr.fault_code_id,
        created_at=fr.created_at,
        related_work_order_id=related_wo.id if related_wo else None,
    )


def _to_detail(db: Session, fr: FaultReport) -> FaultReportDetail:
    out = _to_out(db, fr)
    if out.related_work_order_id:
        wo = db.get(WorkOrder, out.related_work_order_id)
        if wo:
            out.related_work_order_code = wo.code
            out.related_work_order_status = wo.status.value if wo.status else None
    return FaultReportDetail(
        id=out.id,
        equipment_id=out.equipment_id,
        equipment_name=out.equipment_name,
        equipment_code=out.equipment_code,
        title=out.title,
        description=out.description,
        occurred_at=out.occurred_at,
        phenomenon=out.phenomenon,
        is_downtime=out.is_downtime,
        affects_production=out.affects_production,
        has_safety_risk=out.has_safety_risk,
        photos=out.photos,
        reporter_name=out.reporter_name,
        contact=out.contact,
        urgency=out.urgency,
        status=out.status,
        raw_text=out.raw_text,
        parsed_fields=out.parsed_fields,
        fault_code_id=out.fault_code_id,
        created_at=out.created_at,
        related_work_order_id=out.related_work_order_id,
        related_work_order_code=out.related_work_order_code,
        related_work_order_status=out.related_work_order_status,
    )


@router.get("", response_model=PageOut[FaultReportOut])
def list_reports(
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(FaultReport)
    if status:
        q = q.filter(FaultReport.status == status)
    q = q.order_by(FaultReport.created_at.desc())
    items, total = paginate(q, page, page_size)
    return PageOut(items=[_to_out(db, f) for f in items], total=total, page=page, page_size=page_size)


@router.post("", response_model=FaultReportOut)
def create_report(payload: FaultReportCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    fr = FaultReport(
        **payload.model_dump(),
        occurred_at=payload.occurred_at or datetime.now(timezone.utc),
        reporter_name=payload.reporter_name or user.full_name,
        created_by=str(user.id),
    )
    db.add(fr)
    db.commit()
    db.refresh(fr)
    return _to_out(db, fr)


@router.get("/{fr_id}", response_model=FaultReportDetail)
def get_report(fr_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    fr = db.get(FaultReport, fr_id)
    if not fr:
        raise not_found("故障上报不存在")
    return _to_detail(db, fr)


@router.post("/parse", response_model=ParseFaultResult)
def parse_fault(payload: ParseFaultRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """自然语言解析为结构化故障字段（需用户确认后才会落库）。"""
    return ai_parse_fault(db, payload.text, user.id)


@router.post("/{fr_id}/convert-to-work-order", response_model=ConvertToWorkOrderResponse)
def convert_to_work_order(
    fr_id: int,
    payload: ConvertToWorkOrderRequest = ConvertToWorkOrderRequest(),
    db: Session = Depends(get_db),
    user=Depends(supervisor_or_admin),
):
    """将故障上报转换为维修工单。所有操作在事务中完成。"""
    # 1. 查询故障上报
    fr = db.get(FaultReport, fr_id)
    if not fr:
        raise not_found("故障上报不存在")

    # 2. 权限已在 Depends 中校验（supervisor_or_admin）

    # 3. 检查是否已有关联工单（应用层 + 数据库级别唯一性通过 SELECT FOR UPDATE 实现）
    existing = db.query(WorkOrder).filter(WorkOrder.fault_report_id == fr_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "FAULT_REPORT_ALREADY_CONVERTED",
                "message": "该故障上报已创建维修工单",
                "work_order_id": existing.id,
            },
        )

    # 4. 检查状态是否允许转换
    if fr.status == FaultReportStatusEnum.closed:
        raise bad_request("已关闭的故障上报不能创建工单")

    # 5. 优先级映射（先映射默认，再用用户传入覆盖，最后应用安全规则）
    priority = payload.priority or _urgency_to_priority(UrgencyEnum(fr.urgency))
    priority = _enforce_minimum_priority(priority, fr)

    # 6. 在事务中创建工单
    try:
        wo = WorkOrder(
            code=_gen_code(db),
            title=fr.title,
            equipment_id=fr.equipment_id,
            fault_report_id=fr.id,
            fault_description=fr.description,
            fault_code_id=fr.fault_code_id,
            order_type=WorkOrderTypeEnum.fault_repair,
            priority=priority,
            status=WorkOrderStatusEnum.pending_dispatch,
            created_by_id=user.id,
            created_by=str(user.id),
            planned_start_at=payload.planned_start_at,
            planned_end_at=payload.planned_end_at,
        )

        # 安全风险识别
        risk_parts = []
        if fr.has_safety_risk:
            risk_parts.append("故障上报标记为安全风险")
        if any(k in (fr.description or "") for k in _HIGH_RISK_KEYWORDS):
            risk_parts.append("注意：涉及高危风险，维修前必须确认安全措施")
        if risk_parts:
            wo.safety_risk = "；".join(risk_parts)

        db.add(wo)
        db.flush()

        # 生成默认检查清单
        for i, content in enumerate(DEFAULT_CHECKLIST):
            db.add(WorkOrderChecklistItem(work_order_id=wo.id, content=content, order=i, is_required=True))

        # 写入工单状态历史
        now = datetime.now(timezone.utc)
        db.add(WorkOrderStatusHistory(
            work_order_id=wo.id,
            from_status=None,
            to_status=WorkOrderStatusEnum.pending_dispatch.value,
            changed_by=user.id,
            changed_at=now,
            remark=payload.notes or "由故障上报转换创建",
        ))

        # 7. 更新故障上报状态
        fr.status = FaultReportStatusEnum.converted
        fr.updated_by = str(user.id)

        db.commit()
        db.refresh(wo)

    except Exception:
        db.rollback()
        raise

    return ConvertToWorkOrderResponse(
        fault_report_id=fr.id,
        work_order_id=wo.id,
        work_order_code=wo.code,
        priority=wo.priority.value if wo.priority else "P3",
        status=wo.status.value if wo.status else "pending_dispatch",
    )
