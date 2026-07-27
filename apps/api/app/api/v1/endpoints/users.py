"""用户与维修工程师接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import admin_only, get_current_user, supervisor_or_admin
from app.core.exceptions import paginate
from app.db.session import get_db
from app.models.base import RoleEnum, WorkOrderStatusEnum
from app.models.user import Skill, TechnicianProfile, User
from app.models.workorder import WorkOrder
from app.schemas.common import PageOut
from app.schemas.user import TechnicianOut, UserCreate, UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=PageOut[UserOut])
def list_users(
    role: RoleEnum | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    if keyword:
        q = q.filter(User.full_name.contains(keyword) | User.email.contains(keyword))
    items, total = paginate(q, page, page_size)
    return PageOut(items=[UserOut.model_validate(u) for u in items], total=total, page=page, page_size=page_size)


@router.post("", response_model=UserOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db), user=Depends(admin_only)):
    from app.core.security import hash_password

    if db.query(User).filter(User.email == payload.email).first():
        from app.core.exceptions import conflict

        raise conflict("邮箱已存在")
    u = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        role=payload.role,
        is_active=payload.is_active,
        created_by=str(user.id),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return UserOut.model_validate(u)


@router.get("/technicians", response_model=list[TechnicianOut])
def list_technicians(db: Session = Depends(get_db), _=Depends(get_current_user)):
    profiles = db.query(TechnicianProfile).all()
    result: list[TechnicianOut] = []
    for p in profiles:
        active = (
            db.query(WorkOrder)
            .filter(WorkOrder.assignee_id == p.user_id)
            .filter(WorkOrder.status.in_([WorkOrderStatusEnum.assigned, WorkOrderStatusEnum.accepted, WorkOrderStatusEnum.in_progress]))
            .count()
        )
        today_done = 0  # 简化：完成数
        result.append(
            TechnicianOut(
                id=p.id,
                user_id=p.user_id,
                employee_no=p.employee_no,
                availability=p.availability,
                max_concurrent=p.max_concurrent,
                full_name=p.user.full_name,
                email=p.user.email,
                skills=[SkillOut.model_validate(s) for s in p.skills],
                active_work_orders=active,
                completed_today=today_done,
            )
        )
    return result


from app.schemas.user import SkillOut  # noqa: E402
