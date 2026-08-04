"""v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    copilot,
    dashboard,
    equipment,
    fault_reports,
    files,
    intelligence,
    knowledge,
    ml,
    users,
    work_orders,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(equipment.router)
api_router.include_router(equipment.types_router)
api_router.include_router(equipment.fault_codes_router)
api_router.include_router(equipment.spare_parts_router)
api_router.include_router(fault_reports.router)
api_router.include_router(work_orders.router)
api_router.include_router(copilot.router)
api_router.include_router(knowledge.router)
api_router.include_router(intelligence.router)
api_router.include_router(ml.router)
api_router.include_router(dashboard.router)
api_router.include_router(files.router)
