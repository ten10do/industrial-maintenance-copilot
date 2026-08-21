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


def analyze_root_cause(
    db: Session,
    *,
    severity: str,
    message: str,
    telemetry_fields: dict[str, float | bool | None],
    telemetry_record_id: int | None,
    equipment_name: str,
    equipment_type_id: int | None = None,
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
        fault_type = "unknown_anomaly"

    guidance = FAULT_GUIDANCE.get(fault_type or "", None)
    if guidance and fault_type:
        cause_text = guidance[0]
        hypothesis = f"根因假设（{fault_type}）：{cause_text}"
    else:
        hypothesis = (
            "根因假设：多信号复合或瞬态触发，规则层无法唯一确定根因；"
            "建议结合频谱/趋势与现场点检进一步确认。"
        )

    evidence: dict[str, Any] = {
        "severity": severity,
        "equipment": equipment_name,
        "telemetry_record_id": telemetry_record_id,
        "telemetry_fields": {key: value for key, value in telemetry_fields.items()},
        "abnormal_metrics": abnormal,
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
        citations.append(
            {
                "article_id": article.get("article_id"),
                "title": article.get("title"),
                "score": article.get("score"),
            }
        )

    confidence = 0.55
    if len(abnormal) >= 2:
        confidence += 0.15
    if fault_type is not None and guidance:
        confidence += 0.1
    if citations:
        confidence += 0.05
    confidence = min(confidence, 0.85)

    return RootCauseAnalysisResult(
        hypothesis=hypothesis,
        fault_type=fault_type,
        contributing_factors=contributing,
        evidence=evidence,
        citations=citations,
        confidence=round(confidence, 2),
    )
