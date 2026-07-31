"""实时监测、异常诊断、预测维护、仿真与安全审批 API。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, supervisor_or_admin
from app.db.session import get_db
from app.gateways.equipment import EquipmentCommand, equipment_gateway
from app.models.base import RiskLevelEnum, WorkOrderStatusEnum
from app.models.equipment import Equipment
from app.models.intelligence import (
    AgentRun,
    AnomalyEvent,
    EquipmentSensor,
    FaultDiagnosis,
    MaintenanceRecommendation,
    MaintenanceVerification,
    OperationApproval,
    RiskPrediction,
    SparePartReservation,
    TelemetryRecord,
    ToolInvocation,
)
from app.models.user import User
from app.models.workorder import WorkOrder
from app.schemas.intelligence import (
    ApprovalCreate,
    ApprovalReview,
    SimulatorConfigureRequest,
    SimulatorStatusOut,
    SimulatorTickOut,
    TelemetryOut,
    VerificationCreate,
)
from app.services.intelligence_service import verify_maintenance
from app.services.simulator import simulator_controller

router = APIRouter(prefix="/intelligence", tags=["intelligent-maintenance"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), _=Depends(get_current_user)):
    equipment = db.query(Equipment).all()
    active_anomalies = (
        db.query(AnomalyEvent)
        .filter(AnomalyEvent.status.in_(["open", "acknowledged"]))
        .count()
    )
    pending_approvals = (
        db.query(OperationApproval)
        .filter(OperationApproval.status == "pending")
        .count()
    )
    predictions = (
        db.query(RiskPrediction)
        .order_by(RiskPrediction.created_at.desc())
        .limit(20)
        .all()
    )
    latest_telemetry = (
        db.query(TelemetryRecord)
        .order_by(TelemetryRecord.collected_at.desc())
        .limit(12)
        .all()
    )
    return {
        "total_equipment": len(equipment),
        "average_health_score": round(
            sum(item.health_score for item in equipment) / max(len(equipment), 1), 1
        ),
        "warning_equipment": sum(
            1
            for item in equipment
            if item.status.value in {"warning", "fault", "offline"}
        ),
        "high_risk_equipment": sum(
            1
            for item in equipment
            if item.risk_level in {RiskLevelEnum.high, RiskLevelEnum.critical}
        ),
        "active_anomalies": active_anomalies,
        "pending_approvals": pending_approvals,
        "health_distribution": [
            {
                "range": "healthy",
                "label": "健康",
                "count": sum(1 for item in equipment if item.health_score >= 85),
            },
            {
                "range": "attention",
                "label": "关注",
                "count": sum(1 for item in equipment if 70 <= item.health_score < 85),
            },
            {
                "range": "risk",
                "label": "风险",
                "count": sum(1 for item in equipment if item.health_score < 70),
            },
        ],
        "risk_predictions": [_prediction_dict(item, db) for item in predictions],
        "latest_telemetry": [_telemetry_summary(item, db) for item in latest_telemetry],
        "simulator": simulator_controller.status(),
    }


@router.get("/equipment/{equipment_id}")
def equipment_intelligence(
    equipment_id: int,
    limit: int = Query(default=60, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    equipment = db.get(Equipment, equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="设备不存在")
    telemetry = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.equipment_id == equipment_id)
        .order_by(TelemetryRecord.collected_at.desc())
        .limit(limit)
        .all()
    )
    sensors = (
        db.query(EquipmentSensor)
        .filter(EquipmentSensor.equipment_id == equipment_id)
        .order_by(EquipmentSensor.metric_type)
        .all()
    )
    anomalies = (
        db.query(AnomalyEvent)
        .filter(AnomalyEvent.equipment_id == equipment_id)
        .order_by(AnomalyEvent.detected_at.desc())
        .limit(20)
        .all()
    )
    recommendations = (
        db.query(MaintenanceRecommendation)
        .filter(MaintenanceRecommendation.equipment_id == equipment_id)
        .order_by(MaintenanceRecommendation.generated_at.desc())
        .limit(10)
        .all()
    )
    return {
        "equipment_id": equipment_id,
        "health_score": equipment.health_score,
        "risk_level": equipment.risk_level.value,
        "telemetry": [
            TelemetryOut.model_validate(item) for item in reversed(telemetry)
        ],
        "sensors": [
            {
                "id": item.id,
                "code": item.code,
                "name": item.name,
                "metric_type": item.metric_type,
                "unit": item.unit,
                "status": item.status,
                "latest_value": item.latest_value,
                "warning_min": item.warning_min,
                "warning_max": item.warning_max,
                "critical_min": item.critical_min,
                "critical_max": item.critical_max,
                "last_seen_at": item.last_seen_at,
            }
            for item in sensors
        ],
        "anomalies": [_anomaly_dict(item, db) for item in anomalies],
        "recommendations": [_recommendation_dict(item, db) for item in recommendations],
    }


@router.get("/telemetry/{equipment_id}", response_model=list[TelemetryOut])
def telemetry_history(
    equipment_id: int,
    limit: int = Query(default=120, ge=1, le=1000),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    if not db.get(Equipment, equipment_id):
        raise HTTPException(status_code=404, detail="设备不存在")
    items = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.equipment_id == equipment_id)
        .order_by(TelemetryRecord.collected_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(items))


@router.get("/anomalies")
def list_anomalies(
    status: str | None = None,
    severity: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(AnomalyEvent)
    if status:
        query = query.filter(AnomalyEvent.status == status)
    if severity:
        query = query.filter(AnomalyEvent.severity == severity)
    return [
        _anomaly_dict(item, db)
        for item in query.order_by(AnomalyEvent.detected_at.desc()).limit(limit).all()
    ]


@router.get("/predictions")
def list_predictions(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return [
        _prediction_dict(item, db)
        for item in db.query(RiskPrediction)
        .order_by(RiskPrediction.created_at.desc())
        .limit(limit)
        .all()
    ]


@router.get("/recommendations")
def list_recommendations(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return [
        _recommendation_dict(item, db)
        for item in db.query(MaintenanceRecommendation)
        .order_by(MaintenanceRecommendation.generated_at.desc())
        .limit(limit)
        .all()
    ]


@router.get("/diagnoses")
def list_diagnoses(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return [
        _diagnosis_dict(item, db)
        for item in db.query(FaultDiagnosis)
        .order_by(FaultDiagnosis.generated_at.desc())
        .limit(limit)
        .all()
    ]


@router.get("/agent-runs")
def list_agent_runs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(supervisor_or_admin),
):
    return [
        _agent_run_dict(item, db)
        for item in db.query(AgentRun)
        .order_by(AgentRun.started_at.desc())
        .limit(limit)
        .all()
    ]


@router.post("/simulator/configure", response_model=SimulatorStatusOut)
def configure_simulator(
    payload: SimulatorConfigureRequest,
    db: Session = Depends(get_db),
    _=Depends(supervisor_or_admin),
):
    try:
        simulator_controller.configure(
            db,
            equipment_ids=payload.equipment_ids,
            interval_seconds=payload.interval_seconds,
            scenario=payload.scenario,
            seed=payload.seed,
            auto_create_work_orders=payload.auto_create_work_orders,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return simulator_controller.status()


@router.post("/simulator/start", response_model=SimulatorStatusOut)
async def start_simulator(_=Depends(supervisor_or_admin)):
    try:
        simulator_controller.start()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return simulator_controller.status()


@router.post("/simulator/pause", response_model=SimulatorStatusOut)
def pause_simulator(_=Depends(supervisor_or_admin)):
    simulator_controller.pause()
    return simulator_controller.status()


@router.post("/simulator/reset", response_model=SimulatorStatusOut)
def reset_simulator(_=Depends(supervisor_or_admin)):
    simulator_controller.reset()
    return simulator_controller.status()


@router.post("/simulator/tick", response_model=SimulatorTickOut)
async def tick_simulator(db: Session = Depends(get_db), _=Depends(supervisor_or_admin)):
    return await simulator_controller.tick(db)


@router.get("/simulator/status", response_model=SimulatorStatusOut)
def simulator_status(_=Depends(get_current_user)):
    return simulator_controller.status()


@router.get("/approvals")
def list_approvals(
    status: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(OperationApproval)
    if status:
        query = query.filter(OperationApproval.status == status)
    return [
        _approval_dict(item, db)
        for item in query.order_by(OperationApproval.requested_at.desc()).all()
    ]


@router.post("/approvals")
def request_approval(
    payload: ApprovalCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not db.get(Equipment, payload.equipment_id):
        raise HTTPException(status_code=404, detail="设备不存在")
    existing = (
        db.query(OperationApproval)
        .filter(
            OperationApproval.equipment_id == payload.equipment_id,
            OperationApproval.work_order_id == payload.work_order_id,
            OperationApproval.command_type == payload.command_type,
            OperationApproval.status == "pending",
        )
        .first()
    )
    if existing:
        return _approval_dict(existing, db)
    approval = OperationApproval(
        **payload.model_dump(),
        status="pending",
        requested_by=user.id,
        requested_at=datetime.now(UTC),
        command_executed=False,
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return _approval_dict(approval, db)


@router.post("/approvals/{approval_id}/approve")
async def approve_operation(
    approval_id: int,
    payload: ApprovalReview,
    db: Session = Depends(get_db),
    user: User = Depends(supervisor_or_admin),
):
    approval = db.get(OperationApproval, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="审批记录不存在")
    if approval.status == "approved" and approval.command_executed:
        return _approval_dict(approval, db)
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail="该操作已完成审批")
    equipment = db.get(Equipment, approval.equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="设备不存在")

    # 高风险命令只在人工调用此审批接口后才进入 Equipment Gateway。
    result = await equipment_gateway.execute_command(
        EquipmentCommand(
            equipment_id=UUID(equipment.asset_uuid),
            command_type=approval.command_type,
            parameters=approval.command_payload or {},
        )
    )
    approval.status = "approved" if result.success else "execution_failed"
    approval.reviewed_by = user.id
    approval.reviewed_at = datetime.now(UTC)
    approval.review_note = payload.note
    approval.command_executed = result.success
    approval.command_result = result.to_dict()
    db.commit()
    db.refresh(approval)
    return _approval_dict(approval, db)


@router.post("/approvals/{approval_id}/reject")
def reject_operation(
    approval_id: int,
    payload: ApprovalReview,
    db: Session = Depends(get_db),
    user: User = Depends(supervisor_or_admin),
):
    approval = db.get(OperationApproval, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="审批记录不存在")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail="该操作已完成审批")
    approval.status = "rejected"
    approval.reviewed_by = user.id
    approval.reviewed_at = datetime.now(UTC)
    approval.review_note = payload.note
    approval.command_executed = False
    db.commit()
    db.refresh(approval)
    return _approval_dict(approval, db)


@router.post("/verifications")
def create_verification(
    payload: VerificationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(supervisor_or_admin),
):
    work_order = db.get(WorkOrder, payload.work_order_id)
    if not work_order:
        raise HTTPException(status_code=404, detail="工单不存在")
    if work_order.status not in {
        WorkOrderStatusEnum.completed,
        WorkOrderStatusEnum.pending_acceptance,
    }:
        raise HTTPException(status_code=409, detail="工单尚未进入验收或完成状态")
    if (
        db.query(MaintenanceVerification)
        .filter(MaintenanceVerification.work_order_id == work_order.id)
        .first()
    ):
        raise HTTPException(status_code=409, detail="该工单已完成维修效果验证")
    try:
        verification = verify_maintenance(
            db,
            work_order,
            verified_by=user.id,
            notes=payload.notes,
            create_knowledge_case=payload.create_knowledge_case,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": verification.id,
        "work_order_id": verification.work_order_id,
        "equipment_id": verification.equipment_id,
        "health_score_before": verification.health_score_before,
        "health_score_after": verification.health_score_after,
        "result": verification.result,
        "notes": verification.notes,
        "verified_at": verification.verified_at,
        "knowledge_article_id": verification.knowledge_article_id,
    }


def _telemetry_summary(item: TelemetryRecord, db: Session) -> dict:
    equipment = db.get(Equipment, item.equipment_id)
    return {
        "id": item.id,
        "equipment_id": item.equipment_id,
        "equipment_name": equipment.name if equipment else None,
        "equipment_code": equipment.code if equipment else None,
        "collected_at": item.collected_at,
        "vibration_rms": item.vibration_rms,
        "bearing_temperature": item.bearing_temperature,
        "motor_current": item.motor_current,
        "motor_voltage": item.motor_voltage,
        "load_ratio": item.load_ratio,
        "is_anomaly": item.is_anomaly,
        "quality": item.quality,
    }


def _anomaly_dict(item: AnomalyEvent, db: Session) -> dict:
    equipment = db.get(Equipment, item.equipment_id)
    diagnosis = (
        db.query(FaultDiagnosis)
        .filter(FaultDiagnosis.anomaly_event_id == item.id)
        .first()
    )
    return {
        "id": item.id,
        "equipment_id": item.equipment_id,
        "equipment_name": equipment.name if equipment else None,
        "equipment_code": equipment.code if equipment else None,
        "fault_type": item.fault_type,
        "title": item.title,
        "severity": item.severity.value,
        "status": item.status,
        "evidence": item.evidence,
        "diagnosis_summary": item.diagnosis_summary,
        "confidence": item.confidence,
        "diagnosis": _diagnosis_dict(diagnosis, db) if diagnosis else None,
        "detected_at": item.detected_at,
    }


def _prediction_dict(item: RiskPrediction, db: Session) -> dict:
    equipment = db.get(Equipment, item.equipment_id)
    return {
        "id": item.id,
        "equipment_id": item.equipment_id,
        "equipment_name": equipment.name if equipment else None,
        "equipment_code": equipment.code if equipment else None,
        "anomaly_event_id": item.anomaly_event_id,
        "risk_level": item.risk_level.value,
        "failure_mode": item.failure_mode,
        "probability": item.probability,
        "remaining_useful_life_hours": item.remaining_useful_life_hours,
        "predicted_failure_at": item.predicted_failure_at,
        "maintenance_window_start": item.maintenance_window_start,
        "maintenance_window_end": item.maintenance_window_end,
        "factors": item.factors,
        "model_version": item.model_version,
        "is_mock": item.is_mock,
    }


def _recommendation_dict(item: MaintenanceRecommendation, db: Session) -> dict:
    equipment = db.get(Equipment, item.equipment_id)
    reservations = (
        db.query(SparePartReservation)
        .filter(SparePartReservation.recommendation_id == item.id)
        .order_by(SparePartReservation.id)
        .all()
    )
    return {
        "id": item.id,
        "equipment_id": item.equipment_id,
        "equipment_name": equipment.name if equipment else None,
        "equipment_code": equipment.code if equipment else None,
        "prediction_id": item.prediction_id,
        "title": item.title,
        "strategy": item.strategy,
        "priority": item.priority,
        "required_skills": item.required_skills,
        "required_parts": item.required_parts,
        "risk_operations": item.risk_operations,
        "dispatch_suggestion": item.dispatch_suggestion,
        "status": item.status,
        "auto_work_order_id": item.auto_work_order_id,
        "part_reservations": [
            {
                "id": reservation.id,
                "spare_part_id": reservation.spare_part_id,
                "requested_name": reservation.requested_name,
                "requested_qty": reservation.requested_qty,
                "reserved_qty": reservation.reserved_qty,
                "shortage_qty": reservation.shortage_qty,
                "status": reservation.status,
            }
            for reservation in reservations
        ],
        "generated_at": item.generated_at,
    }


def _diagnosis_dict(item: FaultDiagnosis, db: Session) -> dict:
    equipment = db.get(Equipment, item.equipment_id)
    return {
        "id": item.id,
        "equipment_id": item.equipment_id,
        "equipment_name": equipment.name if equipment else None,
        "anomaly_event_id": item.anomaly_event_id,
        "fault_type": item.fault_type,
        "summary": item.summary,
        "possible_causes": item.possible_causes,
        "evidence": item.evidence,
        "rag_citations": item.rag_citations,
        "confidence": item.confidence,
        "requires_human_review": item.requires_human_review,
        "generated_at": item.generated_at,
    }


def _agent_run_dict(item: AgentRun, db: Session) -> dict:
    invocations = (
        db.query(ToolInvocation)
        .filter(ToolInvocation.agent_run_id == item.id)
        .order_by(ToolInvocation.id)
        .all()
    )
    return {
        "id": item.id,
        "equipment_id": item.equipment_id,
        "anomaly_event_id": item.anomaly_event_id,
        "goal": item.goal,
        "status": item.status,
        "provider": item.provider,
        "input": item.input,
        "output": item.output,
        "confidence": item.confidence,
        "requires_human_review": item.requires_human_review,
        "started_at": item.started_at,
        "finished_at": item.finished_at,
        "error": item.error,
        "tool_invocations": [
            {
                "id": invocation.id,
                "tool_name": invocation.tool_name,
                "provider": invocation.provider,
                "status": invocation.status,
                "request": invocation.request,
                "response": invocation.response,
                "duration_ms": invocation.duration_ms,
                "error": invocation.error,
            }
            for invocation in invocations
        ],
    }


def _approval_dict(item: OperationApproval, db: Session) -> dict:
    equipment = db.get(Equipment, item.equipment_id)
    requester = db.get(User, item.requested_by) if item.requested_by else None
    reviewer = db.get(User, item.reviewed_by) if item.reviewed_by else None
    return {
        "id": item.id,
        "equipment_id": item.equipment_id,
        "equipment_name": equipment.name if equipment else None,
        "equipment_code": equipment.code if equipment else None,
        "work_order_id": item.work_order_id,
        "recommendation_id": item.recommendation_id,
        "command_type": item.command_type,
        "command_payload": item.command_payload,
        "risk_level": item.risk_level.value,
        "risk_reason": item.risk_reason,
        "status": item.status,
        "requested_by_name": requester.full_name if requester else "Maintenance Agent",
        "reviewed_by_name": reviewer.full_name if reviewer else None,
        "requested_at": item.requested_at,
        "reviewed_at": item.reviewed_at,
        "review_note": item.review_note,
        "command_executed": item.command_executed,
        "command_result": item.command_result,
    }
