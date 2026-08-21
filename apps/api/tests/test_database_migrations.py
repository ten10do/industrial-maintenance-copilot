import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db.alembic import (
    current_revision,
    database_is_at_head,
    ensure_database_at_head,
    upgrade_database,
)
from app.db.migrations import (
    INTELLIGENT_MAINTENANCE_TABLES,
    downgrade_intelligent_schema,
    schema_is_ready,
    upgrade_schema,
)
from app.models.base import (
    EquipmentStatusEnum,
    PriorityEnum,
    RiskLevelEnum,
    WorkOrderStatusEnum,
    WorkOrderTypeEnum,
)
from app.models.equipment import Equipment, EquipmentType
from app.models.intelligence import TelemetryRecord
from app.models.workorder import WorkOrder


def test_alembic_upgrade_creates_and_versions_new_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'alembic-new.db'}")

    assert current_revision(engine) is None
    assert database_is_at_head(engine) is False

    upgrade_database(engine)

    assert current_revision(engine) == "20260811_01"
    assert database_is_at_head(engine) is True
    assert schema_is_ready(engine) is True
    tables = set(inspect(engine).get_table_names())
    upgrade_database(engine)
    assert set(inspect(engine).get_table_names()) == tables
    assert current_revision(engine) == "20260811_01"


def test_alembic_adopts_unversioned_legacy_database_without_losing_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'alembic-legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE work_order_checklist_items ("
                "id INTEGER PRIMARY KEY, content VARCHAR(255) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO work_order_checklist_items (id, content) "
                "VALUES (1, 'legacy checklist item')"
            )
        )

    upgrade_database(engine)

    assert current_revision(engine) == "20260811_01"
    with engine.connect() as connection:
        legacy_row = connection.execute(
            text(
                "SELECT content, category FROM work_order_checklist_items WHERE id = 1"
            )
        ).one()
    assert legacy_row == ("legacy checklist item", "repair")
    assert schema_is_ready(engine) is True


def test_production_startup_refuses_unmigrated_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'unmigrated.db'}")

    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        ensure_database_at_head(engine, auto_migrate=False)

    ensure_database_at_head(engine, auto_migrate=True)
    ensure_database_at_head(engine, auto_migrate=False)
    assert database_is_at_head(engine) is True


def test_upgrade_adds_checklist_category_without_losing_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE work_order_checklist_items ("
                "id INTEGER PRIMARY KEY, content VARCHAR(255) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO work_order_checklist_items (id, content) "
                "VALUES (1, 'legacy checklist item'), (2, '负载测试')"
            )
        )

    assert upgrade_schema(engine) == [
        "work_order_checklist_items.category",
        "work_order_checklist_items.category_backfill",
        "intelligent_maintenance.head",
    ]

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("work_order_checklist_items")
    }
    assert "category" in columns
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT content, category FROM work_order_checklist_items ORDER BY id")
        ).all()
    assert rows == [
        ("legacy checklist item", "repair"),
        ("负载测试", "testing"),
    ]


def test_upgrade_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'current.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE work_order_checklist_items ("
                "id INTEGER PRIMARY KEY, content VARCHAR(255) NOT NULL, "
                "category VARCHAR(32) NOT NULL DEFAULT 'repair')"
            )
        )

    assert upgrade_schema(engine) == ["intelligent_maintenance.head"]
    assert upgrade_schema(engine) == []


def test_upgrade_adds_intelligent_equipment_fields_and_backfills_uuid(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-equipment.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE equipment ("
                "id INTEGER PRIMARY KEY, code VARCHAR(64) NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO equipment (id, code) VALUES (1, 'EQ-001')")
        )

    applied = upgrade_schema(engine)

    assert applied == [
        "equipment.asset_uuid",
        "equipment.next_maintenance_at",
        "equipment.health_score",
        "equipment.rated_parameters",
        "equipment.cumulative_runtime_hours",
        "equipment.asset_uuid_backfill",
        "intelligent_maintenance.head",
    ]
    columns = {column["name"] for column in inspect(engine).get_columns("equipment")}
    assert {
        "asset_uuid",
        "next_maintenance_at",
        "health_score",
        "rated_parameters",
        "cumulative_runtime_hours",
    }.issubset(columns)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT asset_uuid, health_score, cumulative_runtime_hours "
                "FROM equipment WHERE id = 1"
            )
        ).one()
    assert len(row.asset_uuid) == 32
    assert row.health_score == 100
    assert row.cumulative_runtime_hours == 0
    assert upgrade_schema(engine) == []


