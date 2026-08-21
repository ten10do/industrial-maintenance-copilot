"""工业报警 API：查看、人工确认（acknowledge）与智能分析。

报警由 OPC UA DataChange / Alarm 事件流水线产生（只读采集的派生记录）；
确认与分析操作只修改平台内的记录，不向设备写入任何内容。

Alarm Intelligence 定位：**AI-assisted industrial alarm analysis**——
理解摘要、根因假设与维护建议仅供人工决策参考，不执行任何控制。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, supervisor_or_admin
from app.db.session import get_db
from app.industrial_gateway.alarm_intelligence.correlation import (
    DEFAULT_WINDOW_SECONDS,
    correlate_alarms,
)
from app.industrial_gateway.alarm_intelligence.engine import (
    analyze_root_cause,
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
    CorrelateOut,
    IndustrialAlarmOut,
)
from app.models.equipment import Equipment
from app.models.user import User

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
    return {
        "items": [IndustrialAlarmOut.model_validate(row) for row in rows],
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

    telemetry_fields, telemetry_record_id = latest_telemetry_fields(
        db, alarm.equipment_id
    )
    understanding = understand_alarm(
        severity=alarm.severity,
        message=alarm.message,
        telemetry_fields=telemetry_fields,
    )
    rca = analyze_root_cause(
        db,
        severity=alarm.severity,
        message=alarm.message,
        telemetry_fields=telemetry_fields,
        telemetry_record_id=telemetry_record_id,
        equipment_name=equipment.name,
        equipment_type_id=equipment.equipment_type_id,
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
    for group in correlate_alarms(neighbours, window_seconds=window_seconds):
        if alarm.id in group.alarm_ids:
            correlation_group_id = group.group_id
            break

    record = (
        db.query(AlarmAnalysisRecord)
        .filter(AlarmAnalysisRecord.alarm_id == alarm.id)
        .first()
    )
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
    record.requires_human_review = decision.requires_human_review
    record.model_version = "deterministic-rules-v1"
    record.is_mock = True
    db.commit()
    db.refresh(record)
    return AlarmAnalysisOut.model_validate(record)


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
