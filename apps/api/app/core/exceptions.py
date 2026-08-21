"""统一异常与分页工具。"""

from __future__ import annotations

from typing import Generic, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel

T = TypeVar("T")


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None
    work_order_id: int | None = None
    missing_requirements: list[str] | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


def not_found(msg: str = "资源不存在") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)


def forbidden(msg: str = "权限不足") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)


def bad_request(msg: str = "请求参数有误") -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


def conflict(msg: str = "操作冲突") -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)


def paginate(query, page: int, page_size: int) -> tuple[list, int]:
    page = max(page, 1)
    page_size = max(min(page_size, 200), 1)
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, total
