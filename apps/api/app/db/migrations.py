"""可重复执行的兼容迁移。

项目早期通过 SQLAlchemy ``create_all`` 建库，没有可安全接管既有生产库的 Alembic
revision。这里保留增量升级器作为当前迁移入口；降级只移除新平台表，不删除旧工单数据，
也不回删兼容性新增列。
"""

from __future__ import annotations

import uuid
from contextlib import nullcontext

from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.schema import DropTable

_CHECKLIST_CATEGORIES = {
    "safety": [
        "设备已停机",
        "相关能源已切断",
        "已执行上锁挂牌（LOTO）",
        "残余能量已释放",
        "安全联锁状态已确认",
        "现场警示已设置",
        "个人防护用品已佩戴",
        "确认设备已停机",
        "执行断电操作",
        "执行上锁挂牌（LOTO）",
        "确认残余能量已释放",
    ],
    "diagnosis": ["读取并记录故障代码", "检查相关部件状态"],
    "testing": ["空载测试", "负载测试", "确认设备恢复正常"],
}

INTELLIGENT_MAINTENANCE_TABLES = (
    "equipment_sensors",
    "telemetry_records",
    "anomaly_events",
    "fault_diagnoses",
    "risk_predictions",
    "maintenance_recommendations",
    "spare_part_reservations",
    "operation_approvals",
    "operation_execution_audits",
    "maintenance_verifications",
    "agent_runs",
    "tool_invocations",
    "ml_dataset_versions",
    "ml_feature_definitions",
    "ml_training_runs",
    "ml_model_versions",
    "ml_model_metrics",
    "ml_prediction_records",
)

_INTELLIGENCE_DROP_ORDER = tuple(reversed(INTELLIGENT_MAINTENANCE_TABLES))


