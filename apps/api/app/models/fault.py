"""故障上报。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import AuditMixin, FaultReportStatusEnum, UrgencyEnum


class FaultReport(AuditMixin, Base):
    __tablename__ = "fault_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime | None] = mapped_column(nullable=True)
    phenomenon: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_downtime: Mapped[bool] = mapped_column(default=False)
    affects_production: Mapped[bool] = mapped_column(default=False)
    has_safety_risk: Mapped[bool] = mapped_column(default=False)
    photos: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reporter_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact: Mapped[str | None] = mapped_column(String(64), nullable=True)
    urgency: Mapped[UrgencyEnum] = mapped_column(Enum(UrgencyEnum), default=UrgencyEnum.medium, index=True)
    status: Mapped[FaultReportStatusEnum] = mapped_column(
        Enum(FaultReportStatusEnum), default=FaultReportStatusEnum.pending, index=True
    )
    # 自然语言原始输入与解析结果
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fault_code_id: Mapped[int | None] = mapped_column(
        ForeignKey("fault_codes.id", ondelete="SET NULL"), nullable=True
    )

    equipment: Mapped["Equipment | None"] = relationship()  # type: ignore[name-defined]
