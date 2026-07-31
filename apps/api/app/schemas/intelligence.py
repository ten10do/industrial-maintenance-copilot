"""智能运维、设备仿真与安全审批 schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import RiskLevelEnum

SimulationScenario = Literal[
    "normal",
    "temperature_rise",
    "vibration_spike",
    "current_overload",
    "bearing_wear",
    "voltage_fluctuation",
    "sensor_disconnect",
    "composite_anomaly",
]


class TelemetryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment_id: int
    collected_at: datetime
    vibration_rms: float | None = None
    bearing_temperature: float | None = None
    motor_current: float | None = None
    motor_voltage: float | None = None
    rotational_speed: float | None = None
    load_ratio: float | None = None
    ambient_temperature: float | None = None
    cumulative_runtime_hours: float
    scenario: str
    quality: float
    is_anomaly: bool
    anomaly_metrics: list[str] | None = None


class SimulatorConfigureRequest(BaseModel):
    equipment_ids: list[int] = Field(min_length=1)
    interval_seconds: float = Field(default=5.0, ge=0.2, le=3600)
    scenario: SimulationScenario = "normal"
    seed: int = 20260731
    auto_create_work_orders: bool = True


class SimulatorStatusOut(BaseModel):
    running: bool
    interval_seconds: float
    scenario: str
    seed: int
    equipment_ids: list[int]
    generated_points: int
    auto_create_work_orders: bool


class SimulatorTickOut(BaseModel):
    generated: int
    anomalies: int
    work_orders_created: int
    equipment_ids: list[int]


class ApprovalCreate(BaseModel):
    equipment_id: int
    work_order_id: int | None = None
    recommendation_id: int | None = None
    command_type: str
    command_payload: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevelEnum = RiskLevelEnum.high
    risk_reason: str = Field(min_length=4)


class ApprovalReview(BaseModel):
    note: str | None = None


class VerificationCreate(BaseModel):
    work_order_id: int
    notes: str | None = None
    create_knowledge_case: bool = True
