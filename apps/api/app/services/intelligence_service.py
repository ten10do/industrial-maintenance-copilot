"""从遥测到预测、维修策略、工单和知识沉淀的确定性闭环。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai.knowledge_search import search_articles
from app.core.trace import current_trace_id, start_trace
from app.gateways.equipment import TelemetrySnapshot
from app.gateways.notifications import notification_gateway
from app.models.base import (
    EquipmentStatusEnum,
    KnowledgeCategoryEnum,
    PriorityEnum,
    RiskLevelEnum,
    RoleEnum,
    WorkOrderStatusEnum,
    WorkOrderTypeEnum,
)
from app.models.equipment import Equipment, SparePart
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
from app.models.knowledge import KnowledgeArticle
from app.models.user import TechnicianProfile, User
from app.models.workorder import (
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderChecklistItem,
    WorkOrderStatusHistory,
)
from app.services.work_order_codes import generate_work_order_code


@dataclass(slots=True)
class TelemetryAssessment:
    is_anomaly: bool
    health_score: float
    risk_level: RiskLevelEnum
    fault_type: str | None
    title: str | None
    diagnosis: str | None
    confidence: float
    anomaly_metrics: list[str]
    evidence: dict[str, Any]


@dataclass(slots=True)
class IngestionResult:
    telemetry: TelemetryRecord
    anomaly: AnomalyEvent | None
    prediction: RiskPrediction | None
    recommendation: MaintenanceRecommendation | None
    work_order: WorkOrder | None


SCENARIO_FAULT_MAP = {
    "temperature_rise": ("bearing_overheat", "轴承温度持续升高"),
    "vibration_spike": ("rotor_unbalance", "振动突升，疑似转子不平衡"),
    "current_overload": ("motor_overload", "电机持续过载"),
    "bearing_wear": ("bearing_wear", "轴承磨损趋势"),
    "voltage_fluctuation": ("voltage_abnormal", "供电电压异常波动"),
    "sensor_disconnect": ("sensor_abnormal", "设备传感器数据中断"),
    "composite_anomaly": ("unknown_anomaly", "多指标复合异常"),
}

FAULT_GUIDANCE = {
    "bearing_wear": (
        "振动与温升趋势同时劣化，优先检查轴承游隙、滚道磨损和润滑状态。",
        "计划停机检查轴承；复测振动频谱，必要时更换轴承并校正润滑量。",
        ["机械维修", "仪表校准"],
        ["轴承", "润滑油"],
    ),
    "bearing_overheat": (
        "轴承温度超过运行阈值，可能由润滑不足、安装过紧或轴承磨损引起。",
        "降低负载并安排维护窗口；检查润滑、轴承游隙与冷却条件。",
        ["机械维修"],
        ["轴承", "润滑油"],
    ),
    "motor_overload": (
        "负载率或电流持续超限，存在绕组过热和保护跳闸风险。",
        "核对工艺负载与传动阻力；检查电流三相平衡，排除卡阻后再复机。",
        ["电气维修", "机械维修"],
        ["接触器", "轴承"],
    ),
    "rotor_unbalance": (
        "振动 RMS 突升且转速保持稳定，符合转子不平衡或部件松动特征。",
        "停机检查紧固、叶轮和联轴器；完成动平衡后进行空载及负载验证。",
        ["机械维修", "仪表校准"],
        ["轴承"],
    ),
    "shaft_misalignment": (
        "振动与电流共同升高，需排查联轴器和轴系不对中。",
        "执行 LOTO 后检查软脚与联轴器对中，校正后复测振动。",
        ["机械维修", "仪表校准"],
        ["联轴器"],
    ),
    "insufficient_lubrication": (
        "轴承温升伴随中度振动，润滑不足概率较高。",
        "确认润滑脂型号、加注周期和油路状态，按设备手册补充或更换。",
        ["机械维修"],
        ["润滑油"],
    ),
    "voltage_abnormal": (
        "电机端电压超出允许波动范围，可能造成电流异常和绝缘老化。",
        "由持证电工检查供电、接线和变频器输出；电压稳定后再恢复运行。",
        ["电气维修", "仪表校准"],
        ["接触器", "变频器"],
    ),
    "sensor_abnormal": (
        "遥测质量为零或关键指标缺失，无法可靠判断设备健康状态。",
        "检查传感器供电、接线与采集网关；修复前采用人工点检监护。",
        ["仪表校准", "电气维修"],
        ["传感器"],
    ),
    "unknown_anomaly": (
        "多个指标同时越限，规则模型无法唯一确定故障根因。",
        "进入受控停机与人工诊断流程，结合手册、频谱和历史案例逐项排查。",
        ["机械维修", "电气维修", "仪表校准"],
        ["轴承", "传感器"],
    ),
}

SENSOR_DEFINITIONS = {
    "vibration_rms": ("振动 RMS", "mm/s", None, 4.5, None, 7.1),
    "bearing_temperature": ("轴承温度", "°C", None, 75.0, None, 90.0),
    "motor_current": ("电机电流", "A", None, 27.0, None, 32.0),
    "motor_voltage": ("电机电压", "V", 342.0, 418.0, 320.0, 440.0),
    "rotational_speed": ("转速", "rpm", 1350.0, 1550.0, 1200.0, 1650.0),
    "load_ratio": ("负载率", "%", None, 100.0, None, 115.0),
    "ambient_temperature": ("环境温度", "°C", None, 40.0, None, 50.0),
    "cumulative_runtime_hours": ("累计运行时间", "h", None, None, None, None),
}


def assess_snapshot(snapshot: TelemetrySnapshot) -> TelemetryAssessment:
    values = {
        "振动 RMS": snapshot.vibration_rms,
        "轴承温度": snapshot.bearing_temperature,
        "电机电流": snapshot.motor_current,
        "电机电压": snapshot.motor_voltage,
        "负载率": snapshot.load_ratio,
    }
    anomaly_metrics: list[str] = []
    deductions = 0.0

    if snapshot.quality <= 0 or any(value is None for value in values.values()):
        anomaly_metrics.append("遥测质量")
        sensor_fault_type, sensor_title = SCENARIO_FAULT_MAP["sensor_disconnect"]
        return TelemetryAssessment(
            True,
            42.0,
            RiskLevelEnum.high,
            sensor_fault_type,
            sensor_title,
            FAULT_GUIDANCE[sensor_fault_type][0],
            0.99,
            anomaly_metrics,
            {"quality": snapshot.quality, **values},
        )

    assert snapshot.vibration_rms is not None
    assert snapshot.bearing_temperature is not None
    assert snapshot.motor_current is not None
    assert snapshot.motor_voltage is not None
    assert snapshot.load_ratio is not None

    if snapshot.vibration_rms > 4.5:
        anomaly_metrics.append("振动 RMS")
        deductions += min((snapshot.vibration_rms - 4.5) * 6, 32)
    if snapshot.bearing_temperature > 75:
        anomaly_metrics.append("轴承温度")
        deductions += min((snapshot.bearing_temperature - 75) * 2, 32)
    if snapshot.motor_current > 27:
        anomaly_metrics.append("电机电流")
        deductions += min((snapshot.motor_current - 27) * 2.5, 25)
    if snapshot.load_ratio > 100:
        anomaly_metrics.append("负载率")
        deductions += min((snapshot.load_ratio - 100) * 1.4, 25)
    if snapshot.motor_voltage < 342 or snapshot.motor_voltage > 418:
        anomaly_metrics.append("电机电压")
        deductions += min(abs(snapshot.motor_voltage - 380) * 0.8, 28)

    scenario_fault = SCENARIO_FAULT_MAP.get(snapshot.scenario)
    is_anomaly = bool(anomaly_metrics)
    fault_type: str | None = None
    title: str | None = None
    if is_anomaly and scenario_fault:
        fault_type, title = scenario_fault
    elif is_anomaly:
        if snapshot.motor_current > 27 or snapshot.load_ratio > 100:
            fault_type, title = "motor_overload", "电机负载与电流异常"
        elif snapshot.bearing_temperature > 75 and snapshot.vibration_rms > 4.5:
            fault_type, title = "bearing_wear", "轴承温振趋势异常"
        elif snapshot.bearing_temperature > 75:
            fault_type, title = "bearing_overheat", "轴承温度异常"
        elif snapshot.vibration_rms > 4.5:
            fault_type, title = "rotor_unbalance", "电机振动异常"
        else:
            fault_type, title = "voltage_abnormal", "电机电压异常"

    critical = (
        snapshot.bearing_temperature >= 90
        or snapshot.load_ratio >= 115
        or snapshot.motor_voltage <= 320
        or snapshot.motor_voltage >= 440
        or len(anomaly_metrics) >= 4
    )
    health_score = round(max(18.0, 100.0 - deductions), 1)
    if critical:
        risk = RiskLevelEnum.critical
    elif is_anomaly and (
        health_score < 70 or len(anomaly_metrics) >= 2 or snapshot.vibration_rms >= 7.1
    ):
        risk = RiskLevelEnum.high
    elif is_anomaly:
        risk = RiskLevelEnum.medium
    else:
        risk = RiskLevelEnum.low

    return TelemetryAssessment(
        is_anomaly,
        health_score,
        risk,
        fault_type,
        title,
        FAULT_GUIDANCE.get(fault_type or "", ("", "", [], []))[0] or None,
        0.9 if scenario_fault else 0.78,
        anomaly_metrics,
        values,
    )


def ingest_snapshot(
    db: Session,
    equipment: Equipment,
    snapshot: TelemetrySnapshot,
    *,
    auto_create_work_orders: bool = True,
) -> IngestionResult:
    # 工业事件入口：无既有链路时开启新 trace（网关同步/订阅 flush 已先行绑定，
    # 此处兜底覆盖手动遥测摄入等直接调用）。
    if current_trace_id() is None:
        start_trace("manual-telemetry-ingest")
    assessment = assess_snapshot(snapshot)
    telemetry = TelemetryRecord(
        equipment_id=equipment.id,
        collected_at=snapshot.collected_at,
        vibration_rms=snapshot.vibration_rms,
        bearing_temperature=snapshot.bearing_temperature,
        motor_current=snapshot.motor_current,
        motor_voltage=snapshot.motor_voltage,
        rotational_speed=snapshot.rotational_speed,
        load_ratio=snapshot.load_ratio,
        ambient_temperature=snapshot.ambient_temperature,
        cumulative_runtime_hours=snapshot.cumulative_runtime_hours,
        scenario=snapshot.scenario,
        quality=snapshot.quality,
        is_anomaly=assessment.is_anomaly,
        anomaly_metrics=assessment.anomaly_metrics,
        trace_id=current_trace_id(),
    )
    db.add(telemetry)
    db.flush()

    equipment.cumulative_runtime_hours = snapshot.cumulative_runtime_hours
    equipment.health_score = assessment.health_score
    equipment.risk_level = assessment.risk_level
    if snapshot.quality <= 0:
        equipment.status = EquipmentStatusEnum.offline
    elif assessment.risk_level == RiskLevelEnum.critical:
        equipment.status = EquipmentStatusEnum.fault
    elif assessment.is_anomaly:
        equipment.status = EquipmentStatusEnum.warning
    elif equipment.status not in {
        EquipmentStatusEnum.maintenance,
        EquipmentStatusEnum.under_repair,
        EquipmentStatusEnum.scrapped,
    }:
        equipment.status = EquipmentStatusEnum.running

    _update_sensors(db, equipment, snapshot)
    if not assessment.is_anomaly or not assessment.fault_type:
        db.commit()
        db.refresh(telemetry)
        return IngestionResult(telemetry, None, None, None, None)

    existing = (
        db.query(AnomalyEvent)
        .filter(
            AnomalyEvent.equipment_id == equipment.id,
            AnomalyEvent.fault_type == assessment.fault_type,
            AnomalyEvent.status.in_(["open", "acknowledged"]),
        )
        .first()
    )
    if existing:
        existing.telemetry_id = telemetry.id
        existing.evidence = assessment.evidence
        existing.severity = assessment.risk_level
        existing.diagnosis_summary = assessment.diagnosis
        existing.confidence = assessment.confidence
        existing_work_order_id = (
            db.query(MaintenanceRecommendation.auto_work_order_id)
            .join(
                RiskPrediction,
                MaintenanceRecommendation.prediction_id == RiskPrediction.id,
            )
            .filter(
                RiskPrediction.anomaly_event_id == existing.id,
                MaintenanceRecommendation.auto_work_order_id.is_not(None),
            )
            .scalar()
        )
        if (
            auto_create_work_orders
            and not existing_work_order_id
            and assessment.risk_level in {RiskLevelEnum.high, RiskLevelEnum.critical}
        ):
            escalation_run = AgentRun(
                equipment_id=equipment.id,
                anomaly_event_id=existing.id,
                goal="异常风险升级后生成预测性维护工单",
                status="running",
                provider="deterministic-mock",
                input={
                    "telemetry_id": telemetry.id,
                    "fault_type": assessment.fault_type,
                    "risk_level": assessment.risk_level.value,
                },
                confidence=assessment.confidence,
                requires_human_review=assessment.confidence < 0.8,
                started_at=datetime.now(UTC),
                trace_id=current_trace_id(),
            )
            db.add(escalation_run)
            db.flush()
            diagnosis = (
                db.query(FaultDiagnosis)
                .filter(FaultDiagnosis.anomaly_event_id == existing.id)
                .first()
            )
            if diagnosis:
                diagnosis.evidence = assessment.evidence
                diagnosis.confidence = assessment.confidence
                diagnosis.requires_human_review = assessment.confidence < 0.8
            prediction = _create_prediction(db, equipment, existing, assessment)
            recommendation = _create_recommendation(
                db, equipment, prediction, assessment
            )
            escalation_work_order = _create_predictive_work_order(
                db, equipment, existing, recommendation, assessment
            )
            recommendation.auto_work_order_id = escalation_work_order.id
            recommendation.status = "work_order_created"
            _reserve_parts(db, recommendation, escalation_work_order)
            _create_operation_approval(
                db, equipment, escalation_work_order, recommendation, assessment
            )
            _record_tool(
                db,
                escalation_run,
                "work_order_creator",
                {"anomaly_event_id": existing.id, "risk_escalation": True},
                {"work_order_id": escalation_work_order.id},
            )
            escalation_run.status = "completed"
            escalation_run.output = {
                "prediction_id": prediction.id,
                "recommendation_id": recommendation.id,
                "work_order_id": escalation_work_order.id,
            }
            escalation_run.finished_at = datetime.now(UTC)
            db.commit()
            for entity in (
                telemetry,
                existing,
                prediction,
                recommendation,
                escalation_work_order,
            ):
                db.refresh(entity)
            return IngestionResult(
                telemetry,
                existing,
                prediction,
                recommendation,
                escalation_work_order,
            )
        db.commit()
        db.refresh(telemetry)
        return IngestionResult(telemetry, existing, None, None, None)

    anomaly = AnomalyEvent(
        equipment_id=equipment.id,
        telemetry_id=telemetry.id,
        fault_type=assessment.fault_type,
        title=assessment.title or "设备异常",
        severity=assessment.risk_level,
        evidence=assessment.evidence,
        diagnosis_summary=assessment.diagnosis,
        confidence=assessment.confidence,
        detected_at=snapshot.collected_at,
        trace_id=current_trace_id(),
    )
    db.add(anomaly)
    db.flush()

    agent_run = AgentRun(
        equipment_id=equipment.id,
        anomaly_event_id=anomaly.id,
        goal="诊断设备异常并生成预测性维护策略",
        status="running",
        provider="deterministic-mock",
        input={
            "telemetry_id": telemetry.id,
            "fault_type": assessment.fault_type,
            "evidence": assessment.evidence,
        },
        confidence=assessment.confidence,
        requires_human_review=assessment.confidence < 0.8,
        started_at=datetime.now(UTC),
        trace_id=current_trace_id(),
    )
    db.add(agent_run)
    db.flush()
    _record_tool(
        db,
        agent_run,
        "anomaly_detector",
        {"telemetry_id": telemetry.id},
        {
            "is_anomaly": True,
            "fault_type": assessment.fault_type,
            "health_score": assessment.health_score,
        },
    )
    diagnosis = _create_diagnosis(db, equipment, anomaly, assessment, agent_run)
    prediction = _create_prediction(db, equipment, anomaly, assessment)
    _record_tool(
        db,
        agent_run,
        "risk_predictor",
        {"anomaly_event_id": anomaly.id},
        {
            "risk_level": prediction.risk_level.value,
            "probability": prediction.probability,
            "remaining_useful_life_hours": prediction.remaining_useful_life_hours,
        },
    )
    recommendation = _create_recommendation(db, equipment, prediction, assessment)
    _record_tool(
        db,
        agent_run,
        "maintenance_strategy",
        {"prediction_id": prediction.id},
        {
            "recommendation_id": recommendation.id,
            "priority": recommendation.priority,
        },
    )
    work_order = None
    if auto_create_work_orders and assessment.risk_level in {
        RiskLevelEnum.high,
        RiskLevelEnum.critical,
    }:
        work_order = _create_predictive_work_order(
            db, equipment, anomaly, recommendation, assessment
        )
        recommendation.auto_work_order_id = work_order.id
        recommendation.status = "work_order_created"
        _reserve_parts(db, recommendation, work_order)
        _create_operation_approval(
            db, equipment, work_order, recommendation, assessment
        )
        _record_tool(
            db,
            agent_run,
            "work_order_creator",
            {"recommendation_id": recommendation.id},
            {"work_order_id": work_order.id, "status": work_order.status.value},
        )

    agent_run.status = "completed"
    agent_run.output = {
        "diagnosis_id": diagnosis.id,
        "prediction_id": prediction.id,
        "recommendation_id": recommendation.id,
        "work_order_id": work_order.id if work_order else None,
    }
    agent_run.finished_at = datetime.now(UTC)

    for supervisor in (
        db.query(User)
        .filter(
            User.role.in_([RoleEnum.supervisor, RoleEnum.admin]),
            User.is_active.is_(True),
        )
        .all()
    ):
        notification_gateway.send(
            db,
            user_id=supervisor.id,
            title=f"{equipment.name} 检测到{anomaly.title}",
            content=f"风险等级：{assessment.risk_level.value}；健康分：{assessment.health_score}",
            level="warning",
            link=f"/equipment/{equipment.id}",
        )

    db.commit()
    for entity in (telemetry, anomaly, prediction, recommendation):
        db.refresh(entity)
    if work_order:
        db.refresh(work_order)
    return IngestionResult(telemetry, anomaly, prediction, recommendation, work_order)


def verify_maintenance(
    db: Session,
    work_order: WorkOrder,
    *,
    verified_by: int | None,
    notes: str | None,
    create_knowledge_case: bool,
) -> MaintenanceVerification:
    if not work_order.equipment_id:
        raise ValueError("工单未关联设备")
    latest = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.equipment_id == work_order.equipment_id)
        .order_by(TelemetryRecord.collected_at.desc())
        .first()
    )
    before = (
        db.query(TelemetryRecord)
        .join(AnomalyEvent, AnomalyEvent.telemetry_id == TelemetryRecord.id)
        .filter(
            AnomalyEvent.equipment_id == work_order.equipment_id,
        )
        .order_by(AnomalyEvent.detected_at.desc())
        .first()
    )
    equipment = db.get(Equipment, work_order.equipment_id)
    if not equipment or not latest:
        raise ValueError("缺少设备或维修后遥测数据")

    before_score = _record_health_score(before) if before else 50.0
    after_score = _record_health_score(latest)
    result = "passed" if after_score >= 80 and not latest.is_anomaly else "failed"
    previous_status = work_order.status
    now = datetime.now(UTC)
    verification = MaintenanceVerification(
        work_order_id=work_order.id,
        equipment_id=equipment.id,
        health_score_before=before_score,
        health_score_after=after_score,
        telemetry_before=_telemetry_dict(before),
        telemetry_after=_telemetry_dict(latest),
        result=result,
        notes=notes,
        verified_by=verified_by,
        verified_at=now,
    )
    db.add(verification)
    if result == "passed":
        equipment.health_score = after_score
        equipment.risk_level = RiskLevelEnum.low
        equipment.status = EquipmentStatusEnum.running
        equipment.last_maintenance_at = now.date()
        equipment.next_maintenance_at = (now + timedelta(days=90)).date()
        work_order.status = WorkOrderStatusEnum.completed
        work_order.actual_end_at = now
        work_order.needs_observation = False
        for event in (
            db.query(AnomalyEvent)
            .filter(
                AnomalyEvent.equipment_id == equipment.id,
                AnomalyEvent.status.in_(["open", "acknowledged"]),
            )
            .all()
        ):
            event.status = "resolved"
            event.resolved_at = now
    else:
        work_order.status = WorkOrderStatusEnum.returned
        work_order.actual_end_at = None
        work_order.needs_observation = True
        work_order.rejection_reason = (
            "维修后遥测仍异常或健康分未达到 80，已自动退回重新处理。"
        )

    if work_order.status != previous_status:
        db.add(
            WorkOrderStatusHistory(
                work_order_id=work_order.id,
                from_status=previous_status.value,
                to_status=work_order.status.value,
                changed_by=verified_by,
                changed_at=now,
                remark="维修效果验证通过，自动关闭工单"
                if result == "passed"
                else "维修效果验证失败，自动重新打开工单",
            )
        )

    if create_knowledge_case:
        article = KnowledgeArticle(
            title=f"[待审核] {equipment.name} {work_order.title}维修验证案例",
            category=KnowledgeCategoryEnum.case,
            content=(
                f"工单 {work_order.code}。根因：{work_order.root_cause or '待补充'}。"
                f"措施：{work_order.action_taken or '按工单执行'}。"
                f"健康分由 {before_score} 变为 {after_score}，验证结果：{result}。"
            ),
            summary=f"维修效果验证：{before_score} → {after_score}",
            tags=["预测性维护", "维修验证", "待人工审核", equipment.code],
            equipment_type_id=equipment.equipment_type_id,
            source="维修闭环自动生成，需人工审核",
            author_id=verified_by,
            status="draft",
            created_by=str(verified_by) if verified_by else "system",
        )
        db.add(article)
        db.flush()
        verification.knowledge_article_id = article.id
    db.commit()
    db.refresh(verification)
    return verification


def _create_diagnosis(
    db: Session,
    equipment: Equipment,
    anomaly: AnomalyEvent,
    assessment: TelemetryAssessment,
    agent_run: AgentRun,
) -> FaultDiagnosis:
    query = " ".join(
        filter(
            None,
            [
                equipment.name,
                assessment.title,
                assessment.diagnosis,
                " ".join(assessment.anomaly_metrics),
            ],
        )
    )
    results = search_articles(
        db,
        query,
        equipment_type_id=equipment.equipment_type_id,
        limit=3,
    )
    citations = [
        {
            "article_id": item["article_id"],
            "title": item["title"],
            "source": item["source"],
            "score": item["score"],
        }
        for item in results
    ]
    _record_tool(
        db,
        agent_run,
        "knowledge_search",
        {"query": query, "limit": 3},
        {"citations": citations},
    )
    guidance = FAULT_GUIDANCE.get(
        assessment.fault_type or "unknown_anomaly",
        FAULT_GUIDANCE["unknown_anomaly"],
    )
    diagnosis = FaultDiagnosis(
        equipment_id=equipment.id,
        anomaly_event_id=anomaly.id,
        fault_type=assessment.fault_type or "unknown_anomaly",
        summary=assessment.diagnosis or guidance[0],
        possible_causes=_possible_causes(assessment.fault_type),
        evidence=assessment.evidence,
        rag_citations=citations,
        confidence=assessment.confidence,
        requires_human_review=assessment.confidence < 0.8,
        generated_at=datetime.now(UTC),
    )
    db.add(diagnosis)
    db.flush()
    return diagnosis


def _possible_causes(fault_type: str | None) -> list[str]:
    return {
        "bearing_wear": ["滚道或滚动体磨损", "润滑退化", "轴承游隙异常"],
        "bearing_overheat": ["润滑不足", "安装过紧", "冷却条件恶化"],
        "motor_overload": ["工艺负载过高", "传动卡阻", "三相电流不平衡"],
        "rotor_unbalance": ["转子积垢或损伤", "紧固件松动", "动平衡失效"],
        "shaft_misalignment": ["联轴器偏移", "软脚", "基础松动"],
        "insufficient_lubrication": ["加注周期超期", "油路堵塞", "润滑剂型号不符"],
        "voltage_abnormal": ["供电波动", "接线松动", "变频器输出异常"],
        "sensor_abnormal": ["传感器断电", "采集网关断连", "线路故障"],
        "unknown_anomaly": ["复合机械故障", "电气与负载耦合异常", "数据质量异常"],
    }.get(fault_type or "unknown_anomaly", ["需要人工进一步排查"])


def _record_tool(
    db: Session,
    agent_run: AgentRun,
    tool_name: str,
    request: dict[str, Any],
    response: dict[str, Any],
) -> None:
    db.add(
        ToolInvocation(
            agent_run_id=agent_run.id,
            tool_name=tool_name,
            provider="local",
            status="success",
            request=request,
            response=response,
            duration_ms=0,
        )
    )


def _update_sensors(
    db: Session, equipment: Equipment, snapshot: TelemetrySnapshot
) -> None:
    for metric, definition in SENSOR_DEFINITIONS.items():
        name, unit, warning_min, warning_max, critical_min, critical_max = definition
        sensor = (
            db.query(EquipmentSensor)
            .filter(
                EquipmentSensor.equipment_id == equipment.id,
                EquipmentSensor.metric_type == metric,
            )
            .first()
        )
        if not sensor:
            sensor = EquipmentSensor(
                equipment_id=equipment.id,
                code=f"{equipment.code}-{metric.upper()}",
                name=name,
                metric_type=metric,
                unit=unit,
                warning_min=warning_min,
                warning_max=warning_max,
                critical_min=critical_min,
                critical_max=critical_max,
            )
            db.add(sensor)
        sensor.latest_value = getattr(snapshot, metric)
        sensor.status = "offline" if snapshot.quality <= 0 else "online"
        sensor.last_seen_at = snapshot.collected_at


def _create_prediction(
    db: Session,
    equipment: Equipment,
    anomaly: AnomalyEvent,
    assessment: TelemetryAssessment,
) -> RiskPrediction:
    now = datetime.now(UTC)
    probability = {
        RiskLevelEnum.critical: 0.94,
        RiskLevelEnum.high: 0.82,
        RiskLevelEnum.medium: 0.58,
        RiskLevelEnum.low: 0.2,
    }[assessment.risk_level]
    remaining_hours = {
        RiskLevelEnum.critical: 8.0,
        RiskLevelEnum.high: 36.0,
        RiskLevelEnum.medium: 168.0,
        RiskLevelEnum.low: 720.0,
    }[assessment.risk_level]
    maintenance_window_end = now + timedelta(hours=max(2.0, remaining_hours * 0.5))
    prediction = RiskPrediction(
        equipment_id=equipment.id,
        anomaly_event_id=anomaly.id,
        risk_level=assessment.risk_level,
        failure_mode=assessment.fault_type or "unknown_anomaly",
        probability=probability,
        remaining_useful_life_hours=remaining_hours,
        predicted_failure_at=now + timedelta(hours=remaining_hours),
        maintenance_window_start=now,
        maintenance_window_end=maintenance_window_end,
        factors=assessment.anomaly_metrics,
        is_mock=True,
        trace_id=current_trace_id(),
    )
    equipment.next_maintenance_at = maintenance_window_end.date()
    db.add(prediction)
    db.flush()
    return prediction


def _create_recommendation(
    db: Session,
    equipment: Equipment,
    prediction: RiskPrediction,
    assessment: TelemetryAssessment,
) -> MaintenanceRecommendation:
    _, strategy, required_skills, required_parts = FAULT_GUIDANCE.get(
        assessment.fault_type or "unknown_anomaly",
        FAULT_GUIDANCE["unknown_anomaly"],
    )
    priority = {
        RiskLevelEnum.critical: "P1",
        RiskLevelEnum.high: "P2",
        RiskLevelEnum.medium: "P3",
        RiskLevelEnum.low: "P4",
    }[assessment.risk_level]
    dispatch = _dispatch_suggestion(db, required_skills, required_parts)
    recommendation = MaintenanceRecommendation(
        equipment_id=equipment.id,
        prediction_id=prediction.id,
        title=f"{equipment.name}：{assessment.title}",
        strategy=strategy,
        priority=priority,
        required_skills=required_skills,
        required_parts=dispatch["parts"],
        risk_operations=["shutdown", "reset_alarm", "restart"],
        dispatch_suggestion=dispatch,
        generated_at=datetime.now(UTC),
        trace_id=current_trace_id(),
    )
    db.add(recommendation)
    db.flush()
    return recommendation


def _dispatch_suggestion(
    db: Session, required_skills: list[str], required_parts: list[str]
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for profile in db.query(TechnicianProfile).all():
        user = db.get(User, profile.user_id)
        if not user or not user.is_active:
            continue
        skills = [skill.name for skill in profile.skills]
        active_orders = (
            db.query(WorkOrder)
            .filter(
                WorkOrder.assignee_id == user.id,
                WorkOrder.status.notin_(
                    [WorkOrderStatusEnum.completed, WorkOrderStatusEnum.cancelled]
                ),
            )
            .count()
        )
        match_count = len(set(skills) & set(required_skills))
        candidates.append(
            {
                "user_id": user.id,
                "name": user.full_name,
                "availability": profile.availability,
                "active_orders": active_orders,
                "matched_skills": match_count,
                "score": match_count * 20 - active_orders * 3,
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)

    parts: list[dict[str, Any]] = []
    for keyword in required_parts:
        part = db.query(SparePart).filter(SparePart.name.contains(keyword)).first()
        parts.append(
            {
                "name": keyword,
                "spare_part_id": part.id if part else None,
                "stock_qty": part.stock_qty if part else 0,
                "available": bool(part and part.stock_qty > 0),
            }
        )
    return {
        "technicians": candidates[:3],
        "recommended_technician_id": candidates[0]["user_id"] if candidates else None,
        "parts": parts,
    }


def _reserve_parts(
    db: Session,
    recommendation: MaintenanceRecommendation,
    work_order: WorkOrder,
) -> None:
    reservation_summaries: list[dict[str, Any]] = []
    for required in recommendation.required_parts or []:
        spare_part_id = required.get("spare_part_id")
        part = db.get(SparePart, spare_part_id) if spare_part_id else None
        already_reserved = 0
        if part:
            already_reserved = int(
                db.query(func.coalesce(func.sum(SparePartReservation.reserved_qty), 0))
                .filter(
                    SparePartReservation.spare_part_id == part.id,
                    SparePartReservation.status == "reserved",
                )
                .scalar()
                or 0
            )
        available_qty = max((part.stock_qty if part else 0) - already_reserved, 0)
        reserved_qty = min(available_qty, 1)
        shortage_qty = 1 - reserved_qty
        status = (
            "reserved" if reserved_qty == 1 else ("shortage" if part else "unavailable")
        )
        reservation = SparePartReservation(
            recommendation_id=recommendation.id,
            work_order_id=work_order.id,
            spare_part_id=part.id if part else None,
            requested_name=str(required["name"]),
            requested_qty=1,
            reserved_qty=reserved_qty,
            shortage_qty=shortage_qty,
            status=status,
            reserved_at=datetime.now(UTC) if reserved_qty else None,
        )
        db.add(reservation)
        reservation_summaries.append(
            {
                **required,
                "requested_qty": 1,
                "reserved_qty": reserved_qty,
                "shortage_qty": shortage_qty,
                "reservation_status": status,
            }
        )
    recommendation.required_parts = reservation_summaries
    dispatch = dict(recommendation.dispatch_suggestion or {})
    dispatch["parts"] = reservation_summaries
    dispatch["parts_ready"] = all(
        item["reservation_status"] == "reserved" for item in reservation_summaries
    )
    recommendation.dispatch_suggestion = dispatch


def _create_predictive_work_order(
    db: Session,
    equipment: Equipment,
    anomaly: AnomalyEvent,
    recommendation: MaintenanceRecommendation,
    assessment: TelemetryAssessment,
) -> WorkOrder:
    assignee_id = (recommendation.dispatch_suggestion or {}).get(
        "recommended_technician_id"
    )
    priority = PriorityEnum(recommendation.priority)
    status = (
        WorkOrderStatusEnum.assigned
        if assignee_id
        else WorkOrderStatusEnum.pending_dispatch
    )
    prediction = (
        db.get(RiskPrediction, recommendation.prediction_id)
        if recommendation.prediction_id
        else None
    )
    planned_end_at = (
        prediction.maintenance_window_end
        if prediction and prediction.maintenance_window_end
        else datetime.now(UTC) + timedelta(hours=8)
    )
    work_order = WorkOrder(
        code=generate_work_order_code(),
        title=f"[预测性维护] {anomaly.title}",
        equipment_id=equipment.id,
        fault_description=(
            f"系统由遥测异常自动创建。诊断：{assessment.diagnosis}；"
            f"证据：{', '.join(assessment.anomaly_metrics)}。"
        ),
        order_type=WorkOrderTypeEnum.preventive,
        priority=priority,
        status=status,
        assignee_id=assignee_id,
        planned_start_at=datetime.now(UTC),
        planned_end_at=planned_end_at,
        safety_risk="涉及旋转机械与电气能源，必须执行停机、断电、验电和 LOTO。",
        ai_diagnosis_summary=assessment.diagnosis,
        maintenance_steps=[
            "确认设备状态与异常遥测",
            "执行停机、断电、验电和 LOTO",
            recommendation.strategy,
            "完成空载和负载测试",
            "采集维修后遥测并验证健康分",
        ],
        acceptance_criteria="异常指标恢复阈值内，健康分不低于 80，空载与负载测试通过。",
        created_by="maintenance-agent",
        trace_id=current_trace_id(),
    )
    db.add(work_order)
    db.flush()

    db.add(
        WorkOrderStatusHistory(
            work_order_id=work_order.id,
            from_status=None,
            to_status=status.value,
            changed_by=None,
            changed_at=datetime.now(UTC),
            remark=f"由异常事件 #{anomaly.id} 自动创建",
        )
    )
    if assignee_id:
        db.add(
            WorkOrderAssignment(
                work_order_id=work_order.id,
                assignee_id=assignee_id,
                assigned_by=None,
                assigned_at=datetime.now(UTC),
                is_current=True,
            )
        )
    checklist = [
        ("safety", "设备已停机并执行 LOTO", 1),
        ("diagnosis", "复核遥测异常与故障诊断", 2),
        ("repair", recommendation.strategy, 3),
        ("testing", "采集维修后遥测并验证健康分", 4),
    ]
    for category, content, order in checklist:
        db.add(
            WorkOrderChecklistItem(
                work_order_id=work_order.id,
                category=category,
                content=content,
                order=order,
                is_required=True,
                created_by="maintenance-agent",
            )
        )
    return work_order


def _create_operation_approval(
    db: Session,
    equipment: Equipment,
    work_order: WorkOrder,
    recommendation: MaintenanceRecommendation,
    assessment: TelemetryAssessment,
) -> None:
    db.add(
        OperationApproval(
            equipment_id=equipment.id,
            work_order_id=work_order.id,
            recommendation_id=recommendation.id,
            command_type="shutdown",
            command_payload={"reason": anomaly_reason(assessment)},
            risk_level=assessment.risk_level,
            risk_reason="设备停机影响产线，且涉及旋转机械与电气能源隔离，必须人工审批。",
            status="pending",
            requested_by=None,
            requested_at=datetime.now(UTC),
            trace_id=current_trace_id(),
        )
    )


def anomaly_reason(assessment: TelemetryAssessment) -> str:
    return f"{assessment.title or '设备异常'}：{', '.join(assessment.anomaly_metrics)}"


def _record_health_score(record: TelemetryRecord | None) -> float:
    if not record:
        return 50.0
    snapshot = TelemetrySnapshot(
        equipment_id=__import__("uuid").UUID(int=record.equipment_id),
        collected_at=record.collected_at,
        vibration_rms=record.vibration_rms,
        bearing_temperature=record.bearing_temperature,
        motor_current=record.motor_current,
        motor_voltage=record.motor_voltage,
        rotational_speed=record.rotational_speed,
        load_ratio=record.load_ratio,
        ambient_temperature=record.ambient_temperature,
        cumulative_runtime_hours=record.cumulative_runtime_hours,
        scenario=record.scenario,
        quality=record.quality,
    )
    return assess_snapshot(snapshot).health_score


def _telemetry_dict(record: TelemetryRecord | None) -> dict[str, Any] | None:
    if not record:
        return None
    return {
        "id": record.id,
        "collected_at": record.collected_at.isoformat(),
        "vibration_rms": record.vibration_rms,
        "bearing_temperature": record.bearing_temperature,
        "motor_current": record.motor_current,
        "motor_voltage": record.motor_voltage,
        "rotational_speed": record.rotational_speed,
        "load_ratio": record.load_ratio,
        "ambient_temperature": record.ambient_temperature,
        "quality": record.quality,
        "is_anomaly": record.is_anomaly,
    }
