"""仪表盘 schema。"""
from __future__ import annotations

from pydantic import BaseModel


class SupervisorDashboard(BaseModel):
    pending_dispatch: int
    in_progress: int
    pending_acceptance: int
    overdue: int
    today_new_faults: int
    today_completed: int
    avg_repair_hours: float | None
    total_downtime_hours: float
    by_priority: list[dict]
    by_equipment_type: list[dict]
    recent_work_orders: list[dict]


class TechnicianDashboard(BaseModel):
    assigned_to_me: int
    today_todo: int
    high_priority: int
    overdue: int
    my_work_orders: list[dict]
    recent_logs: list[dict]
