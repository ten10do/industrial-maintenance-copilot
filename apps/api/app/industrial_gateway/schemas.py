"""工业网关 API 的 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class GatewayConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    protocol: str
    endpoint: str
    mode: str
    status: str
    enabled: bool
    poll_interval_seconds: float
    last_connected_at: datetime | None
    last_sync_at: datetime | None
    last_error: str | None


class GatewayNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: str
    equipment_code: str | None
    metric_name: str
    unit: str
    enabled: bool
    informational: bool
    last_value: float | bool | int | str | None = None
    last_quality: str | None = None
    last_timestamp: datetime | None = None
    last_error: str | None = None


class GatewayNodesOut(BaseModel):
    nodes: list[GatewayNodeOut]
    read_only: bool = True


class TestConnectOut(BaseModel):
    ok: bool
    endpoint: str
    latency_ms: float
    probe_node: str | None
    sample_value: float | bool | int | str | None
    error: str | None


class GatewaySyncOut(BaseModel):
    ok: bool
    error: str | None
    reads_total: int
    accepted: int
    rejected: int
    corrections: int
    reject_reasons: dict[str, int]
    snapshots_ingested: int
    snapshots_skipped: int
    anomalies: int
    work_orders_created: int
    telemetry_ids: list[int]
    skipped_details: list[str]
    duration_ms: float


class MappingReloadOut(BaseModel):
    created: int
    updated: int
    skipped: list[str]


class GatewayStatusOut(BaseModel):
    connection: GatewayConnectionOut | None
    runtime: dict[str, Any]
    enabled: bool
    read_only: bool = True
    seed_error: str | None = None


# ============ OPC UA DataChange 订阅（事件驱动，只读） ============


class GatewaySubscriptionRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    gateway_id: int
    node_id: str
    sampling_interval: float
    status: str
    last_event_at: datetime | None
    event_count: int


class SubscriptionStatusOut(BaseModel):
    ok: bool = True
    status: str
    subscription_status: str
    sampling_interval_ms: float
    active_nodes: list[str] = []
    buffer_pending: int = 0
    event_totals: dict[str, int] = {}
    last_event_at: str | None = None
    last_event: str | None = None
    error: str | None = None
    read_only: bool = True
    rows: list[GatewaySubscriptionRowOut] = []


class SubscriptionActionOut(BaseModel):
    ok: bool
    status: str
    already_active: bool = False
    error: str | None = None
    detail: dict[str, Any] = {}
