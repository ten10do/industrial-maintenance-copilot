"""为工业事件链路追踪添加 trace_id 列与索引。

Revision ID: 20260824_07
Revises: 20260824_06

设计：

- ``trace_id``（String(36)，可空，索引，非唯一）：
  同一次工业事件链（OPC UA DataChange → Telemetry → Anomaly →
  Prediction → Alarm → Analysis → Agent → Work Order → Approval）
  的所有领域记录共享同一 trace_id；
- 历史数据保持 NULL，不做回填（append-only，保留既有数据）；
- 幂等：逐表检查列/索引是否存在，全新库与存量库均可升级。
"""

from typing import NoReturn

import sqlalchemy as sa

from alembic import op

revision = "20260824_07"
down_revision = "20260824_06"
branch_labels = None
depends_on = None

# 表名 → 索引名
_TARGETS: list[tuple[str, str]] = [
    ("telemetry_records", "ix_telemetry_records_trace_id"),
    ("anomaly_events", "ix_anomaly_events_trace_id"),
    ("risk_predictions", "ix_risk_predictions_trace_id"),
    ("maintenance_recommendations", "ix_maintenance_recommendations_trace_id"),
    ("industrial_alarms", "ix_industrial_alarms_trace_id"),
    ("alarm_analysis_records", "ix_alarm_analysis_records_trace_id"),
    ("work_orders", "ix_work_orders_trace_id"),
    ("operation_approvals", "ix_operation_approvals_trace_id"),
    ("agent_runs", "ix_agent_runs_trace_id"),
]


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _column_exists(bind: sa.engine.Connection, table_name: str, column: str) -> bool:
    return any(
        col["name"] == column for col in sa.inspect(bind).get_columns(table_name)
    )


def _index_exists(bind: sa.engine.Connection, table_name: str, index_name: str) -> bool:
    return any(
        idx["name"] == index_name for idx in sa.inspect(bind).get_indexes(table_name)
    )


def upgrade() -> None:
    bind = op.get_bind()
    for table_name, index_name in _TARGETS:
        if not _table_exists(bind, table_name):
            continue
        if not _column_exists(bind, table_name, "trace_id"):
            op.add_column(
                table_name,
                sa.Column("trace_id", sa.String(length=36), nullable=True),
            )
        if not _index_exists(bind, table_name, index_name):
            op.create_index(index_name, table_name, ["trace_id"])


def downgrade() -> NoReturn:
    raise RuntimeError(
        "trace_id 列不支持自动降级（可能已承载链路追踪数据）；"
        "如确需删除请手工处理并确认无业务依赖"
    )
