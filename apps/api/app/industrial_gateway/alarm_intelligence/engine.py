"""Alarm Understanding 与 Root Cause Analysis（确定性规则 + 既有知识检索）。

定位：**AI-assisted industrial alarm analysis**。

- 理解：把阈值式报警消息归纳为结构化语义（越限指标、触发规则、严重度）；
- 根因分析：结合最新遥测证据、平台既有故障处置知识（``FAULT_GUIDANCE``，
  只读复用）与知识库检索（``search_articles``，RAG 关键词基线），
  给出**根因假设**与证据链；
- 全部为确定性规则，不修改、不替代任何 ML 模型与 Agent 决策逻辑；
- 输出仅为分析结论，不执行任何操作。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from sqlalchemy.orm import Session

from app.ai.knowledge_search import search_articles
from app.models.base import RiskLevelEnum
from app.models.intelligence import TelemetryRecord
from app.services.intelligence_service import FAULT_GUIDANCE

MODEL_VERSION: Final = "deterministic-rules-v1"

# 平台警告阈值（与 intelligence_service.SENSOR_DEFINITIONS / alarms.py 对齐）。
WARNING_THRESHOLDS: Final[dict[str, float]] = {
    "bearing_temperature": 75.0,
    "vibration_rms": 4.5,
    "motor_current": 27.0,
    "load_ratio": 100.0,
}
VOLTAGE_RANGE: Final[tuple[float, float]] = (342.0, 418.0)

METRIC_LABELS: Final[dict[str, str]] = {
    "bearing_temperature": "轴承温度",
    "vibration_rms": "振动 RMS",
    "motor_current": "电机电流",
    "motor_voltage": "电机电压",
    "load_ratio": "负载率",
}

# 指标 → 根因假设（分析层本地映射；只读引用 FAULT_GUIDANCE 的处置知识）。
METRIC_FAULT_HYPOTHESIS: Final[dict[str, str]] = {
    "bearing_temperature": "bearing_overheat",
    "vibration_rms": "rotor_unbalance",
    "motor_current": "motor_overload",
    "load_ratio": "motor_overload",
    "motor_voltage": "voltage_abnormal",
}


def latest_telemetry_fields(
    db: Session, equipment_id: int
) -> tuple[dict[str, float | bool | None], int | None]:
    """读取该设备最新一条遥测的评估字段（供证据链使用）。"""
    record = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.equipment_id == equipment_id)
        .order_by(TelemetryRecord.collected_at.desc())
        .first()
    )
    if record is None:
        return {}, None
    fields: dict[str, float | bool | None] = {
        "bearing_temperature": record.bearing_temperature,
        "vibration_rms": record.vibration_rms,
        "motor_current": record.motor_current,
        "motor_voltage": record.motor_voltage,
        "load_ratio": record.load_ratio,
    }
    return fields, record.id


def _abnormal_metrics(
    telemetry_fields: dict[str, float | bool | None],
) -> list[dict[str, Any]]:
    """返回越限指标明细（按越限比例降序）。"""
    result: list[dict[str, Any]] = []
    for metric, threshold in WARNING_THRESHOLDS.items():
        value = telemetry_fields.get(metric)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if float(value) > threshold:
            result.append(
                {
                    "metric": metric,
                    "label": METRIC_LABELS[metric],
                    "value": round(float(value), 2),
                    "threshold": threshold,
                    "ratio": round(float(value) / threshold, 3),
                    "state": "above_upper",
                }
            )
    voltage = telemetry_fields.get("motor_voltage")
    if isinstance(voltage, (int, float)) and not isinstance(voltage, bool):
        low, high = VOLTAGE_RANGE
        if not (low <= float(voltage) <= high):
            result.append(
                {
                    "metric": "motor_voltage",
                    "label": METRIC_LABELS["motor_voltage"],
                    "value": round(float(voltage), 2),
                    "threshold": f"{low}-{high}",
                    "ratio": round(float(voltage) / high, 3),
                    "state": "voltage_out_of_range",
                }
            )
    result.sort(key=lambda item: item["ratio"], reverse=True)
    return result


@dataclass(slots=True)
class AlarmUnderstanding:
    """报警理解结果：结构化语义归纳。"""

    summary: str
    severity: str
    abnormal_metrics: list[dict[str, Any]] = field(default_factory=list)
    triggered_rules: list[str] = field(default_factory=list)


def understand_alarm(
    *,
    severity: str,
    message: str,
    telemetry_fields: dict[str, float | bool | None],
) -> AlarmUnderstanding:
    """把报警与遥测证据归纳为结构化理解。"""
    abnormal = _abnormal_metrics(telemetry_fields)
    rules = [f"{item['label']}>{item['threshold']}" for item in abnormal]
    if severity == "CRITICAL":
        rules.insert(0, "Alarm 位已置位")
    parts = [f"{item['label']}={item['value']}" for item in abnormal]
    summary = (
        f"{severity} 级工业报警："
        + ("、".join(parts) if parts else "指标未见明显越限（可能由报警位或瞬态触发）")
        + f"。原始信息：{message}"
    )
    return AlarmUnderstanding(
        summary=summary,
        severity=severity,
        abnormal_metrics=abnormal,
        triggered_rules=rules,
    )


@dataclass(slots=True)
class RootCauseAnalysisResult:
    """根因分析结果：假设 + 证据链 + 知识引用。"""

    hypothesis: str
    fault_type: str | None
    contributing_factors: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    citations: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5
    confidence_factors: list[str] = field(default_factory=list)
    evidence_conflicts: list[str] = field(default_factory=list)


def analyze_root_cause(
    db: Session,
    *,
    severity: str,
    message: str,
    telemetry_fields: dict[str, float | bool | None],
    telemetry_record_id: int | None,
    equipment_name: str,
    equipment_type_id: int | None = None,
    prediction_context: dict[str, Any] | None = None,
) -> RootCauseAnalysisResult:
    """给出根因假设与证据链（确定性规则 + 只读知识检索）。"""
    abnormal = _abnormal_metrics(telemetry_fields)
    contributing = [
        f"{item['label']}={item['value']}（阈值 {item['threshold']}）"
        for item in abnormal
    ]
    contributing.append(f"报警信息：{message}")

    fault_type: str | None = None
    if abnormal:
        fault_type = METRIC_FAULT_HYPOTHESIS.get(abnormal[0]["metric"])
    elif severity == "CRITICAL":
        fault_type = None

    guidance = FAULT_GUIDANCE.get(fault_type or "", None)
    if guidance and fault_type:
        cause_text = guidance[0]
        hypothesis = f"根因假设（{fault_type}）：{cause_text}"
    elif abnormal:
        hypothesis = (
            "根因假设：多信号复合或瞬态触发，规则层无法唯一确定根因；"
            "建议结合频谱/趋势与现场点检进一步确认。"
        )
    else:
        hypothesis = (
            "insufficient_evidence / manual_review_required：当前没有可验证的"
            "遥测越限或知识证据，不能给出高置信度根因。"
        )

    evidence: dict[str, Any] = {
        "severity": severity,
        "equipment": equipment_name,
        "telemetry_record_id": telemetry_record_id,
        "telemetry_fields": {key: value for key, value in telemetry_fields.items()},
        "abnormal_metrics": abnormal,
        "prediction_context": prediction_context,
    }

    citations: list[dict[str, Any]] = []
    query_parts = [equipment_name]
    if fault_type:
        query_parts.append(fault_type.replace("_", " "))
    for item in abnormal:
        query_parts.append(str(item["label"]))
    try:
        articles = search_articles(
            db,
            query=" ".join(query_parts),
            equipment_type_id=equipment_type_id,
            limit=3,
        )
    except Exception:  # pragma: no cover - 知识库不可用时降级为空引用
        articles = []
    for article in articles:
        content = str(article.get("summary") or article.get("content") or "")
        citations.append(
            {
                "article_id": article.get("article_id"),
                "document_id": article.get("article_id"),
                "title": article.get("title"),
                "source": article.get("source") or article.get("category"),
                "section": None,
                "snippet": content[:240],
                "score": article.get("score"),
            }
        )

    confidence = 0.0
    confidence_factors: list[str] = []
    conflicts: list[str] = []
    if abnormal:
        confidence += 0.35
        confidence_factors.append("telemetry_threshold_evidence:+0.35")
    if len(abnormal) >= 2:
        confidence += 0.1
        confidence_factors.append("multiple_consistent_signals:+0.10")
    if fault_type is not None and guidance:
        confidence += 0.2
        confidence_factors.append("deterministic_guidance_match:+0.20")
    if citations:
        confidence += 0.15
        confidence_factors.append("rag_evidence:+0.15")
    if prediction_context:
        predicted_mode = str(prediction_context.get("failure_mode") or "")
        probability = float(prediction_context.get("probability") or 0.0)
        if fault_type and predicted_mode and fault_type not in predicted_mode:
            confidence -= 0.2
            conflicts.append(
                f"预测故障模式 {predicted_mode} 与规则根因 {fault_type} 不一致"
            )
            confidence_factors.append("conflicting_prediction:-0.20")
        elif probability >= 0.5:
            confidence += 0.15
            confidence_factors.append("fault_prediction_support:+0.15")
    if severity == "CRITICAL":
        confidence += 0.05
        confidence_factors.append("critical_alarm_signal:+0.05")
    if not citations:
        confidence_factors.append("rag_evidence_absent:+0.00")
    confidence = max(confidence, 0.1)
    confidence = min(confidence, 0.85)
    evidence["confidence_factors"] = confidence_factors
    evidence["evidence_conflicts"] = conflicts

    return RootCauseAnalysisResult(
        hypothesis=hypothesis,
        fault_type=fault_type,
        contributing_factors=contributing,
        evidence=evidence,
        citations=citations,
        confidence=round(confidence, 2),
        confidence_factors=confidence_factors,
        evidence_conflicts=conflicts,
    )


@dataclass(slots=True, frozen=True)
class RiskAssessmentResult:
    """透明的报警风险规则输出。"""

    risk_level: str
    reasons: list[str]
    inputs: dict[str, Any]


def assess_alarm_risk(
    *,
    severity: str,
    confidence: float,
    correlated_alarm_count: int,
    equipment_health_score: float | None,
    equipment_risk_level: RiskLevelEnum | str | None,
    fault_probability: float | None,
) -> RiskAssessmentResult:
    """综合报警、预测和设备状态，按可解释规则给出风险等级。"""
    level = "LOW"
    reasons: list[str] = []
    normalized_equipment_risk = (
        equipment_risk_level.value
        if isinstance(equipment_risk_level, RiskLevelEnum)
        else str(equipment_risk_level or "").lower()
    )
    if severity.upper() == "WARNING":
        level = "MEDIUM"
        reasons.append("industrial_alarm=WARNING")
    if severity.upper() == "CRITICAL":
        level = "HIGH"
        reasons.append("industrial_alarm=CRITICAL")
    strong_support = False
    if fault_probability is not None and fault_probability >= 0.7:
        strong_support = True
        reasons.append("fault_probability>=0.70")
    if equipment_health_score is not None and equipment_health_score <= 50:
        strong_support = True
        reasons.append("health_score<=50")
    if correlated_alarm_count >= 3:
        strong_support = True
        reasons.append("correlated_alarm_count>=3")
    if normalized_equipment_risk in {"high", "critical"}:
        reasons.append(f"equipment_risk={normalized_equipment_risk}")
        if normalized_equipment_risk == "critical":
            strong_support = True
        if level == "MEDIUM":
            level = "HIGH"
    if severity.upper() == "CRITICAL" and strong_support:
        level = "CRITICAL"
    elif level == "MEDIUM" and strong_support:
        level = "HIGH"
    if confidence < 0.5:
        reasons.append("diagnosis_confidence<0.50_requires_review")
    return RiskAssessmentResult(
        risk_level=level,
        reasons=reasons,
        inputs={
            "alarm_severity": severity.upper(),
            "diagnosis_confidence": confidence,
            "correlated_alarm_count": correlated_alarm_count,
            "equipment_health_score": equipment_health_score,
            "equipment_risk_level": normalized_equipment_risk or None,
            "fault_probability": fault_probability,
        },
    )


# ----------------------------------------------------------------------
# Maintenance Decision Support（仅建议，不执行）
# ----------------------------------------------------------------------

HUMAN_APPROVAL_DISCLAIMER: Final = (
    "以上为 AI 辅助分析建议，仅供人工决策参考；"
    "任何设备操作必须通过智能工单与 Human Approval（OperationApproval）审批流执行，"
    "本分析不会自动创建或执行任何控制。"
)


@dataclass(slots=True)
class DecisionSupportResult:
    """维护决策支持：建议行动 + 优先级建议 + 关联工单提示。"""

    recommended_actions: list[str] = field(default_factory=list)
    suggested_priority: str = "P3"
    related_work_orders: list[dict[str, Any]] = field(default_factory=list)
    requires_human_review: bool = True
    disclaimer: str = HUMAN_APPROVAL_DISCLAIMER


def build_decision_support(
    db: Session,
    *,
    severity: str,
    fault_type: str | None,
    confidence: float,
    equipment_id: int,
) -> DecisionSupportResult:
    """把根因假设转化为维护行动建议（只读查询，不创建任何对象）。"""
    from app.models.base import WorkOrderStatusEnum
    from app.models.workorder import WorkOrder

    guidance = FAULT_GUIDANCE.get(fault_type or "", None)
    if guidance and fault_type:
        actions = [item for item in str(guidance[1]).split("；") if item]
        skills = "、".join(guidance[2]) if guidance[2] else ""
        parts = "、".join(
            part.get("name") if isinstance(part, dict) else str(part)
            for part in (guidance[3] or [])
        )
        if skills:
            actions.append(f"建议技能配置：{skills}")
        if parts:
            actions.append(f"建议备件预核：{parts}")
    else:
        actions = [
            "安排现场点检并记录频谱/趋势数据",
            "结合历史工单与知识库案例复核根因",
        ]
    actions.append("处理前确认现场安全条件（LOTO）")

    if severity == "CRITICAL":
        suggested_priority = "P1" if confidence >= 0.7 else "P2"
    elif severity == "WARNING":
        suggested_priority = "P3"
    else:
        suggested_priority = "P4"

    open_statuses = [
        WorkOrderStatusEnum.pending_dispatch,
        WorkOrderStatusEnum.assigned,
        WorkOrderStatusEnum.accepted,
        WorkOrderStatusEnum.in_progress,
        WorkOrderStatusEnum.paused,
    ]
    related_rows = (
        db.query(WorkOrder)
        .filter(
            WorkOrder.equipment_id == equipment_id,
            WorkOrder.status.in_(open_statuses),
        )
        .order_by(WorkOrder.created_at.desc())
        .limit(3)
        .all()
    )
    related = [
        {
            "work_order_id": row.id,
            "code": row.code,
            "title": row.title,
            "status": row.status.value if row.status else None,
        }
        for row in related_rows
    ]

    return DecisionSupportResult(
        recommended_actions=actions,
        suggested_priority=suggested_priority,
        related_work_orders=related,
        requires_human_review=True,
        disclaimer=HUMAN_APPROVAL_DISCLAIMER,
    )
