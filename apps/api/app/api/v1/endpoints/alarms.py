"""工业报警 API：查看、人工确认（acknowledge）与智能分析。

报警由 OPC UA DataChange / Alarm 事件流水线产生（只读采集的派生记录）；
确认与分析操作只修改平台内的记录，不向设备写入任何内容。

Alarm Intelligence 定位：**AI-assisted industrial alarm analysis**——
理解摘要、根因假设与维护建议仅供人工决策参考，不执行任何控制。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, supervisor_or_admin
from app.db.session import get_db
from app.industrial_gateway.alarm_intelligence.correlation import (
    DEFAULT_WINDOW_SECONDS,
    correlate_alarms,
)
from app.industrial_gateway.alarm_intelligence.engine import (
    analyze_root_cause,
    assess_alarm_risk,
    build_decision_support,
    latest_telemetry_fields,
    understand_alarm,
)
from app.industrial_gateway.models import (
    AlarmAnalysisRecord,
    IndustrialAlarm,
)
from app.industrial_gateway.schemas import (
    AlarmAnalysisOut,
    AlarmReviewIn,
    AlarmWorkOrderOut,
    CorrelateOut,
    IndustrialAlarmOut,
)
from app.models.base import PriorityEnum, WorkOrderStatusEnum, WorkOrderTypeEnum
from app.models.equipment import Equipment
from app.models.intelligence import AgentRun, RiskPrediction, ToolInvocation
from app.models.user import User
from app.models.workorder import (
    WorkOrder,
    WorkOrderChecklistItem,
    WorkOrderStatusHistory,
)
from app.services.work_order_codes import generate_work_order_code

router = APIRouter(prefix="/alarms", tags=["industrial-alarms"])


@router.get("")
def list_alarms(
    status: str | None = Query(default=None, description="active|acknowledged|cleared"),
    equipment_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    """查看工业报警列表（severity / equipment / timestamp / status）。"""
    query = db.query(IndustrialAlarm)
    if status == "active":
        query = query.filter(IndustrialAlarm.cleared_at.is_(None))
    elif status == "cleared":
        query = query.filter(IndustrialAlarm.cleared_at.is_not(None))
    elif status == "acknowledged":
        query = query.filter(IndustrialAlarm.acknowledged.is_(True))
    if equipment_id is not None:
        query = query.filter(IndustrialAlarm.equipment_id == equipment_id)
    total = query.count()
    rows = query.order_by(IndustrialAlarm.created_at.desc()).limit(limit).all()
    analyses = {
        item.alarm_id: item
        for item in db.query(AlarmAnalysisRecord)
        .filter(AlarmAnalysisRecord.alarm_id.in_([row.id for row in rows]))
        .all()
    }
    return {
        "items": [_alarm_out(row, analyses.get(row.id)) for row in rows],
        "total": total,
        "read_only_source": True,
    }


@router.post("/{alarm_id}/acknowledge")
def acknowledge_alarm(
    alarm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(supervisor_or_admin),
) -> dict[str, object]:
    """人工确认报警（平台内记录，不触碰设备）。"""
    alarm = _get_alarm_or_404(db, alarm_id)
    if not alarm.acknowledged:
        alarm.acknowledged = True
        alarm.acknowledged_at = datetime.now(UTC)
        alarm.acknowledged_by = user.id
        db.commit()
        db.refresh(alarm)
    return {
        "ok": True,
        "id": alarm.id,
        "acknowledged": alarm.acknowledged,
        "acknowledged_at": alarm.acknowledged_at.isoformat()
        if alarm.acknowledged_at
        else None,
    }


def _get_alarm_or_404(db: Session, alarm_id: int) -> IndustrialAlarm:
    alarm = db.get(IndustrialAlarm, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="工业报警不存在")
    return alarm


def _alarm_out(
    alarm: IndustrialAlarm, analysis: AlarmAnalysisRecord | None
) -> IndustrialAlarmOut:
    correlated_count = 0
    if analysis:
        raw_count = (analysis.evidence or {}).get("correlated_alarm_count", 0)
        correlated_count = int(raw_count) if isinstance(raw_count, (int, float)) else 0
    return IndustrialAlarmOut(
        **IndustrialAlarmOut.model_validate(alarm).model_dump(
            exclude={
                "risk_level",
                "analysis_status",
                "correlation_group_id",
                "correlated_alarm_count",
            }
        ),
        risk_level=analysis.risk_level if analysis else None,
        analysis_status=analysis.analysis_status if analysis else "NEW",
        correlation_group_id=analysis.correlation_group_id if analysis else None,
        correlated_alarm_count=correlated_count,
    )


# ----------------------------------------------------------------------
# Alarm Intelligence（AI-assisted analysis，仅建议，不执行）
# ----------------------------------------------------------------------


@router.post("/correlate", response_model=CorrelateOut)
def correlate_active_alarms(
    window_seconds: float = Query(default=DEFAULT_WINDOW_SECONDS, ge=30.0, le=3600.0),
    db: Session = Depends(get_db),
    _user: User = Depends(supervisor_or_admin),
) -> CorrelateOut:
    """对当前活动报警做关联分组（同设备时间窗 + 同产线级联）。"""
    active = (
        db.query(IndustrialAlarm)
        .filter(IndustrialAlarm.cleared_at.is_(None))
        .order_by(IndustrialAlarm.created_at)
        .all()
    )
    equipment_ids = {alarm.equipment_id for alarm in active}
    lines: dict[int, str | None] = {}
    if equipment_ids:
        rows = (
            db.query(Equipment.id, Equipment.production_line)
            .filter(Equipment.id.in_(equipment_ids))
            .all()
        )
        lines = {row_id: line for row_id, line in rows}
    groups = correlate_alarms(
        active,
        window_seconds=window_seconds,
        production_line_by_equipment=lines,
    )
    return CorrelateOut(
        groups=[
            {
                "group_id": group.group_id,
                "reason": group.reason,
                "alarm_ids": group.alarm_ids,
                "equipment_ids": group.equipment_ids,
                "severity": group.severity,
                "window_start": group.window_start,
                "window_end": group.window_end,
                "size": group.size,
            }
            for group in groups
        ],
        total_alarms=len(active),
    )


@router.get("/{alarm_id}", response_model=IndustrialAlarmOut)
def get_alarm_event(
    alarm_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> IndustrialAlarmOut:
    """读取报警事件及其分析工作流摘要。"""
    alarm = _get_alarm_or_404(db, alarm_id)
    analysis = (
        db.query(AlarmAnalysisRecord)
        .filter(AlarmAnalysisRecord.alarm_id == alarm_id)
        .first()
    )
    return _alarm_out(alarm, analysis)


@router.post("/{alarm_id}/analyze", response_model=AlarmAnalysisOut)
def analyze_alarm(
    alarm_id: int,
    window_seconds: float = Query(default=DEFAULT_WINDOW_SECONDS, ge=30.0, le=3600.0),
    db: Session = Depends(get_db),
    _user: User = Depends(supervisor_or_admin),
) -> AlarmAnalysisOut:
    """生成并持久化报警智能分析（理解 + 根因 + 决策建议，仅建议不执行）。"""
    alarm = _get_alarm_or_404(db, alarm_id)
    equipment = db.get(Equipment, alarm.equipment_id)
    if equipment is None:
        raise HTTPException(status_code=404, detail="报警关联的设备不存在")
    existing_record = (
        db.query(AlarmAnalysisRecord)
        .filter(AlarmAnalysisRecord.alarm_id == alarm.id)
        .first()
    )
    if existing_record and existing_record.analysis_status in {
        "APPROVED",
        "WORK_ORDER_CREATED",
    }:
        raise HTTPException(status_code=409, detail="已审批的分析不能被重新生成")

    started_at = datetime.now(UTC)
    started_clock = perf_counter()
    agent_run = AgentRun(
        equipment_id=equipment.id,
        goal="工业报警关联、证据约束根因分析与维护决策支持",
        status="running",
        provider="deterministic-rules-v1",
        input={"alarm_event_id": alarm.id, "window_seconds": window_seconds},
        confidence=0.0,
        requires_human_review=True,
        started_at=started_at,
    )
    db.add(agent_run)
    db.flush()

    telemetry_fields, telemetry_record_id = latest_telemetry_fields(
        db, alarm.equipment_id
    )
    understanding = understand_alarm(
        severity=alarm.severity,
        message=alarm.message,
        telemetry_fields=telemetry_fields,
    )
    prediction = (
        db.query(RiskPrediction)
        .filter(RiskPrediction.equipment_id == alarm.equipment_id)
        .order_by(RiskPrediction.created_at.desc())
        .first()
    )
    prediction_context = (
        {
            "prediction_id": prediction.id,
            "failure_mode": prediction.failure_mode,
            "probability": prediction.probability,
            "model_version": prediction.model_version,
        }
        if prediction
        else None
    )
    rca = analyze_root_cause(
        db,
        severity=alarm.severity,
        message=alarm.message,
        telemetry_fields=telemetry_fields,
        telemetry_record_id=telemetry_record_id,
        equipment_name=equipment.name,
        equipment_type_id=equipment.equipment_type_id,
        prediction_context=prediction_context,
    )
    decision = build_decision_support(
        db,
        severity=alarm.severity,
        fault_type=rca.fault_type,
        confidence=rca.confidence,
        equipment_id=alarm.equipment_id,
    )

    # 关联组：同设备 ±window 内的报警一起分组，取包含当前报警的组。
    window = timedelta(seconds=window_seconds)
    neighbours = (
        db.query(IndustrialAlarm)
        .filter(
            IndustrialAlarm.equipment_id == alarm.equipment_id,
            IndustrialAlarm.created_at.between(
                alarm.created_at - window, alarm.created_at + window
            ),
        )
        .all()
    )
    correlation_group_id: str | None = None
    correlated_alarm_count = 1
    for group in correlate_alarms(neighbours, window_seconds=window_seconds):
        if alarm.id in group.alarm_ids:
            correlation_group_id = group.group_id
            correlated_alarm_count = group.size
            break

    risk = assess_alarm_risk(
        severity=alarm.severity,
        confidence=rca.confidence,
        correlated_alarm_count=correlated_alarm_count,
        equipment_health_score=equipment.health_score,
        equipment_risk_level=equipment.risk_level,
        fault_probability=prediction.probability if prediction else None,
    )
    mandatory_review = (
        rca.confidence < 0.7
        or bool(rca.evidence_conflicts)
        or not rca.citations
        or risk.risk_level in {"HIGH", "CRITICAL"}
    )

    record = existing_record
    if record is None:
        record = AlarmAnalysisRecord(alarm_id=alarm.id)
        db.add(record)
    record.correlation_group_id = correlation_group_id
    record.summary = understanding.summary
    record.root_cause_hypothesis = rca.hypothesis
    record.contributing_factors = rca.contributing_factors
    record.evidence = {
        **rca.evidence,
        "understanding": {
            "triggered_rules": understanding.triggered_rules,
            "abnormal_metrics": understanding.abnormal_metrics,
        },
        "decision_support": {
            "suggested_priority": decision.suggested_priority,
            "related_work_orders": decision.related_work_orders,
        },
        "correlated_alarm_count": correlated_alarm_count,
        "risk_assessment": {"inputs": risk.inputs, "reasons": risk.reasons},
        "mandatory_review_reasons": {
            "low_confidence": rca.confidence < 0.7,
            "conflicting_evidence": bool(rca.evidence_conflicts),
            "missing_rag_evidence": not rca.citations,
            "high_or_critical_risk": risk.risk_level in {"HIGH", "CRITICAL"},
        },
    }
    record.citations = rca.citations
    record.confidence = rca.confidence
    record.recommended_actions = decision.recommended_actions
    record.suggested_priority = decision.suggested_priority
    record.related_work_order_id = (
        decision.related_work_orders[0]["work_order_id"]
        if decision.related_work_orders
        else None
    )
    record.risk_level = risk.risk_level
    record.analysis_status = "WAITING_REVIEW"
    record.review_status = None
    record.reviewed_by = None
    record.reviewed_at = None
    record.review_note = None
    record.requires_human_review = mandatory_review
    record.agent_run_id = agent_run.id
    record.model_version = "deterministic-rules-v1"
    record.is_mock = True
    duration_ms = int((perf_counter() - started_clock) * 1000)
    db.add_all(
        [
            ToolInvocation(
                agent_run_id=agent_run.id,
                tool_name="alarm_correlation",
                provider="local",
                status="success",
                request={"alarm_event_id": alarm.id, "window_seconds": window_seconds},
                response={
                    "correlation_group_id": correlation_group_id,
                    "correlated_alarm_count": correlated_alarm_count,
                },
                duration_ms=0,
            ),
            ToolInvocation(
                agent_run_id=agent_run.id,
                tool_name="maintenance_knowledge_search",
                provider="local",
                status="success",
                request={"alarm_event_id": alarm.id, "equipment_id": equipment.id},
                response={
                    "citation_article_ids": [
                        item.get("article_id") for item in rca.citations
                    ],
                    "evidence_count": len(rca.citations),
                },
                duration_ms=0,
            ),
        ]
    )
    agent_run.status = "completed"
    agent_run.output = {
        "alarm_event_id": alarm.id,
        "analysis_status": record.analysis_status,
        "risk_level": risk.risk_level,
        "confidence": rca.confidence,
        "evidence_article_ids": [item.get("article_id") for item in rca.citations],
        "latency_ms": duration_ms,
    }
    agent_run.confidence = rca.confidence
    agent_run.requires_human_review = mandatory_review
    agent_run.finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(record)
    return AlarmAnalysisOut.model_validate(record)


@router.post("/{alarm_id}/review", response_model=AlarmAnalysisOut)
def review_alarm_analysis(
    alarm_id: int,
    payload: AlarmReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(supervisor_or_admin),
) -> AlarmAnalysisOut:
    """人工复核分析；不触发设备命令。"""
    _get_alarm_or_404(db, alarm_id)
    record = (
        db.query(AlarmAnalysisRecord)
        .filter(AlarmAnalysisRecord.alarm_id == alarm_id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=409, detail="请先生成报警分析")
    target_by_action = {
        "approve": "APPROVED",
        "reject": "REJECTED",
        "request_more_evidence": "WAITING_REVIEW",
    }
    target = target_by_action[payload.action]
    if record.analysis_status == target and record.review_status == payload.action:
        return AlarmAnalysisOut.model_validate(record)
    if record.analysis_status not in {"WAITING_REVIEW", "DIAGNOSED"}:
        raise HTTPException(
            status_code=409,
            detail=f"非法分析状态流转：{record.analysis_status} -> {target}",
        )
    record.analysis_status = target
    record.review_status = payload.action
    record.reviewed_by = user.id
    record.reviewed_at = datetime.now(UTC)
    record.review_note = payload.note
    record.requires_human_review = payload.action == "request_more_evidence"
    db.commit()
    db.refresh(record)
    return AlarmAnalysisOut.model_validate(record)


@router.post("/{alarm_id}/create-work-order", response_model=AlarmWorkOrderOut)
def create_alarm_work_order(
    alarm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(supervisor_or_admin),
) -> AlarmWorkOrderOut:
    """经人工批准后创建正式工单；重复请求返回同一工单。"""
    alarm = _get_alarm_or_404(db, alarm_id)
    record = (
        db.query(AlarmAnalysisRecord)
        .filter(AlarmAnalysisRecord.alarm_id == alarm_id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=409, detail="请先生成并复核报警分析")
    if record.created_work_order_id:
        existing = db.get(WorkOrder, record.created_work_order_id)
        if existing:
            return AlarmWorkOrderOut(
                alarm_id=alarm_id,
                analysis_id=record.id,
                work_order_id=existing.id,
                work_order_code=existing.code,
                status=existing.status.value,
                created=False,
            )
    if record.analysis_status != "APPROVED" or record.review_status != "approve":
        raise HTTPException(
            status_code=409,
            detail="必须先由主管或管理员批准报警分析，才能创建工单",
        )
    claim = db.execute(
        update(AlarmAnalysisRecord)
        .where(
            AlarmAnalysisRecord.id == record.id,
            AlarmAnalysisRecord.analysis_status == "APPROVED",
            AlarmAnalysisRecord.review_status == "approve",
            AlarmAnalysisRecord.created_work_order_id.is_(None),
        )
        .values(analysis_status="CREATING_WORK_ORDER")
    )
    if claim.rowcount != 1:
        db.rollback()
        db.expire_all()
        current = db.get(AlarmAnalysisRecord, record.id)
        if current and current.created_work_order_id:
            existing = db.get(WorkOrder, current.created_work_order_id)
            if existing:
                return AlarmWorkOrderOut(
                    alarm_id=alarm_id,
                    analysis_id=current.id,
                    work_order_id=existing.id,
                    work_order_code=existing.code,
                    status=existing.status.value,
                    created=False,
                )
        raise HTTPException(status_code=409, detail="工单创建请求正在处理中")
    priority = PriorityEnum(record.suggested_priority)
    work_order = WorkOrder(
        code=generate_work_order_code(),
        title=f"[报警处置] 设备 #{alarm.equipment_id} {alarm.severity} 报警",
        equipment_id=alarm.equipment_id,
        fault_description=(
            f"来源报警 #{alarm.id}：{alarm.message}\n{record.root_cause_hypothesis}"
        ),
        order_type=WorkOrderTypeEnum.fault_repair,
        priority=priority,
        status=WorkOrderStatusEnum.pending_dispatch,
        safety_risk="执行前必须确认现场安全条件并按既有流程完成 LOTO 与操作审批。",
        ai_diagnosis_summary=record.root_cause_hypothesis,
        maintenance_steps=record.recommended_actions,
        acceptance_criteria="完成现场复核、维修后测试与遥测验证，未经审批不得执行设备命令。",
        created_by_id=user.id,
        created_by=str(user.id),
    )
    db.add(work_order)
    db.flush()
    db.add(
        WorkOrderStatusHistory(
            work_order_id=work_order.id,
            from_status=None,
            to_status=WorkOrderStatusEnum.pending_dispatch.value,
            changed_by=user.id,
            changed_at=datetime.now(UTC),
            remark=f"由已批准的报警分析 #{record.id} 创建",
        )
    )
    checklist = (
        ("safety", "设备操作前执行 LOTO 并确认既有 OperationApproval", True),
        ("diagnosis", "现场复核报警、遥测、预测与知识证据", True),
        ("repair", "按批准后的维修方案执行", True),
        ("testing", "采集维修后遥测并验证报警解除", True),
    )
    for order, (category, content, required) in enumerate(checklist):
        db.add(
            WorkOrderChecklistItem(
                work_order_id=work_order.id,
                category=category,
                content=content,
                order=order,
                is_required=required,
            )
        )
    record.created_work_order_id = work_order.id
    record.analysis_status = "WORK_ORDER_CREATED"
    db.commit()
    db.refresh(work_order)
    return AlarmWorkOrderOut(
        alarm_id=alarm_id,
        analysis_id=record.id,
        work_order_id=work_order.id,
        work_order_code=work_order.code,
        status=work_order.status.value,
        created=True,
    )


@router.get("/{alarm_id}/analysis", response_model=AlarmAnalysisOut)
def get_alarm_analysis(
    alarm_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AlarmAnalysisOut:
    """读取已持久化的报警分析结论。"""
    _get_alarm_or_404(db, alarm_id)
    record = (
        db.query(AlarmAnalysisRecord)
        .filter(AlarmAnalysisRecord.alarm_id == alarm_id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="该报警尚未生成分析")
    return AlarmAnalysisOut.model_validate(record)
