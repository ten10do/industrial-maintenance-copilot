"""故障上报 schema。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.base import FaultReportStatusEnum, PriorityEnum, UrgencyEnum


class FaultReportBase(BaseModel):
    equipment_id: int | None = None
    title: str
    description: str
    occurred_at: datetime | None = None
    phenomenon: str | None = None
    is_downtime: bool = False
    affects_production: bool = False
    has_safety_risk: bool = False
    photos: list[str] | None = None
    reporter_name: str | None = None
    contact: str | None = None
    urgency: UrgencyEnum = UrgencyEnum.medium
    fault_code_id: int | None = None


class FaultReportCreate(FaultReportBase):
    pass


class FaultReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    equipment_id: int | None = None
    equipment_name: str | None = None
    equipment_code: str | None = None
    title: str
    description: str
    occurred_at: datetime | None = None
    phenomenon: str | None = None
    is_downtime: bool
    affects_production: bool
    has_safety_risk: bool
    photos: list[str] | None = None
    reporter_name: str | None = None
    contact: str | None = None
    urgency: UrgencyEnum
    status: FaultReportStatusEnum
    raw_text: str | None = None
    parsed_fields: dict[str, Any] | None = None
    fault_code_id: int | None = None
    created_at: datetime | None = None
    related_work_order_id: int | None = None


class FaultReportDetail(FaultReportOut):
    """Detail view with full related work order info."""
    related_work_order_code: str | None = None
    related_work_order_status: str | None = None


class ConvertToWorkOrderRequest(BaseModel):
    assignee_id: int | None = None
    priority: PriorityEnum | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    notes: str | None = None


class ConvertToWorkOrderResponse(BaseModel):
    fault_report_id: int
    work_order_id: int
    work_order_code: str
    priority: str
    status: str


class ParseFaultRequest(BaseModel):
    text: str


class ParseFaultResult(BaseModel):
    title: str | None = None
    description: str | None = None
    equipment_keyword: str | None = None
    equipment_id: int | None = None
    phenomenon: str | None = None
    fault_code: str | None = None
    is_downtime: bool = False
    affects_production: bool = False
    has_safety_risk: bool = False
    urgency: UrgencyEnum = UrgencyEnum.medium
    suggested_priority: str | None = None
    confidence: float = 0.0
    raw: dict[str, Any] | None = None
