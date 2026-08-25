"""设备遥测、异常、预测、维修策略、审批与效果验证。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import RiskLevelEnum, TimestampMixin
from app.models.equipment import Equipment


class EquipmentSensor(TimestampMixin, Base):
    __tablename__ = "equipment_sensors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    metric_type: Mapped[str] = mapped_column(String(64), index=True)
    unit: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="online", index=True)
    warning_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    warning_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    critical_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    critical_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    latest_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    equipment: Mapped[Equipment] = relationship()


class TelemetryRecord(TimestampMixin, Base):
    __tablename__ = "telemetry_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    vibration_rms: Mapped[float | None] = mapped_column(Float, nullable=True)
    bearing_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    motor_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    motor_voltage: Mapped[float | None] = mapped_column(Float, nullable=True)
    rotational_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    ambient_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    cumulative_runtime_hours: Mapped[float] = mapped_column(Float, default=0.0)
    scenario: Mapped[str] = mapped_column(String(48), default="normal", index=True)
    quality: Mapped[float] = mapped_column(Float, default=1.0)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    anomaly_metrics: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # 工业事件链路追踪：同一次事件链共享同一 trace_id（历史数据为 NULL）。
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class AnomalyEvent(TimestampMixin, Base):
    __tablename__ = "anomaly_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    telemetry_id: Mapped[int | None] = mapped_column(
        ForeignKey("telemetry_records.id", ondelete="SET NULL"), nullable=True
    )
    fault_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(160))
    severity: Mapped[RiskLevelEnum] = mapped_column(
        Enum(RiskLevelEnum), default=RiskLevelEnum.medium, index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    diagnosis_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class FaultDiagnosis(TimestampMixin, Base):
    __tablename__ = "fault_diagnoses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    anomaly_event_id: Mapped[int] = mapped_column(
        ForeignKey("anomaly_events.id", ondelete="CASCADE"), unique=True, index=True
    )
    fault_type: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str] = mapped_column(Text)
    possible_causes: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rag_citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    requires_human_review: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RiskPrediction(TimestampMixin, Base):
    __tablename__ = "risk_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    anomaly_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("anomaly_events.id", ondelete="SET NULL"), nullable=True
    )
    risk_level: Mapped[RiskLevelEnum] = mapped_column(
        Enum(RiskLevelEnum), default=RiskLevelEnum.medium, index=True
    )
    failure_mode: Mapped[str] = mapped_column(String(96), index=True)
    probability: Mapped[float] = mapped_column(Float)
    remaining_useful_life_hours: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    predicted_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    maintenance_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    maintenance_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    factors: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    model_version: Mapped[str] = mapped_column(
        String(48), default="deterministic-rules-v1"
    )
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class MaintenanceRecommendation(TimestampMixin, Base):
    __tablename__ = "maintenance_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    prediction_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_predictions.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(160))
    strategy: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(8), default="P3", index=True)
    required_skills: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    required_parts: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True
    )
    risk_operations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    dispatch_suggestion: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default="proposed", index=True)
    auto_work_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class SparePartReservation(TimestampMixin, Base):
    __tablename__ = "spare_part_reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_recommendations.id", ondelete="CASCADE"), index=True
    )
    work_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    spare_part_id: Mapped[int | None] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    requested_name: Mapped[str] = mapped_column(String(128))
    requested_qty: Mapped[int] = mapped_column(Integer, default=1)
    reserved_qty: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    shortage_qty: Mapped[int] = mapped_column(Integer, default=0)
    reserved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OperationApproval(TimestampMixin, Base):
    __tablename__ = "operation_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    work_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("maintenance_recommendations.id", ondelete="SET NULL"), nullable=True
    )
    command_type: Mapped[str] = mapped_column(String(64))
    command_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    execution_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, default=lambda: uuid4().hex
    )
    risk_level: Mapped[RiskLevelEnum] = mapped_column(
        Enum(RiskLevelEnum), default=RiskLevelEnum.high, index=True
    )
    risk_reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    execution_attempt: Mapped[int] = mapped_column(Integer, default=0)
    command_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    command_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reconciliation_outcome: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    reconciliation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_device_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconciled_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class OperationExecutionAudit(Base):
    __tablename__ = "operation_execution_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    approval_id: Mapped[int] = mapped_column(
        ForeignKey("operation_approvals.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    execution_key: Mapped[str] = mapped_column(String(64), index=True)
    execution_attempt: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_device_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class MaintenanceVerification(TimestampMixin, Base):
    __tablename__ = "maintenance_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), unique=True, index=True
    )
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    health_score_before: Mapped[float] = mapped_column(Float)
    health_score_after: Mapped[float] = mapped_column(Float)
    telemetry_before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    telemetry_after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[str] = mapped_column(String(24), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    knowledge_article_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_articles.id", ondelete="SET NULL"), nullable=True
    )


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    anomaly_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("anomaly_events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    goal: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    provider: Mapped[str] = mapped_column(String(48), default="deterministic-mock")
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    requires_human_review: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Agent 链路追踪：与所属工业事件链共享 trace_id。
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class ToolInvocation(TimestampMixin, Base):
    __tablename__ = "tool_invocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(48), default="local")
    status: Mapped[str] = mapped_column(String(24), default="success", index=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
