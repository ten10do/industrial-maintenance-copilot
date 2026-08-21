"""认证接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.demo import is_demo_account
from app.core.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Token
from app.schemas.user import LoginRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    if not settings.is_development and is_demo_account(str(payload.email)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误"
        )
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误"
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
    token = create_access_token(
        user.id, extra={"role": user.role.value, "name": user.full_name}
    )
    return Token(
        access_token=token,
        role=user.role.value,
        user_id=user.id,
        full_name=user.full_name,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
