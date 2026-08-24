"""知识库文章与分块、AI 交互记录、验收记录、通知。"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import (
    AIInteractionTypeEnum,
    AIStatusEnum,
    AuditMixin,
    KnowledgeCategoryEnum,
    TimestampMixin,
)


class KnowledgeArticle(AuditMixin, Base):
    __tablename__ = "knowledge_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[KnowledgeCategoryEnum] = mapped_column(
        Enum(KnowledgeCategoryEnum),
        default=KnowledgeCategoryEnum.experience,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    equipment_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipment_types.id", ondelete="SET NULL"), nullable=True
    )
    fault_code_id: Mapped[int | None] = mapped_column(
        ForeignKey("fault_codes.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default="published"
    )  # draft / published
    view_count: Mapped[int] = mapped_column(Integer, default=0)

    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class KnowledgeChunk(TimestampMixin, Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    # 向量以 JSON 存储（兼容 SQLite / PostgreSQL）。启用 pgvector 时可迁移为向量列。
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)

    article: Mapped[KnowledgeArticle] = relationship(back_populates="chunks")


class AIInteraction(TimestampMixin, Base):
    __tablename__ = "ai_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    interaction_type: Mapped[AIInteractionTypeEnum] = mapped_column(
        Enum(AIInteractionTypeEnum), index=True
    )
    request: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AIStatusEnum] = mapped_column(
        Enum(AIStatusEnum), default=AIStatusEnum.mock
    )
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AcceptanceRecord(TimestampMixin, Base):
    __tablename__ = "acceptance_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), index=True
    )
    result: Mapped[str] = mapped_column(String(16))  # approved / rejected
    reviewer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(32), default="info")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)
