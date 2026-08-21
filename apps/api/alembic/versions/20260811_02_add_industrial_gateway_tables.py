"""新增工业网关表：gateway_connections / opcua_node_mappings。

Revision ID: 20260811_02
Revises: 20260811_01

幂等设计：基线迁移（20260811_01）通过 ``Base.metadata.create_all`` 建表，
在全新数据库上这两张表可能已存在，因此这里先检查再创建，
保证「全新库」与「已停在 20260811_01 的存量库」都能升级到 head。
"""

from typing import NoReturn

import sqlalchemy as sa
from alembic import op

revision = "20260811_02"
down_revision = "20260811_01"
branch_labels = None
depends_on = None

_CONNECTION_TABLE = "gateway_connections"
_MAPPING_TABLE = "opcua_node_mappings"


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(bind: sa.engine.Connection, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(
        index["name"] == index_name for index in inspector.get_indexes(table_name)
    )


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, _CONNECTION_TABLE):
        op.create_table(
            _CONNECTION_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("protocol", sa.String(length=24), nullable=False),
            sa.Column("endpoint", sa.String(length=255), nullable=False),
            sa.Column("mode", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("poll_interval_seconds", sa.Float(), nullable=False),
            sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
        )
        op.create_index(
            "ix_gateway_connections_name", _CONNECTION_TABLE, ["name"], unique=True
        )
        op.create_index(
            "ix_gateway_connections_protocol", _CONNECTION_TABLE, ["protocol"]
        )
        op.create_index(
            "ix_gateway_connections_status", _CONNECTION_TABLE, ["status"]
        )

    if not _table_exists(bind, _MAPPING_TABLE):
        op.create_table(
            _MAPPING_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("node_id", sa.String(length=160), nullable=False),
            sa.Column("equipment_id", sa.Integer(), nullable=False),
            sa.Column("metric_name", sa.String(length=64), nullable=False),
            sa.Column("unit", sa.String(length=24), nullable=False),
            sa.Column("scale", sa.Float(), nullable=False),
            sa.Column("offset", sa.Float(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("informational", sa.Boolean(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.ForeignKeyConstraint(
                ["equipment_id"], ["equipment.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint(
                "equipment_id",
                "metric_name",
                name="uq_opcua_node_mapping_equipment_metric",
            ),
        )
        op.create_index(
            "ix_opcua_node_mappings_node_id", _MAPPING_TABLE, ["node_id"], unique=True
        )
        op.create_index(
            "ix_opcua_node_mappings_equipment_id", _MAPPING_TABLE, ["equipment_id"]
        )
        op.create_index(
            "ix_opcua_node_mappings_metric_name", _MAPPING_TABLE, ["metric_name"]
        )
    elif not _index_exists(
        bind, _MAPPING_TABLE, "ix_opcua_node_mappings_node_id"
    ):
        op.create_index(
            "ix_opcua_node_mappings_node_id", _MAPPING_TABLE, ["node_id"], unique=True
        )


def downgrade() -> NoReturn:
    raise RuntimeError(
        "工业网关表不支持破坏性降级（可能包含现场映射配置）；"
        "如确需删除请手工处理并确认无业务依赖"
    )
