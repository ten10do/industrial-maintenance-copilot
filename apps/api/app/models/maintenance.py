"""维修过程记录、工时、备件使用、附件、维修报告。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import MaintenanceLogTypeEnum, TimestampMixin


class MaintenanceLog(TimestampMixin, Base):
    __tablename__ = "maintenance_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    log_type: Mapped[MaintenanceLogTypeEnum] = mapped_column(
        Enum(MaintenanceLogTypeEnum), default=MaintenanceLogTypeEnum.note
    )
    content: Mapped[str] = mapped_column(Text)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_polished: Mapped[str | None] = mapped_column(Text, nullable=True)
    photos: Mapped[list | None] = mapped_column(JSON, nullable=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    operator_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    logged_at: Mapped[datetime | None] = mapped_column(nullable=True)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="logs")  # type: ignore[name-defined]


class LaborEntry(TimestampMixin, Base):
    __tablename__ = "labor_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    hours: Mapped[float] = mapped_column(Float, default=0.0)
    is_downtime: Mapped[bool] = mapped_column(Boolean, default=False)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    operator_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="labor_entries")  # type: ignore[name-defined]


class WorkOrderSparePart(TimestampMixin, Base):
    __tablename__ = "work_order_spare_parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    spare_part_id: Mapped[int | None] = mapped_column(ForeignKey("spare_parts.id", ondelete="SET NULL"), nullable=True)
    spare_part_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    spare_part_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=1)
    unit: Mapped[str] = mapped_column(String(16), default="个")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="spare_parts")  # type: ignore[name-defined]
    spare_part: Mapped["SparePart | None"] = relationship()  # type: ignore[name-defined]


class Attachment(TimestampMixin, Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=True, index=True)
    fault_report_id: Mapped[int | None] = mapped_column(ForeignKey("fault_reports.id", ondelete="CASCADE"), nullable=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    file_url: Mapped[str] = mapped_column(String(512))
    file_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class WorkOrderReport(TimestampMixin, Base):
    """持久化维修报告，支持版本管理。"""

    __tablename__ = "work_order_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    generation_method: Mapped[str] = mapped_column(String(16), default="template")  # "ai" | "template"
    summary: Mapped[str] = mapped_column(Text)
    sections: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
