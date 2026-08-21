"""新增工业报警表：industrial_alarms。

Revision ID: 20260811_04
Revises: 20260811_03

幂等设计：基线迁移通过 ``Base.metadata.create_all`` 建表，在全新数据库上
该表可能已存在，因此先检查再创建，保证「全新库」与「已停在 20260811_03
的存量库」都能升级到 head。
"""

from typing import NoReturn

import sqlalchemy as sa
from alembic import op

revision = "20260811_04"
down_revision = "20260811_03"
branch_labels = None
depends_on = None

_TABLE = "industrial_alarms"


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, _TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.Integer(), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["equipment_id"], ["equipment.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_industrial_alarms_equipment_id", _TABLE, ["equipment_id"])
    op.create_index("ix_industrial_alarms_severity", _TABLE, ["severity"])
    op.create_index("ix_industrial_alarms_source", _TABLE, ["source"])
    op.create_index("ix_industrial_alarms_acknowledged", _TABLE, ["acknowledged"])
    op.create_index("ix_industrial_alarms_cleared_at", _TABLE, ["cleared_at"])


def downgrade() -> NoReturn:
    raise RuntimeError(
        "工业报警表不支持破坏性降级（可能包含现场报警历史）；"
        "如确需删除请手工处理并确认无业务依赖"
    )
