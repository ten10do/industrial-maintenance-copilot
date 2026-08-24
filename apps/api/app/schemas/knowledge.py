"""知识库与 Copilot schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.base import KnowledgeCategoryEnum


class KnowledgeArticleBase(BaseModel):
    title: str
    category: KnowledgeCategoryEnum = KnowledgeCategoryEnum.experience
    content: str
    summary: str | None = None
    tags: list[str] | None = None
    equipment_type_id: int | None = None
    fault_code_id: int | None = None
    source: str | None = None
    status: str = "published"


class KnowledgeArticleCreate(KnowledgeArticleBase):
    pass


class KnowledgeArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    category: KnowledgeCategoryEnum
    content: str
    summary: str | None = None
    tags: list[str] | None = None
    equipment_type_id: int | None = None
    fault_code_id: int | None = None
    source: str | None = None
    status: str
    view_count: int
    created_at: datetime | None = None


# ---- Copilot ----


class DiagnoseRequest(BaseModel):
    work_order_id: int | None = None
    fault_description: str
    equipment_id: int | None = None
    fault_code: str | None = None


class SimilarCase(BaseModel):
    work_order_id: int
    code: str
    title: str
    similarity: float
    root_cause: str | None = None
    action_taken: str | None = None


class DiagnoseResult(BaseModel):
    possible_causes: list[dict[str, Any]] = []
    inspection_order: list[str] = []
    safety_notes: list[str] = []
    recommended_tools: list[str] = []
    recommended_parts: list[str] = []
    similar_cases: list[SimilarCase] = []
    disclaimer: str = (
        "AI 建议仅供辅助，维修人员应依据现场情况、设备手册和安全规范进行判断。"
    )
    is_mock: bool = True


class RewriteLogRequest(BaseModel):
    content: str
    log_type: str | None = None


class RewriteLogResult(BaseModel):
    original: str
    polished: str
    is_mock: bool = True


class GenerateReportRequest(BaseModel):
    work_order_id: int


class ReportSection(BaseModel):
    title: str
    content: str


class MaintenanceReport(BaseModel):
    work_order_id: int
    work_order_code: str
    sections: list[ReportSection] = []
    summary: str
    is_mock: bool = True


class AskRequest(BaseModel):
    question: str
    equipment_type_id: int | None = None
    fault_code: str | None = None


class Citation(BaseModel):
    """Copilot 回答中的结构化引用来源。"""

    source_type: str  # "knowledge_article" | "work_order" | "equipment"
    source_id: int
    title: str
    excerpt: str | None = None
    relevance_score: float = 0.0
    url: str | None = None


class AskResult(BaseModel):
    answer: str
    confidence: float = 0.0
    citations: list[Citation] = []
    warnings: list[str] = []
    is_mock: bool = True
    disclaimer: str = "以上内容来自知识库检索与 AI 生成，仅供参考，不构成强制维修指令。"


class HistorySummary(BaseModel):
    equipment_id: int
    equipment_name: str
    total_work_orders: int
    frequent_faults: list[dict[str, Any]] = []
    recent_faults: list[dict[str, Any]] = []
    repeated_faults: list[dict[str, Any]] = []
    common_parts: list[dict[str, Any]] = []
    avg_repair_hours: float | None = None
    is_mock: bool = True
