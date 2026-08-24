"""新增报警智能分析表：alarm_analysis_records。

Revision ID: 20260811_05
Revises: 20260811_04

幂等设计：基线迁移通过 ``Base.metadata.create_all`` 建表，在全新数据库上
该表可能已存在，因此先检查再创建，保证「全新库」与「已停在 20260811_04
的存量库」都能升级到 head。
"""

from typing import NoReturn

import sqlalchemy as sa

from alembic import op

revision = "20260811_05"
down_revision = "20260811_04"
branch_labels = None
depends_on = None

_TABLE = "alarm_analysis_records"


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, _TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alarm_id", sa.Integer(), nullable=False),
        sa.Column("correlation_group_id", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("root_cause_hypothesis", sa.Text(), nullable=False),
        sa.Column("contributing_factors", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("recommended_actions", sa.JSON(), nullable=False),
        sa.Column("suggested_priority", sa.String(length=8), nullable=False),
        sa.Column("related_work_order_id", sa.Integer(), nullable=True),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False),
        sa.Column("model_version", sa.String(length=48), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["alarm_id"], ["industrial_alarms.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["related_work_order_id"], ["work_orders.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_alarm_analysis_records_alarm_id", _TABLE, ["alarm_id"], unique=True
    )
    op.create_index(
        "ix_alarm_analysis_records_correlation_group_id",
        _TABLE,
        ["correlation_group_id"],
    )


def downgrade() -> NoReturn:
    raise RuntimeError(
        "报警分析记录不支持破坏性降级（可能包含分析历史）；"
        "如确需删除请手工处理并确认无业务依赖"
    )
