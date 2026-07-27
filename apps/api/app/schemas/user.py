"""认证与用户 schema。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.base import RoleEnum


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    phone: str | None = None
    role: RoleEnum = RoleEnum.technician
    is_active: bool = True


class UserCreate(UserBase):
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    phone: str | None = None
    role: RoleEnum
    is_active: bool
    created_at: datetime | None = None


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    category: str | None = None


class TechnicianOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    employee_no: str | None = None
    availability: str
    max_concurrent: int
    full_name: str | None = None
    email: str | None = None
    skills: list[SkillOut] = []
    active_work_orders: int = 0
    completed_today: int = 0
