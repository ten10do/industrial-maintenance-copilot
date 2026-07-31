"""集中导入所有模型，便于 Alembic 与 create_all 发现表结构。"""
from app.models.base import (
    AIInteractionTypeEnum,
    AIStatusEnum,
    EquipmentStatusEnum,
    FaultReportStatusEnum,
    KnowledgeCategoryEnum,
    MaintenanceLogTypeEnum,
    PriorityEnum,
    RiskLevelEnum,
    RoleEnum,
    UrgencyEnum,
    WorkOrderStatusEnum,
    WorkOrderTypeEnum,
)
from app.models.equipment import Equipment, EquipmentType, FaultCode, SparePart
from app.models.fault import FaultReport
from app.models.knowledge import (
    AcceptanceRecord,
    AIInteraction,
    KnowledgeArticle,
    KnowledgeChunk,
    Notification,
)
from app.models.maintenance import (
    Attachment,
    LaborEntry,
    MaintenanceLog,
    WorkOrderReport,
    WorkOrderSparePart,
)
from app.models.user import Skill, TechnicianProfile, User
from app.models.workorder import (
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderChecklistItem,
    WorkOrderStatusHistory,
)

__all__ = [
    "RoleEnum",
    "EquipmentStatusEnum",
    "RiskLevelEnum",
    "UrgencyEnum",
    "FaultReportStatusEnum",
    "WorkOrderTypeEnum",
    "PriorityEnum",
    "WorkOrderStatusEnum",
    "MaintenanceLogTypeEnum",
    "KnowledgeCategoryEnum",
    "AIInteractionTypeEnum",
    "AIStatusEnum",
    "User",
    "Skill",
    "TechnicianProfile",
    "Equipment",
    "EquipmentType",
    "FaultCode",
    "SparePart",
    "FaultReport",
    "WorkOrder",
    "WorkOrderAssignment",
    "WorkOrderStatusHistory",
    "WorkOrderChecklistItem",
    "MaintenanceLog",
    "LaborEntry",
    "WorkOrderSparePart",
    "WorkOrderReport",
    "Attachment",
    "KnowledgeArticle",
    "KnowledgeChunk",
    "AIInteraction",
    "AcceptanceRecord",
    "Notification",
]