def test_upgrade_backfills_operation_approval_execution_keys(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-approvals.db'}")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE operation_approvals (id INTEGER PRIMARY KEY)")
        )
        connection.execute(text("INSERT INTO operation_approvals (id) VALUES (1), (2)"))

    assert upgrade_schema(engine) == [
        "operation_approvals.execution_key",
        "operation_approvals.execution_reconciliation",
        "intelligent_maintenance.head",
    ]
    with engine.connect() as connection:
        keys = (
            connection.execute(
                text("SELECT execution_key FROM operation_approvals ORDER BY id")
            )
            .scalars()
            .all()
        )
    assert all(key and len(key) == 32 for key in keys)
    assert len(set(keys)) == 2
    assert any(
        index["name"] == "ix_operation_approvals_execution_key" and index["unique"]
        for index in inspect(engine).get_indexes("operation_approvals")
    )
    approval_columns = {
        column["name"] for column in inspect(engine).get_columns("operation_approvals")
    }
    assert {
        "execution_started_at",
        "execution_attempt",
        "reconciliation_outcome",
        "reconciliation_note",
        "observed_device_state",
        "reconciled_by",
        "reconciled_at",
    }.issubset(approval_columns)
    assert "operation_execution_audits" in inspect(engine).get_table_names()
    assert any(
        index["name"] == "ix_operation_approvals_execution_started_at"
        for index in inspect(engine).get_indexes("operation_approvals")
    )
    assert upgrade_schema(engine) == []


def test_intelligent_schema_upgrade_downgrade_upgrade_preserves_legacy_data(
    tmp_path,
):
    engine = create_engine(f"sqlite:///{tmp_path / 'roundtrip.db'}")
    assert upgrade_schema(engine) == ["intelligent_maintenance.head"]
    assert schema_is_ready(engine) is True

    with Session(engine) as db:
        equipment_type = EquipmentType(name="工业电机")
        db.add(equipment_type)
        db.flush()
        equipment = Equipment(
            code="MOTOR-MIG-001",
            name="迁移验证电机",
            equipment_type_id=equipment_type.id,
            status=EquipmentStatusEnum.running,
            risk_level=RiskLevelEnum.low,
            qr_token="migration-motor",
        )
        db.add(equipment)
        db.flush()
        work_order = WorkOrder(
            code="WO-MIG-001",
            title="迁移前兼容工单",
            equipment_id=equipment.id,
            order_type=WorkOrderTypeEnum.fault_repair,
            priority=PriorityEnum.P3,
            status=WorkOrderStatusEnum.pending_dispatch,
        )
        db.add(work_order)
        db.commit()

    dropped = downgrade_intelligent_schema(engine)
    assert set(dropped) == set(INTELLIGENT_MAINTENANCE_TABLES)
    assert schema_is_ready(engine) is False
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT title FROM work_orders WHERE code = 'WO-MIG-001'")
            ).scalar_one()
            == "迁移前兼容工单"
        )

    assert upgrade_schema(engine) == ["intelligent_maintenance.head"]
    assert schema_is_ready(engine) is True
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT name FROM equipment WHERE code = 'MOTOR-MIG-001'")
            ).scalar_one()
            == "迁移验证电机"
        )


def test_intelligent_schema_has_foreign_keys_indexes_and_utc_columns(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'constraints.db'}")
    upgrade_schema(engine)
    inspector = inspect(engine)

    telemetry_fks = inspector.get_foreign_keys("telemetry_records")
    assert any(fk["referred_table"] == "equipment" for fk in telemetry_fks)
    telemetry_indexes = inspector.get_indexes("telemetry_records")
    assert any("equipment_id" in index["column_names"] for index in telemetry_indexes)
    assert any("collected_at" in index["column_names"] for index in telemetry_indexes)
    assert TelemetryRecord.__table__.c.collected_at.type.timezone is True
    model_indexes = inspector.get_indexes("ml_model_versions")
    assert any(
        index["name"] == "uq_ml_model_active_production_task" and index["unique"]
        for index in model_indexes
    )
    feature_indexes = inspector.get_indexes("ml_feature_definitions")
    assert any(
        index["name"] == "uq_ml_feature_schema_name" and index["unique"]
        for index in feature_indexes
    )
