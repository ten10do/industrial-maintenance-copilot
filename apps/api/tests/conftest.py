"""Test fixtures for fault report conversion tests."""
import pytest
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
    PriorityEnum,
    RoleEnum,
    UrgencyEnum,
    WorkOrderStatusEnum,
)
from app.models.equipment import Equipment, EquipmentType, FaultCode
from app.models.fault import FaultReport
from app.models.user import User
from app.models.workorder import WorkOrder

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
    fc = FaultCode(code="E101", name="Spindle Error", severity="high", equipment_type_id=equipment_type.id)
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
