"""工业网关数据库模型：连接配置、节点映射、订阅与报警分析。

新增表：

- ``gateway_connections``：网关连接（协议、端点、状态、最近连接时间）。
- ``opcua_node_mappings``：OPC UA NodeId → 平台设备资产 + 指标映射。
- ``gateway_subscriptions``：DataChange 订阅（事件驱动接入，只读）。
- ``industrial_alarms``：工业报警（OPC UA Alarm 语义）。
- ``alarm_analysis_records``：报警智能分析结论（仅建议，不执行）。

均为追加式新增，不修改任何既有业务表。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.equipment import Equipment

PROTOCOL_OPCUA = "opcua"

# 网关状态机：disconnected → connected → error（连接失败回退）
GATEWAY_STATUS_DISCONNECTED = "disconnected"
GATEWAY_STATUS_CONNECTED = "connected"
GATEWAY_STATUS_ERROR = "error"


class GatewayConnection(TimestampMixin, Base):
    """工业协议网关连接配置与运行状态。"""

    __tablename__ = "gateway_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    protocol: Mapped[str] = mapped_column(
        String(24), default=PROTOCOL_OPCUA, index=True
    )
    endpoint: Mapped[str] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(16), default="mock")
    status: Mapped[str] = mapped_column(
        String(24), default=GATEWAY_STATUS_DISCONNECTED, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    poll_interval_seconds: Mapped[float] = mapped_column(Float, default=5.0)
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class OpcUaNodeMapping(TimestampMixin, Base):
    """OPC UA 节点与平台设备资产的映射关系（配置化，不硬编码）。"""

    __tablename__ = "opcua_node_mappings"
    __table_args__ = (
        UniqueConstraint(
            "equipment_id",
            "metric_name",
            name="uq_opcua_node_mapping_equipment_metric",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    metric_name: Mapped[str] = mapped_column(String(64), index=True)
    unit: Mapped[str] = mapped_column(String(24), default="")
    scale: Mapped[float] = mapped_column(Float, default=1.0)
    offset: Mapped[float] = mapped_column(Float, default=0.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 说明字段：informational 节点（如 RunningState/Alarm）仅展示，不进入遥测快照。
    informational: Mapped[bool] = mapped_column(Boolean, default=False)

    equipment: Mapped[Equipment] = relationship()


class GatewaySubscription(TimestampMixin, Base):
    """OPC UA DataChange 订阅（事件驱动接入，只读）。"""

    __tablename__ = "gateway_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "gateway_id",
            "node_id",
            name="uq_gateway_subscription_gateway_node",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gateway_id: Mapped[int] = mapped_column(
        ForeignKey("gateway_connections.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str] = mapped_column(String(160), index=True)
    sampling_interval: Mapped[float] = mapped_column(Float, default=1000.0)
    status: Mapped[str] = mapped_column(String(24), default="inactive", index=True)
    last_event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    event_count: Mapped[int] = mapped_column(Integer, default=0)


class IndustrialAlarm(TimestampMixin, Base):
    """工业报警（OPC UA Alarm 语义的平台侧记录）。

    生命周期：产生（created_at）→ 人工确认（acknowledged）→ 解除（cleared_at）。
    仅在报警状态跃迁时产生/解除，不随高频事件重复创建。
    """

    __tablename__ = "industrial_alarms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    severity: Mapped[str] = mapped_column(String(16), index=True)  # WARNING/CRITICAL
    message: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64), default="opcua", index=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cleared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    equipment: Mapped[Equipment] = relationship()


class AlarmAnalysisRecord(TimestampMixin, Base):
    """工业报警智能分析记录（Alarm Intelligence，1:1 附属报警）。

    定位：AI-assisted industrial alarm analysis 的持久化结论——
    理解摘要、根因假设、证据链与维护建议。**仅建议，不执行**：
    任何设备操作必须走既有工单与 Human Approval 审批流。
    """

    __tablename__ = "alarm_analysis_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alarm_id: Mapped[int] = mapped_column(
        ForeignKey("industrial_alarms.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    correlation_group_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    summary: Mapped[str] = mapped_column(Text)
    root_cause_hypothesis: Mapped[str] = mapped_column(Text)
    contributing_factors: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    recommended_actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    suggested_priority: Mapped[str] = mapped_column(String(8), default="P3")
    related_work_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True
    )
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=True)
    model_version: Mapped[str] = mapped_column(
        String(48), default="deterministic-rules-v1"
    )
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
