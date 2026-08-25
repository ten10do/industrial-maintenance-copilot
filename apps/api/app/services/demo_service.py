"""Demo State 聚合（只读 read model）。

原则：

- 仅聚合**既有领域对象**，不创建任何业务数据；
- 所有字段来自真实数据库查询；某阶段未发生时显式返回 null，
  绝不伪造"完整链路"；
- 不复制 domain service 逻辑。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.industrial_gateway.models import (
    AlarmAnalysisRecord,
    GatewayConnection,
    IndustrialAlarm,
)
from app.models.equipment import Equipment
from app.models.intelligence import (
    AgentRun,
    AnomalyEvent,
    MaintenanceRecommendation,
    OperationApproval,
    RiskPrediction,
    TelemetryRecord,
)
from app.models.workorder import WorkOrder


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def get_demo_state(db: Session, *, equipment_code: str = "Motor001") -> dict[str, Any]:
    """聚合一次演示所需的全部真实状态。"""
    from app.industrial_gateway.opcua.service import get_gateway_runtime

    equipment = db.query(Equipment).filter(Equipment.code == equipment_code).first()
    if equipment is None:
        equipment = db.query(Equipment).order_by(Equipment.id).first()

    if equipment is None:
        return {
            "equipment": None,
            "simulator": _simulator_state(),
            "gateway": {
                "enabled": settings.GATEWAY_ENABLED,
                "mode": settings.GATEWAY_MODE,
            },
            "telemetry": None,
            "quality": None,
            "anomaly": None,
            "prediction": None,
            "recommendation": None,
            "alarm": None,
            "analysis": None,
            "work_order": None,
            "approval": None,
            "trace_id": None,
        }

    telemetry = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.equipment_id == equipment.id)
        .order_by(TelemetryRecord.collected_at.desc(), TelemetryRecord.id.desc())
        .first()
    )
    anomaly = (
        db.query(AnomalyEvent)
        .filter(AnomalyEvent.equipment_id == equipment.id)
        .order_by(AnomalyEvent.detected_at.desc(), AnomalyEvent.id.desc())
        .first()
    )
    prediction = (
        db.query(RiskPrediction)
        .filter(RiskPrediction.equipment_id == equipment.id)
        .order_by(RiskPrediction.created_at.desc(), RiskPrediction.id.desc())
        .first()
    )
    recommendation = (
        db.query(MaintenanceRecommendation)
        .filter(MaintenanceRecommendation.equipment_id == equipment.id)
        .order_by(
            MaintenanceRecommendation.created_at.desc(),
            MaintenanceRecommendation.id.desc(),
        )
        .first()
    )
    alarm = (
        db.query(IndustrialAlarm)
        .filter(IndustrialAlarm.equipment_id == equipment.id)
        .order_by(IndustrialAlarm.created_at.desc(), IndustrialAlarm.id.desc())
        .first()
    )
    analysis = (
        db.query(AlarmAnalysisRecord)
        .join(IndustrialAlarm, AlarmAnalysisRecord.alarm_id == IndustrialAlarm.id)
        .filter(IndustrialAlarm.equipment_id == equipment.id)
        .order_by(AlarmAnalysisRecord.created_at.desc(), AlarmAnalysisRecord.id.desc())
        .first()
    )
    work_order = (
        db.query(WorkOrder)
        .filter(WorkOrder.equipment_id == equipment.id)
        .order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc())
        .first()
    )
    approval_pending = (
        db.query(OperationApproval)
        .filter(
            OperationApproval.equipment_id == equipment.id,
            OperationApproval.status.in_(["pending", "execution_unknown"]),
        )
        .order_by(OperationApproval.requested_at.desc())
        .first()
    )
    agent_run = (
        db.query(AgentRun)
        .filter(AgentRun.equipment_id == equipment.id)
        .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
        .first()
    )

    trace_id = None
    for candidate in (alarm, anomaly, telemetry, work_order):
        if candidate is not None and getattr(candidate, "trace_id", None):
            trace_id = candidate.trace_id
            break

    gateway_row = db.query(GatewayConnection).first()
    quality_summary = None
    runtime = get_gateway_runtime()
    if runtime is not None:
        last_sync = runtime.status().get("last_sync")
        if last_sync:
            quality_summary = {
                "accepted": last_sync.get("accepted"),
                "rejected": last_sync.get("rejected"),
                "reject_reasons": last_sync.get("reject_reasons") or {},
                "corrections": last_sync.get("corrections"),
                "snapshots_ingested": last_sync.get("snapshots_ingested"),
            }

    return {
        "equipment": {
            "id": equipment.id,
            "code": equipment.code,
            "name": equipment.name,
            "status": equipment.status.value if equipment.status else None,
            "health_score": equipment.health_score,
            "risk_level": equipment.risk_level.value if equipment.risk_level else None,
        },
        "simulator": _simulator_state(),
        "gateway": {
            "enabled": settings.GATEWAY_ENABLED,
            "mode": settings.GATEWAY_MODE,
            "status": gateway_row.status if gateway_row else None,
            "last_sync_at": _iso(gateway_row.last_sync_at) if gateway_row else None,
        },
        "telemetry": {
            "id": telemetry.id,
            "collected_at": _iso(telemetry.collected_at),
            "temperature_c": telemetry.bearing_temperature,
            "vibration_rms": telemetry.vibration_rms,
            "motor_current_a": telemetry.motor_current,
            "motor_voltage_v": telemetry.motor_voltage,
            "speed_rpm": telemetry.rotational_speed,
            "load_ratio_pct": telemetry.load_ratio,
            "quality": telemetry.quality,
            "is_anomaly": telemetry.is_anomaly,
            "trace_id": telemetry.trace_id,
        }
        if telemetry
        else None,
        "quality": quality_summary,
        "anomaly": {
            "id": anomaly.id,
            "fault_type": anomaly.fault_type,
            "title": anomaly.title,
            "severity": anomaly.severity.value if anomaly.severity else None,
            "status": anomaly.status,
            "confidence": anomaly.confidence,
            "detected_at": _iso(anomaly.detected_at),
            "trace_id": anomaly.trace_id,
        }
        if anomaly
        else None,
        "prediction": {
            "id": prediction.id,
            "model_version": prediction.model_version,
            "failure_mode": prediction.failure_mode,
            "probability": prediction.probability,
            "remaining_useful_life_hours": prediction.remaining_useful_life_hours,
            "is_mock": prediction.is_mock,
            "created_at": _iso(prediction.created_at),
        }
        if prediction
        else None,
        "recommendation": {
            "id": recommendation.id,
            "title": recommendation.title,
            "strategy": recommendation.strategy,
            "priority": recommendation.priority,
            "auto_work_order_id": recommendation.auto_work_order_id,
        }
        if recommendation
        else None,
        "alarm": {
            "id": alarm.id,
            "severity": alarm.severity,
            "message": alarm.message,
            "source": alarm.source,
            "acknowledged": alarm.acknowledged,
            "cleared": alarm.cleared_at is not None,
            "created_at": _iso(alarm.created_at),
            "trace_id": alarm.trace_id,
        }
        if alarm
        else None,
        "analysis": {
            "id": analysis.id,
            "alarm_id": analysis.alarm_id,
            "analysis_status": analysis.analysis_status,
            "review_status": analysis.review_status,
            "confidence": analysis.confidence,
            "risk_level": analysis.risk_level,
            "root_cause_hypothesis": analysis.root_cause_hypothesis,
            "recommended_actions": analysis.recommended_actions or [],
            "citations": (analysis.citations or [])[:3],
            "model_version": analysis.model_version,
            "requires_human_review": analysis.requires_human_review,
            "created_work_order_id": analysis.created_work_order_id,
        }
        if analysis
        else None,
        "work_order": {
            "id": work_order.id,
            "code": work_order.code,
            "title": work_order.title,
            "status": work_order.status.value if work_order.status else None,
            "priority": work_order.priority.value if work_order.priority else None,
            "assignee_id": work_order.assignee_id,
            "trace_id": work_order.trace_id,
        }
        if work_order
        else None,
        "approval": {
            "id": approval_pending.id,
            "command_type": approval_pending.command_type,
            "risk_level": approval_pending.risk_level.value
            if approval_pending.risk_level
            else None,
            "status": approval_pending.status,
        }
        if approval_pending
        else None,
        "agent_run": {
            "id": agent_run.id,
            "goal": agent_run.goal,
            "status": agent_run.status,
            "provider": agent_run.provider,
        }
        if agent_run
        else None,
        "trace_id": trace_id,
    }


def _simulator_state() -> dict[str, Any]:
    from app.industrial_gateway.opcua.service import get_mock_simulator

    simulator = get_mock_simulator()
    if simulator is None:
        return {"available": False, "scenario": None, "tick": None}
    return {"available": True, "scenario": simulator.scenario, "tick": simulator.tick}
