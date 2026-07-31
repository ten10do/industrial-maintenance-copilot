"""工单及相关实体 schema。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import (
    MaintenanceLogTypeEnum,
    PriorityEnum,
    WorkOrderStatusEnum,
    WorkOrderTypeEnum,
)


class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    work_order_id: int
    category: str = "repair"
    content: str
    order: int
    is_required: bool
    is_completed: bool
    remark: str | None = None
    completed_at: datetime | None = None
    completed_by: int | None = None


class ChecklistItemUpdate(BaseModel):
    is_completed: bool | None = None
    remark: str | None = None


class MaintenanceLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    work_order_id: int
    log_type: MaintenanceLogTypeEnum
    content: str
    raw_content: str | None = None
    ai_polished: str | None = None
    photos: list[str] | None = None
    operator_id: int | None = None
    operator_name: str | None = None
    logged_at: datetime | None = None
    created_at: datetime | None = None


class MaintenanceLogCreate(BaseModel):
    log_type: MaintenanceLogTypeEnum = MaintenanceLogTypeEnum.note
    content: str
    raw_content: str | None = None
    photos: list[str] | None = None
    logged_at: datetime | None = None


class LaborEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    work_order_id: int
    started_at: datetime | None = None
    ended_at: datetime | None = None
    hours: float
    is_downtime: bool
    operator_id: int | None = None
    operator_name: str | None = None
    remark: str | None = None


class LaborEntryCreate(BaseModel):
    started_at: datetime | None = None
    ended_at: datetime | None = None
    hours: float = 0.0
    is_downtime: bool = False
    operator_name: str | None = None
    remark: str | None = None


class SparePartUsageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    work_order_id: int
    spare_part_id: int | None = None
    spare_part_code: str | None = None
    spare_part_name: str | None = None
    quantity: float
    unit: str
    remark: str | None = None


class SparePartUsageCreate(BaseModel):
    spare_part_id: int | None = None
    spare_part_code: str | None = None
    spare_part_name: str | None = None
    quantity: float = 1
    unit: str = "个"
    remark: str | None = None


# ---- Update schemas ----


class MaintenanceLogUpdate(BaseModel):
    content: str | None = None
    log_type: MaintenanceLogTypeEnum | None = None
    photos: list[str] | None = None
    logged_at: datetime | None = None


class LaborEntryUpdate(BaseModel):
    started_at: datetime | None = None
    ended_at: datetime | None = None
    hours: float | None = None
    is_downtime: bool | None = None
    remark: str | None = None


class SparePartUsageUpdate(BaseModel):
    spare_part_id: int | None = None
    spare_part_code: str | None = None
    spare_part_name: str | None = None
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = None
    remark: str | None = None


# ---- Completion validation ----


class CompletionValidationError(BaseModel):
    code: str = "WORK_ORDER_COMPLETION_VALIDATION_FAILED"
    message: str = "工单尚未满足完工条件"
    missing_requirements: list[str] = []


class WorkOrderBase(BaseModel):
    title: str
    equipment_id: int | None = None
    fault_report_id: int | None = None
    fault_description: str | None = None
    fault_code_id: int | None = None
    order_type: WorkOrderTypeEnum = WorkOrderTypeEnum.fault_repair
    priority: PriorityEnum = PriorityEnum.P3
    safety_risk: str | None = None
    ai_diagnosis_summary: str | None = None
    acceptance_criteria: str | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None


class WorkOrderCreate(WorkOrderBase):
    pass


class WorkOrderUpdate(BaseModel):
    title: str | None = None
    equipment_id: int | None = None
    fault_description: str | None = None
    fault_code_id: int | None = None
    order_type: WorkOrderTypeEnum | None = None
    priority: PriorityEnum | None = None
    safety_risk: str | None = None
    acceptance_criteria: str | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None


class AssignRequest(BaseModel):
    assignee_id: int
    priority: PriorityEnum | None = None
    planned_end_at: datetime | None = None


class SubmitRequest(BaseModel):
    root_cause: str
    action_taken: str
    replaced_parts: str | None = None
    test_result: str
    equipment_status_after: str | None = None
    follow_up_advice: str | None = None
    needs_observation: bool = False
    completion_photos: list[str] | None = None


class RejectRequest(BaseModel):
    remark: str


class WorkOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    title: str
    equipment_id: int | None = None
    equipment_name: str | None = None
    equipment_code: str | None = None
    fault_report_id: int | None = None
    fault_description: str | None = None
    fault_code_id: int | None = None
    fault_code: str | None = None
    order_type: WorkOrderTypeEnum
    priority: PriorityEnum
    status: WorkOrderStatusEnum
    created_by_id: int | None = None
    creator_name: str | None = None
    assignee_id: int | None = None
    assignee_name: str | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    actual_start_at: datetime | None = None
    actual_end_at: datetime | None = None
    safety_risk: str | None = None
    ai_diagnosis_summary: str | None = None
    maintenance_steps: list[Any] | None = None
    acceptance_criteria: str | None = None
    root_cause: str | None = None
    action_taken: str | None = None
    replaced_parts: str | None = None
    test_result: str | None = None
    equipment_status_after: str | None = None
    follow_up_advice: str | None = None
    needs_observation: bool
    completion_photos: list[str] | None = None
    rejection_reason: str | None = None
    submitted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkOrderDetail(WorkOrderOut):
    checklist_items: list[ChecklistItemOut] = []
    logs: list[MaintenanceLogOut] = []
    labor_entries: list[LaborEntryOut] = []
    spare_parts: list[SparePartUsageOut] = []
    status_history: list[dict] = []


class StatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    from_status: str | None = None
    to_status: str
    changed_by: int | None = None
    changed_at: datetime | None = None
    remark: str | None = None


# ---- 维修报告 ----


class ReportSectionOut(BaseModel):
    title: str
    content: str


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    work_order_id: int
    version: int
    generation_method: str
    summary: str
    sections: list[dict] | None = None
    is_current: bool
    generated_by: int | None = None
    created_at: datetime | None = None


class ReportGenerateResponse(BaseModel):
    work_order_id: int
    work_order_code: str
    summary: str
    sections: list[ReportSectionOut] = []
    generation_method: str
    version: int
    is_mock: bool = True


class AcceptRequest(BaseModel):
    acceptance_notes: str | None = None
    equipment_verified: bool = True
    safety_verified: bool = True
