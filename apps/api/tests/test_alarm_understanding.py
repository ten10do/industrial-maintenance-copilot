"""Alarm Understanding 与 Root Cause Analysis 测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.industrial_gateway.alarm_intelligence.engine import (
    analyze_root_cause,
    assess_alarm_risk,
    latest_telemetry_fields,
    understand_alarm,
)
from app.models.intelligence import TelemetryRecord

HEALTHY: dict[str, float | bool | None] = {
    "bearing_temperature": 55.0,
    "vibration_rms": 1.8,
    "motor_current": 12.0,
    "motor_voltage": 380.0,
    "load_ratio": 60.0,
}


def test_understanding_summarizes_abnormal_metrics():
    fields = {**HEALTHY, "bearing_temperature": 87.5, "vibration_rms": 4.9}
    result = understand_alarm(
        severity="WARNING", message="工业报警升级为 WARNING", telemetry_fields=fields
    )
    assert result.severity == "WARNING"
    assert "轴承温度=87.5" in result.summary
    assert "振动 RMS=4.9" in result.summary
    metrics = {item["metric"] for item in result.abnormal_metrics}
    assert metrics == {"bearing_temperature", "vibration_rms"}
    # 越限比例高的排前面。
    assert result.abnormal_metrics[0]["metric"] == "bearing_temperature"
    assert result.triggered_rules and "轴承温度>75.0" in result.triggered_rules


def test_understanding_handles_healthy_telemetry():
    result = understand_alarm(
        severity="CRITICAL", message="Alarm 已置位", telemetry_fields=dict(HEALTHY)
    )
    assert result.abnormal_metrics == []
    assert "Alarm 位已置位" in result.triggered_rules
    assert "瞬态" in result.summary or "报警位" in result.summary


def test_root_cause_maps_temperature_to_bearing_overheat(db):
    fields = {**HEALTHY, "bearing_temperature": 96.0}
    result = analyze_root_cause(
        db,
        severity="CRITICAL",
        message="工业报警升级为 CRITICAL",
        telemetry_fields=fields,
        telemetry_record_id=None,
        equipment_name="验证电机",
    )
    assert result.fault_type == "bearing_overheat"
    assert "bearing_overheat" in result.hypothesis
    # 复用平台既有处置知识（FAULT_GUIDANCE）。
    assert "轴承" in result.hypothesis
    assert any("轴承温度" in factor for factor in result.contributing_factors)
    assert 0.5 <= result.confidence <= 0.85
    assert result.evidence["abnormal_metrics"][0]["metric"] == "bearing_temperature"


def test_root_cause_without_offenders_stays_honest(db):
    result = analyze_root_cause(
        db,
        severity="CRITICAL",
        message="Alarm 已置位",
        telemetry_fields=dict(HEALTHY),
        telemetry_record_id=None,
        equipment_name="验证电机",
    )
    assert result.fault_type is None
    assert "insufficient_evidence" in result.hypothesis
    assert "manual_review_required" in result.hypothesis
    assert result.confidence < 0.5
    assert result.citations == []


def test_root_cause_citations_degrade_gracefully(db):
    """空知识库时引用为空但不报错（RAG 降级路径）。"""
    result = analyze_root_cause(
        db,
        severity="WARNING",
        message="工业报警升级为 WARNING",
        telemetry_fields={**HEALTHY, "vibration_rms": 4.9},
        telemetry_record_id=None,
        equipment_name="验证电机",
    )
    assert result.fault_type == "rotor_unbalance"
    assert isinstance(result.citations, list)


def test_latest_telemetry_fields_reads_record(db, equipment):
    db.add(
        TelemetryRecord(
            equipment_id=equipment.id,
            collected_at=datetime.now(UTC),
            bearing_temperature=88.0,
            vibration_rms=1.9,
            motor_current=12.1,
            motor_voltage=380.0,
            load_ratio=60.0,
            cumulative_runtime_hours=100.0,
        )
    )
    db.commit()

    fields, record_id = latest_telemetry_fields(db, equipment.id)
    record = db.query(TelemetryRecord).filter_by(equipment_id=equipment.id).one()
    assert record_id == record.id
    assert fields["bearing_temperature"] == 88.0


def test_risk_rule_escalates_critical_alarm_with_prediction_support():
    result = assess_alarm_risk(
        severity="CRITICAL",
        confidence=0.75,
        correlated_alarm_count=2,
        equipment_health_score=62,
        equipment_risk_level="high",
        fault_probability=0.82,
    )
    assert result.risk_level == "CRITICAL"
    assert "fault_probability>=0.70" in result.reasons
    assert result.inputs["fault_probability"] == 0.82
