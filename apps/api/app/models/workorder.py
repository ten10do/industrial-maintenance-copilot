"""工单及关联实体：分派、状态历史、检查清单。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import (
    AuditMixin,
    PriorityEnum,
    TimestampMixin,
    WorkOrderStatusEnum,
    WorkOrderTypeEnum,
)


class WorkOrder(AuditMixin, Base):
    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(128), index=True)
    equipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fault_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("fault_reports.id", ondelete="SET NULL"), nullable=True
    )
    fault_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fault_code_id: Mapped[int | None] = mapped_column(
        ForeignKey("fault_codes.id", ondelete="SET NULL"), nullable=True
    )
    order_type: Mapped[WorkOrderTypeEnum] = mapped_column(
        Enum(WorkOrderTypeEnum), default=WorkOrderTypeEnum.fault_repair, index=True
    )
    priority: Mapped[PriorityEnum] = mapped_column(Enum(PriorityEnum), default=PriorityEnum.P3, index=True)
    status: Mapped[WorkOrderStatusEnum] = mapped_column(
        Enum(WorkOrderStatusEnum), default=WorkOrderStatusEnum.pending_dispatch, index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    planned_start_at: Mapped[datetime | None] = mapped_column(nullable=True)
    planned_end_at: Mapped[datetime | None] = mapped_column(nullable=True)
    actual_start_at: Mapped[datetime | None] = mapped_column(nullable=True)
    actual_end_at: Mapped[datetime | None] = mapped_column(nullable=True)
    safety_risk: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_diagnosis_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    maintenance_steps: Mapped[list | None] = mapped_column(JSON, nullable=True)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 完工信息
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_taken: Mapped[str | None] = mapped_column(Text, nullable=True)
    replaced_parts: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment_status_after: Mapped[str | None] = mapped_column(String(32), nullable=True)
    follow_up_advice: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_observation: Mapped[bool] = mapped_column(Boolean, default=False)
    completion_photos: Mapped[list | None] = mapped_column(JSON, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    equipment: Mapped["Equipment | None"] = relationship()  # type: ignore[name-defined]
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assignee_id])  # type: ignore[name-defined]
    creator: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])  # type: ignore[name-defined]
    checklist_items: Mapped[list["WorkOrderChecklistItem"]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan"
    )
    logs: Mapped[list["MaintenanceLog"]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan"
    )
    labor_entries: Mapped[list["LaborEntry"]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan"
    )
    spare_parts: Mapped[list["WorkOrderSparePart"]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan"
    )
    status_history: Mapped[list["WorkOrderStatusHistory"]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan"
    )
    assignments: Mapped[list["WorkOrderAssignment"]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan"
    )


class WorkOrderAssignment(TimestampMixin, Base):
    __tablename__ = "work_order_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="assignments")


class WorkOrderStatusHistory(TimestampMixin, Base):
    __tablename__ = "work_order_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), index=True)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="status_history")


class WorkOrderChecklistItem(AuditMixin, Base):
    __tablename__ = "work_order_checklist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(32), default="repair")
    content: Mapped[str] = mapped_column(String(255))
    order: Mapped[int] = mapped_column(Integer, default=0)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="checklist_items")
