"""建立可接管既有数据库的 Alembic 基线。

Revision ID: 20260811_01
Revises:
"""

from typing import NoReturn

from alembic import op
from app.db.migrations import upgrade_schema

revision = "20260811_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    upgrade_schema(op.get_bind())


def downgrade() -> NoReturn:
    raise RuntimeError(
        "基线迁移可能接管既有生产库，不支持破坏性降级；请回滚应用并保留数据库结构"
    )