def upgrade_schema(engine: Engine | Connection) -> list[str]:
    """升级到当前 head，返回本次实际应用的迁移名称。"""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    applied: list[str] = []

    transaction = (
        nullcontext(engine) if isinstance(engine, Connection) else engine.begin()
    )
    with transaction as connection:
        if "work_order_checklist_items" in table_names:
            columns = {
                column["name"]
                for column in inspector.get_columns("work_order_checklist_items")
            }
            if "category" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE work_order_checklist_items "
                        "ADD COLUMN category VARCHAR(32) NOT NULL DEFAULT 'repair'"
                    )
                )
                applied.append("work_order_checklist_items.category")

            backfilled = False
            for category, contents in _CHECKLIST_CATEGORIES.items():
                for content in contents:
                    result = connection.execute(
                        text(
                            "UPDATE work_order_checklist_items "
                            "SET category = :category "
                            "WHERE content = :content AND category = 'repair'"
                        ),
                        {"category": category, "content": content},
                    )
                    backfilled = bool(result.rowcount) or backfilled
            if backfilled:
                applied.append("work_order_checklist_items.category_backfill")

        if "equipment" in table_names:
            equipment_columns = {
                column["name"] for column in inspector.get_columns("equipment")
            }
            additions = {
                "asset_uuid": "VARCHAR(32)",
                "next_maintenance_at": "DATE",
                "health_score": "FLOAT NOT NULL DEFAULT 100",
                "rated_parameters": "JSON",
                "cumulative_runtime_hours": "FLOAT NOT NULL DEFAULT 0",
            }
            for column_name, sql_type in additions.items():
                if column_name not in equipment_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE equipment ADD COLUMN {column_name} {sql_type}"
                        )
                    )
                    applied.append(f"equipment.{column_name}")

            rows = connection.execute(
                text("SELECT id FROM equipment WHERE asset_uuid IS NULL")
            ).all()
            for row in rows:
                stable_uuid = uuid.uuid5(
                    uuid.NAMESPACE_URL, f"industrial-maintenance-equipment:{row.id}"
                ).hex
                connection.execute(
                    text(
                        "UPDATE equipment SET asset_uuid = :asset_uuid WHERE id = :id"
                    ),
                    {"asset_uuid": stable_uuid, "id": row.id},
                )
            if rows:
                applied.append("equipment.asset_uuid_backfill")

            if connection.dialect.name == "postgresql":
                for enum_value in ("idle", "warning", "maintenance", "offline"):
                    connection.execute(
                        text(
                            "ALTER TYPE equipmentstatusenum "
                            f"ADD VALUE IF NOT EXISTS '{enum_value}'"
                        )
                    )

        if "ml_dataset_versions" in table_names:
            dataset_columns = {
                column["name"]
                for column in inspector.get_columns("ml_dataset_versions")
            }
            if "processed_sha256" not in dataset_columns:
                connection.execute(
                    text(
                        "ALTER TABLE ml_dataset_versions "
                        "ADD COLUMN processed_sha256 VARCHAR(64)"
                    )
                )
                applied.append("ml_dataset_versions.processed_sha256")

        if "operation_approvals" in table_names:
            approval_columns = {
                column["name"]
                for column in inspector.get_columns("operation_approvals")
            }
            if "execution_key" not in approval_columns:
                connection.execute(
                    text(
                        "ALTER TABLE operation_approvals "
                        "ADD COLUMN execution_key VARCHAR(64)"
                    )
                )
                approval_ids = connection.execute(
                    text("SELECT id FROM operation_approvals")
                ).scalars()
                for approval_id in approval_ids:
                    execution_key = uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"industrial-maintenance-operation-approval:{approval_id}",
                    ).hex
                    connection.execute(
                        text(
                            "UPDATE operation_approvals "
                            "SET execution_key = :execution_key WHERE id = :id"
                        ),
                        {"execution_key": execution_key, "id": approval_id},
                    )
                applied.append("operation_approvals.execution_key")
            datetime_sql = (
                "TIMESTAMP WITH TIME ZONE"
                if connection.dialect.name == "postgresql"
                else "DATETIME"
            )
            reconciliation_additions = {
                "execution_started_at": datetime_sql,
                "execution_attempt": "INTEGER NOT NULL DEFAULT 0",
                "reconciliation_outcome": "VARCHAR(32)",
                "reconciliation_note": "TEXT",
                "observed_device_state": "TEXT",
                "reconciled_by": "INTEGER",
                "reconciled_at": datetime_sql,
            }
            reconciliation_added = False
            for column_name, sql_type in reconciliation_additions.items():
                if column_name not in approval_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE operation_approvals "
                            f"ADD COLUMN {column_name} {sql_type}"
                        )
                    )
                    reconciliation_added = True
            if reconciliation_added and {"status", "reviewed_at"}.issubset(
                approval_columns
            ):
                connection.execute(
                    text(
                        "UPDATE operation_approvals "
                        "SET execution_started_at = reviewed_at "
                        "WHERE status = 'executing' "
                        "AND execution_started_at IS NULL"
                    )
                )
            if reconciliation_added:
                applied.append("operation_approvals.execution_reconciliation")
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "ix_operation_approvals_execution_key "
                    "ON operation_approvals (execution_key)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_operation_approvals_execution_started_at "
                    "ON operation_approvals (execution_started_at)"
                )
            )

    # 集中导入模型，确保 metadata 包含所有旧工单与智能运维表。
    import app.models  # noqa: F401
    from app.db.session import Base

    before_create = set(inspect(engine).get_table_names())
    Base.metadata.create_all(bind=engine)
    for table_name, index_name in (
        ("ml_model_versions", "uq_ml_model_active_production_task"),
        ("ml_feature_definitions", "uq_ml_feature_schema_name"),
    ):
        required_index = next(
            index
            for index in Base.metadata.tables[table_name].indexes
            if index.name == index_name
        )
        required_index.create(bind=engine, checkfirst=True)
    after_create = set(inspect(engine).get_table_names())
    if set(INTELLIGENT_MAINTENANCE_TABLES) - before_create and set(
        INTELLIGENT_MAINTENANCE_TABLES
    ).issubset(after_create):
        applied.append("intelligent_maintenance.head")

    return applied


def downgrade_intelligent_schema(engine: Engine) -> list[str]:
    """回退到旧工单兼容版本，同时保留旧表与设备增量列。

    该函数用于迁移演练和紧急应用回滚。它会删除智能运维表中的数据，因此生产环境必须先
    备份；正常生产回滚推荐保留新表，仅回退应用版本。
    """
    import app.models  # noqa: F401
    from app.db.session import Base

    existing = set(inspect(engine).get_table_names())
    dropped: list[str] = []
    with engine.begin() as connection:
        for table_name in _INTELLIGENCE_DROP_ORDER:
            if table_name not in existing:
                continue
            connection.execute(
                DropTable(Base.metadata.tables[table_name], if_exists=True)
            )
            dropped.append(table_name)
    return dropped


def schema_is_ready(engine: Engine) -> bool:
    """检查当前数据库是否包含平台运行所需的核心表。"""
    tables = set(inspect(engine).get_table_names())
    return {"users", "equipment", "work_orders"}.issubset(tables) and set(
        INTELLIGENT_MAINTENANCE_TABLES
    ).issubset(tables)
