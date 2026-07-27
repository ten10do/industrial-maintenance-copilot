"""设备、设备类型、故障代码、备件 schema。"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.base import EquipmentStatusEnum, RiskLevelEnum


class EquipmentTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None = None


class EquipmentTypeCreate(BaseModel):
    name: str
    description: str | None = None


class EquipmentBase(BaseModel):
    code: str
    name: str
    equipment_type_id: int | None = None
    plant: str | None = None
    production_line: str | None = None
    location: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    commissioning_date: date | None = None
    status: EquipmentStatusEnum = EquipmentStatusEnum.running
    risk_level: RiskLevelEnum = RiskLevelEnum.medium
    responsible_person_id: int | None = None
    remarks: str | None = None


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentUpdate(BaseModel):
    name: str | None = None
    equipment_type_id: int | None = None
    plant: str | None = None
    production_line: str | None = None
    location: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    commissioning_date: date | None = None
    status: EquipmentStatusEnum | None = None
    risk_level: RiskLevelEnum | None = None
    responsible_person_id: int | None = None
    last_maintenance_at: date | None = None
    remarks: str | None = None


class EquipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    equipment_type_id: int | None = None
    equipment_type_name: str | None = None
    plant: str | None = None
    production_line: str | None = None
    location: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    commissioning_date: date | None = None
    status: EquipmentStatusEnum
    risk_level: RiskLevelEnum
    responsible_person_id: int | None = None
    responsible_person_name: str | None = None
    last_maintenance_at: date | None = None
    qr_token: str
    remarks: str | None = None
    created_at: datetime | None = None


class FaultCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    description: str | None = None
    severity: str
    equipment_type_id: int | None = None


class FaultCodeCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    severity: str = "medium"
    equipment_type_id: int | None = None


class SparePartOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    specification: str | None = None
    unit: str
    stock_qty: int
    remarks: str | None = None


class SparePartCreate(BaseModel):
    code: str
    name: str
    specification: str | None = None
    unit: str = "个"
    stock_qty: int = 0
    remarks: str | None = None
