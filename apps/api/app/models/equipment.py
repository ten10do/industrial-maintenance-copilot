"""设备、设备类型、故障代码、备件。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import JSON, Date, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import (
    AuditMixin,
    EquipmentStatusEnum,
    RiskLevelEnum,
    TimestampMixin,
)
from app.models.user import User


class EquipmentType(AuditMixin, Base):
    __tablename__ = "equipment_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    equipment: Mapped[list[Equipment]] = relationship(back_populates="equipment_type")
    fault_codes: Mapped[list[FaultCode]] = relationship(back_populates="equipment_type")


class Equipment(AuditMixin, Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_uuid: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        index=True,
        default=lambda: __import__("uuid").uuid4().hex,
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    equipment_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipment_types.id", ondelete="SET NULL"), nullable=True, index=True
    )
    plant: Mapped[str | None] = mapped_column(String(64), nullable=True)
    production_line: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    commissioning_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[EquipmentStatusEnum] = mapped_column(
        Enum(EquipmentStatusEnum), default=EquipmentStatusEnum.running, index=True
    )
    risk_level: Mapped[RiskLevelEnum] = mapped_column(
        Enum(RiskLevelEnum), default=RiskLevelEnum.medium, index=True
    )
    responsible_person_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_maintenance_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_maintenance_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    health_score: Mapped[float] = mapped_column(Float, default=100.0, index=True)
    rated_parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    cumulative_runtime_hours: Mapped[float] = mapped_column(Float, default=0.0)
    qr_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    equipment_type: Mapped[EquipmentType | None] = relationship(
        back_populates="equipment"
    )
    responsible_person: Mapped[User | None] = relationship(
        foreign_keys=[responsible_person_id]
    )


class FaultCode(TimestampMixin, Base):
    __tablename__ = "fault_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(32), default="medium")
    equipment_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipment_types.id", ondelete="SET NULL"), nullable=True
    )

    equipment_type: Mapped[EquipmentType | None] = relationship(
        back_populates="fault_codes"
    )


class SparePart(AuditMixin, Base):
    __tablename__ = "spare_parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    specification: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit: Mapped[str] = mapped_column(String(16), default="个")
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
