"""在当前 DATABASE_URL 上演练 Alembic 升级、重复升级与种子数据。"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db.alembic import current_revision, database_is_at_head, upgrade_database
from app.db.migrations import schema_is_ready
from app.db.session import engine
from app.models.base import (
    EquipmentStatusEnum,
    PriorityEnum,
    RiskLevelEnum,
    WorkOrderStatusEnum,
    WorkOrderTypeEnum,
)
from app.models.equipment import Equipment, EquipmentType
from app.models.workorder import WorkOrder
from app.seed import _seed


def main() -> None:
    upgrade_database(engine)
    assert schema_is_ready(engine)
    assert database_is_at_head(engine)
    first_revision = current_revision(engine)
    upgrade_database(engine)
    assert current_revision(engine) == first_revision

    with Session(engine) as db:
        if not db.query(WorkOrder).filter_by(code="WO-MIGRATION-COMPAT-001").first():
            equipment_type = EquipmentType(name="迁移兼容设备")
            db.add(equipment_type)
            db.flush()
            equipment = Equipment(
                code="MIGRATION-COMPAT-001",
                name="升级前兼容设备",
                equipment_type_id=equipment_type.id,
                status=EquipmentStatusEnum.running,
                risk_level=RiskLevelEnum.low,
                qr_token="migration-compat-001",
            )
            db.add(equipment)
            db.flush()
            db.add(
                WorkOrder(
                    code="WO-MIGRATION-COMPAT-001",
                    title="升级前工单 Copilot 兼容记录",
                    equipment_id=equipment.id,
                    order_type=WorkOrderTypeEnum.fault_repair,
                    priority=PriorityEnum.P3,
                    status=WorkOrderStatusEnum.pending_dispatch,
                )
            )
        db.commit()

    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT COUNT(*) FROM work_orders "
                    "WHERE code = 'WO-MIGRATION-COMPAT-001'"
                )
            ).scalar_one()
            == 1
        )

    with Session(engine) as db:
        _seed(db)
        db.commit()

    inspector = inspect(engine)
    assert inspector.get_foreign_keys("telemetry_records")
    assert inspector.get_indexes("telemetry_records")
    collected_at = next(
        column
        for column in inspector.get_columns("telemetry_records")
        if column["name"] == "collected_at"
    )
    if engine.dialect.name == "postgresql":
        assert collected_at["type"].timezone is True
    print(
        f"migration verification passed: dialect={engine.dialect.name}, "
        f"tables={len(inspector.get_table_names())}"
    )


if __name__ == "__main__":
    main()
