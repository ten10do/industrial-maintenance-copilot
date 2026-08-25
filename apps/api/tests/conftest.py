"""Test fixtures for fault report conversion tests."""

# Observability 共享脚手架依赖（保持模块顶部导入）。
import asyncio as _asyncio
from datetime import UTC as _UTC
from datetime import datetime as _datetime
from pathlib import Path as _Path

import pytest
import yaml as _yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models.base import (
    EquipmentStatusEnum,
    FaultReportStatusEnum,
    RoleEnum,
    UrgencyEnum,
)
from app.models.base import (
    RiskLevelEnum as _RiskLevelEnum,
)
from app.models.equipment import Equipment, EquipmentType, FaultCode
from app.models.fault import FaultReport
from app.models.user import User

# In-memory SQLite with StaticPool ensures all connections share the same :memory: database
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key support in SQLite."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    """Reset database before each test."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


def _create_user(db: Session, email: str, name: str, role: RoleEnum) -> User:
    user = User(
        email=email,
        full_name=name,
        hashed_password=hash_password("test123"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _token_for(user: User) -> str:
    return create_access_token(str(user.id))


@pytest.fixture
def supervisor(db):
    return _create_user(db, "sup@test.com", "Supervisor", RoleEnum.supervisor)


@pytest.fixture
def technician(db):
    return _create_user(db, "tech@test.com", "Technician", RoleEnum.technician)


@pytest.fixture
def another_technician(db):
    return _create_user(
        db,
        "tech2@test.com",
        "Technician 2",
        RoleEnum.technician,
    )


@pytest.fixture
def admin_user(db):
    return _create_user(db, "admin@test.com", "Admin", RoleEnum.admin)


@pytest.fixture
def auth_supervisor(client, supervisor):
    return {"Authorization": f"Bearer {_token_for(supervisor)}"}


@pytest.fixture
def auth_technician(client, technician):
    return {"Authorization": f"Bearer {_token_for(technician)}"}


@pytest.fixture
def auth_admin(client, admin_user):
    return {"Authorization": f"Bearer {_token_for(admin_user)}"}


@pytest.fixture
def equipment_type(db):
    et = EquipmentType(name="CNC Machine", description="CNC Machine")
    db.add(et)
    db.commit()
    db.refresh(et)
    return et


@pytest.fixture
def equipment(db, equipment_type):
    eq = Equipment(
        code="EQ-001",
        name="CNC-01",
        equipment_type_id=equipment_type.id,
        status=EquipmentStatusEnum.running,
        plant="Plant A",
        production_line="Line 1",
        qr_token="qr-test-001",
    )
    db.add(eq)
    db.commit()
    db.refresh(eq)
    return eq


@pytest.fixture
def fault_code(db, equipment_type):
    fc = FaultCode(
        code="E101",
        name="Spindle Error",
        severity="high",
        equipment_type_id=equipment_type.id,
    )
    db.add(fc)
    db.commit()
    db.refresh(fc)
    return fc


@pytest.fixture
def fault_report_pending(db, equipment, fault_code):
    fr = FaultReport(
        equipment_id=equipment.id,
        title="主轴异响",
        description="CNC-01主轴在高速运转时发出异常噪音",
        urgency=UrgencyEnum.high,
        status=FaultReportStatusEnum.pending,
        is_downtime=False,
        affects_production=True,
        has_safety_risk=False,
        reporter_name="Operator Wang",
        fault_code_id=fault_code.id,
        created_by="1",
    )
    db.add(fr)
    db.commit()
    db.refresh(fr)
    return fr


@pytest.fixture
def fault_report_critical(db, equipment, fault_code):
    fr = FaultReport(
        equipment_id=equipment.id,
        title="高压电气故障",
        description="电气柜冒烟，有高压危险",
        urgency=UrgencyEnum.critical,
        status=FaultReportStatusEnum.pending,
        is_downtime=True,
        affects_production=True,
        has_safety_risk=True,
        reporter_name="Operator Li",
        fault_code_id=fault_code.id,
        created_by="1",
    )
    db.add(fr)
    db.commit()
    db.refresh(fr)
    return fr


# ---------------------------------------------------------------------------
# Observability 共享脚手架：真实订阅故障链 → 带 trace_id 的领域实体。
# （导入统一放在文件顶部）
# ---------------------------------------------------------------------------

_TRACE_NODES = [
    ("Temperature", "temperature"),
    ("Vibration", "vibration"),
    ("Current", "current"),
    ("Speed", "speed"),
    ("Voltage", "voltage"),
    ("LoadRatio", "load"),
]
_TRACE_UNITS = {
    "temperature": "celsius",
    "vibration": "mm/s",
    "current": "A",
    "speed": "rpm",
    "voltage": "V",
    "load": "%",
}
_TRACE_FIELDS = {
    "temperature": "bearing_temperature",
    "vibration": "vibration_rms",
    "current": "motor_current",
    "speed": "rotational_speed",
    "voltage": "motor_voltage",
    "load": "load_ratio",
}


def run_fault_trace_chain(db, tmp_path, *, code_suffix: str = ""):
    """真实订阅故障链（Mock 客户端）→ 返回 (equipment, alarm, work_order)。

    生成的所有领域实体共享同一条工业 trace_id；不伪造任何记录。
    局部导入：避免 conftest 顶层触发 industrial_gateway ↔ app.models 的
    包初始化顺序问题。
    """

    from app.industrial_gateway.models import IndustrialAlarm as _IndustrialAlarm
    from app.industrial_gateway.opcua.client import MockOpcUaClient as _MockClient
    from app.industrial_gateway.opcua.models import NodeRead as _NodeRead
    from app.industrial_gateway.opcua.service import OpcUaGatewayService as _Service
    from app.industrial_gateway.opcua.subscription import (
        MockSubscriptionClient as _SubClient,
    )
    from app.industrial_gateway.opcua.subscription import (
        NodeDataChange as _NodeDataChange,
    )
    from app.industrial_gateway.simulator.generator import MotorSimulator as _Sim
    from app.models.workorder import WorkOrder as _WorkOrder

    equipment = Equipment(
        code=f"EQ-TRACE-01{code_suffix}",
        name="链路追踪验证电机",
        status=EquipmentStatusEnum.running,
        risk_level=_RiskLevelEnum.low,
        qr_token=f"qr-trace-01{code_suffix}",
    )
    db.add(equipment)
    db.commit()
    db.refresh(equipment)

    config = {
        "mappings": [
            {
                "node_id": f"ns=2;s=Motor001.{name}",
                "equipment_code": equipment.code,
                "metric": metric,
                "unit": _TRACE_UNITS[metric],
            }
            for name, metric in _TRACE_NODES
        ]
    }
    config_path = _Path(tmp_path) / "trace-chain-mapping.yaml"
    config_path.write_text(
        _yaml.safe_dump(config, allow_unicode=True), encoding="utf-8"
    )

    simulator = _Sim(seed=42, scenario="fault")

    def initial_provider(node_id: str) -> _NodeRead:
        _, metric = next(
            (n, m) for n, m in _TRACE_NODES if node_id == f"ns=2;s=Motor001.{n}"
        )
        values = simulator.current_values()
        return _NodeRead(
            node_id=node_id,
            value=values.get(_TRACE_FIELDS[metric]),
            source_timestamp=_datetime.now(_UTC),
            quality="good",
        )

    sub_client = _SubClient(initial_provider=initial_provider)
    service = _Service(
        _MockClient(value_provider=simulator.value_provider()),
        mode="mock",
        poll_interval_seconds=5.0,
        mapping_config_path=str(config_path),
        before_sync=simulator.advance,
        subscription_client_factory=lambda: sub_client,
        session_factory=lambda: Session(bind=db.get_bind(), autoflush=False),
    )

    async def _chain():
        await service.start_subscription(db, client=sub_client)
        for _ in range(16):
            simulator.advance()
        now = _datetime.now(_UTC)
        values = simulator.current_values()
        for name, _m in _TRACE_NODES:
            sub_client.publish(
                _NodeDataChange(
                    node_id=f"ns=2;s=Motor001.{name}",
                    value=values[name],
                    source_timestamp=now,
                    status_code=0,
                    quality="good",
                )
            )
        flush = await service.flush_now(db)
        await service.stop_subscription(db)
        return flush

    flush = _asyncio.run(_chain())
    assert flush["snapshots_ingested"] == 1

    alarm = (
        db.query(_IndustrialAlarm)
        .filter(_IndustrialAlarm.equipment_id == equipment.id)
        .first()
    )
    work_order = (
        db.query(_WorkOrder).filter(_WorkOrder.equipment_id == equipment.id).first()
    )
    return equipment, alarm, work_order


@pytest.fixture
def fault_chain(db, tmp_path):
    """可重复调用的故障链工厂：fault_chain() / fault_chain(code_suffix="-2")。"""

    def _make(code_suffix: str = ""):
        return run_fault_trace_chain(db, tmp_path, code_suffix=code_suffix)

    return _make
