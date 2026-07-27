"""用户、角色、维修工程师档案、技能。"""
from __future__ import annotations

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import AuditMixin, RoleEnum, TimestampMixin, gen_uuid

# 技能 多对多 关联
technician_skill = Table(
    "technician_skill",
    Base.metadata,
    Column("technician_id", Integer, ForeignKey("technician_profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", Integer, ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
)


class User(AuditMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), default=RoleEnum.technician, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    profile: Mapped["TechnicianProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Skill(TimestampMixin, Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TechnicianProfile(TimestampMixin, Base):
    __tablename__ = "technician_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    employee_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    availability: Mapped[str] = mapped_column(String(32), default="available")  # available / busy / off
    max_concurrent: Mapped[int] = mapped_column(Integer, default=5)

    user: Mapped["User"] = relationship(back_populates="profile")
    skills: Mapped[list["Skill"]] = relationship(secondary=technician_skill)
