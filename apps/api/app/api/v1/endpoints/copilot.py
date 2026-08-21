"""Copilot 接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.copilot import (
    ask as ai_ask,
)
from app.ai.copilot import (
    diagnose as ai_diagnose,
)
from app.ai.copilot import (
    generate_report as ai_report,
)
from app.ai.copilot import (
    history_summary as ai_history,
)
from app.ai.copilot import (
    rewrite_log as ai_rewrite,
)
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.workorder import WorkOrder
from app.schemas.knowledge import (
    AskRequest,
    AskResult,
    DiagnoseRequest,
    DiagnoseResult,
    GenerateReportRequest,
    HistorySummary,
    MaintenanceReport,
    RewriteLogRequest,
    RewriteLogResult,
)

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.post("/diagnose", response_model=DiagnoseResult)
def diagnose(
    payload: DiagnoseRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    wo = None
    if payload.work_order_id:
        wo = db.get(WorkOrder, payload.work_order_id)
    return ai_diagnose(
        db,
        payload.fault_description,
        payload.equipment_id,
        payload.fault_code,
        wo,
        user.id,
    )


@router.post("/rewrite-maintenance-log", response_model=RewriteLogResult)
def rewrite_log(
    payload: RewriteLogRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return ai_rewrite(db, payload.content, user.id)


@router.post("/generate-report", response_model=MaintenanceReport)
def generate_report(
    payload: GenerateReportRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return ai_report(db, payload.work_order_id, user.id)


@router.post("/ask", response_model=AskResult)
def ask(
    payload: AskRequest, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    return ai_ask(
        db, payload.question, payload.equipment_type_id, payload.fault_code, user.id
    )


@router.get("/equipment-history/{equipment_id}", response_model=HistorySummary)
def equipment_history(
    equipment_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    return ai_history(db, equipment_id)
