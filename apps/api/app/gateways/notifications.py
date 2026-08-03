"""消息通知 Gateway；首期使用站内通知，后续可接企业消息服务。"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.models.knowledge import Notification


class NotificationGateway(Protocol):
    def send(
        self,
        db: Session,
        *,
        user_id: int | None,
        title: str,
        content: str,
        level: str = "info",
        link: str | None = None,
    ) -> None: ...


class DatabaseNotificationGateway:
    def send(
        self,
        db: Session,
        *,
        user_id: int | None,
        title: str,
        content: str,
        level: str = "info",
        link: str | None = None,
    ) -> None:
        db.add(
            Notification(
                user_id=user_id,
                title=title,
                content=content,
                type=level,
                link=link,
            )
        )


notification_gateway: NotificationGateway = DatabaseNotificationGateway()
