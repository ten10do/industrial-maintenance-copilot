"""工业网关数据库模型：连接配置与节点映射。

新增表：

- ``gateway_connections``：网关连接（协议、端点、状态、最近连接时间）。
- ``opcua_node_mappings``：OPC UA NodeId → 平台设备资产 + 指标映射。

两表均为追加式新增，不修改任何既有业务表。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
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
