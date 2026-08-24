"""补齐报警智能分析风险、复核、追踪与工单关联字段。

Revision ID: 20260824_06
Revises: 20260811_05

仅追加列与索引；保留既有分析记录。列检查使迁移同时兼容 SQLite 与
PostgreSQL，并适配基线 ``Base.metadata.create_all`` 已提前创建字段的仓库策略。
"""

from typing import NoReturn

import sqlalchemy as sa

from alembic import op

revision = "20260824_06"
down_revision = "20260811_05"
branch_labels = None
depends_on = None

_TABLE = "alarm_analysis_records"

_COLUMNS = (
    sa.Column("created_work_order_id", sa.Integer(), nullable=True),
    sa.Column(
        "risk_level",
        sa.String(length=16),
        nullable=False,
        server_default="MEDIUM",
    ),
    sa.Column(
        "analysis_status",
        sa.String(length=32),
        nullable=False,
        server_default="NEW",
    ),
    sa.Column("review_status", sa.String(length=32), nullable=True),
    sa.Column("reviewed_by", sa.Integer(), nullable=True),
    sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("review_note", sa.Text(), nullable=True),
    sa.Column("agent_run_id", sa.Integer(), nullable=True),
)

_INDEXES = {
    "ix_alarm_analysis_records_created_work_order_id": ["created_work_order_id"],
    "ix_alarm_analysis_records_risk_level": ["risk_level"],
    "ix_alarm_analysis_records_analysis_status": ["analysis_status"],
    "ix_alarm_analysis_records_review_status": ["review_status"],
    "ix_alarm_analysis_records_agent_run_id": ["agent_run_id"],
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in _COLUMNS:
        if column.name not in existing_columns:
            op.add_column(_TABLE, column)
    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes(_TABLE)}
    for name, columns in _INDEXES.items():
        if name not in existing_indexes:
            op.create_index(name, _TABLE, columns)
    if bind.dialect.name != "sqlite":
        existing_fks = {
            foreign_key["name"]
            for foreign_key in sa.inspect(bind).get_foreign_keys(_TABLE)
        }
        constraints = (
            (
                "fk_alarm_analysis_created_work_order",
                "work_orders",
                ["created_work_order_id"],
            ),
            ("fk_alarm_analysis_reviewer", "users", ["reviewed_by"]),
            ("fk_alarm_analysis_agent_run", "agent_runs", ["agent_run_id"]),
        )
        for name, referred_table, local_columns in constraints:
            if name not in existing_fks:
                op.create_foreign_key(
                    name,
                    _TABLE,
                    referred_table,
                    local_columns,
                    ["id"],
                    ondelete="SET NULL",
                )


def downgrade() -> NoReturn:
    raise RuntimeError(
        "报警智能分析工作流字段不支持破坏性降级；"
        "如确需删除请手工处理并确认分析、复核与工单关联数据已备份"
    )
