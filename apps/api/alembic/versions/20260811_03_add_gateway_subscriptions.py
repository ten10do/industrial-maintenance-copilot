"""新增 DataChange 订阅表：gateway_subscriptions。

Revision ID: 20260811_03
Revises: 20260811_02

幂等设计：基线迁移通过 ``Base.metadata.create_all`` 建表，在全新数据库上
该表可能已存在，因此先检查再创建，保证「全新库」与「已停在 20260811_02
的存量库」都能升级到 head。
"""

from typing import NoReturn

import sqlalchemy as sa
from alembic import op

revision = "20260811_03"
down_revision = "20260811_02"
branch_labels = None
depends_on = None

_TABLE = "gateway_subscriptions"


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, _TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("gateway_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(length=160), nullable=False),
        sa.Column("sampling_interval", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["gateway_id"], ["gateway_connections.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "gateway_id", "node_id", name="uq_gateway_subscription_gateway_node"
        ),
    )
    op.create_index(
        "ix_gateway_subscriptions_gateway_id", _TABLE, ["gateway_id"]
    )
    op.create_index("ix_gateway_subscriptions_node_id", _TABLE, ["node_id"])
    op.create_index("ix_gateway_subscriptions_status", _TABLE, ["status"])


def downgrade() -> NoReturn:
    raise RuntimeError(
        "订阅表不支持破坏性降级；如确需删除请手工处理并确认无业务依赖"
    )
