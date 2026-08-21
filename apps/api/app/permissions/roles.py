"""权限校验工具。"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.models.base import RoleEnum


def require_roles(*roles: RoleEnum):
    """依赖工厂：校验当前用户角色是否在允许列表内。"""

    def _check(user) -> object:
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="未认证"
            )
        if RoleEnum(user.role) not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="权限不足"
            )
        return user

    return _check
