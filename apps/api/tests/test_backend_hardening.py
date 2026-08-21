from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from app.api.v1.endpoints.files import _resolve_storage_path
from app.core.security import hash_password
from app.models.base import RiskLevelEnum, RoleEnum, WorkOrderStatusEnum
from app.models.equipment import Equipment, EquipmentType
from app.models.fault import FaultReport
from app.models.intelligence import OperationApproval
from app.models.user import Skill, TechnicianProfile, User
from app.models.workorder import WorkOrder
from app.services.work_order_codes import generate_work_order_code


def test_concurrent_work_order_codes_are_unique():
    now = datetime(2026, 8, 11, tzinfo=UTC)

    with ThreadPoolExecutor(max_workers=32) as executor:
        codes = list(executor.map(lambda _: generate_work_order_code(now), range(2000)))

    assert len(codes) == len(set(codes))
    assert all(code.startswith("WO-2026-") for code in codes)


def test_work_order_list_uses_constant_query_count(
    client, auth_supervisor, db, supervisor, technician, equipment
):
    for index in range(12):
        db.add(
            WorkOrder(
                code=generate_work_order_code(),
                title=f"查询效率工单 {index}",
                equipment_id=equipment.id,
                status=WorkOrderStatusEnum.assigned,
                creator=supervisor,
                assignee=technician,
            )
        )
    db.commit()

    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", record_statement)
    try:
        response = client.get(
            "/api/v1/work-orders?page_size=100",
            headers=auth_supervisor,
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_statement)

    assert response.status_code == 200
    assert len(response.json()["items"]) == 12
    assert len(statements) <= 3, statements


def test_equipment_list_uses_constant_query_count(client, auth_supervisor, db):
    password = hash_password("test123")
    for index in range(12):
        responsible_person = User(
            email=f"equipment-owner-{index}@test.com",
            full_name=f"设备负责人 {index}",
            hashed_password=password,
            role=RoleEnum.technician,
            is_active=True,
        )
        equipment_type = EquipmentType(name=f"查询设备类型 {index}")
        db.add_all([responsible_person, equipment_type])
        db.flush()
        db.add(
            Equipment(
                code=f"QUERY-EQ-{index:03d}",
                name=f"查询设备 {index}",
                equipment_type_id=equipment_type.id,
                responsible_person_id=responsible_person.id,
                qr_token=f"query-equipment-{index}",
            )
        )
    db.commit()
    db.expunge_all()

    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", record_statement)
    try:
        response = client.get(
            "/api/v1/equipment?page_size=100",
            headers=auth_supervisor,
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_statement)

    assert response.status_code == 200
    assert len(response.json()["items"]) == 12
    assert response.json()["items"][0]["equipment_type_name"] is not None
    assert response.json()["items"][0]["responsible_person_name"] is not None
    assert len(statements) <= 3, statements


def test_technician_list_uses_constant_query_count(
    client, auth_supervisor, db, equipment
):
    password = hash_password("test123")
    for index in range(12):
        user = User(
            email=f"technician-query-{index}@test.com",
            full_name=f"查询工程师 {index}",
            hashed_password=password,
            role=RoleEnum.technician,
            is_active=True,
        )
        skill = Skill(name=f"查询技能 {index}")
        db.add_all([user, skill])
        db.flush()
        profile = TechnicianProfile(user_id=user.id, skills=[skill])
        db.add(profile)
        db.add(
            WorkOrder(
                code=f"TECH-QUERY-WO-{index:03d}",
                title=f"工程师负载查询 {index}",
                equipment_id=equipment.id,
                status=WorkOrderStatusEnum.assigned,
                assignee_id=user.id,
            )
        )
    db.commit()
    db.expunge_all()

    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", record_statement)
    try:
        response = client.get("/api/v1/users/technicians", headers=auth_supervisor)
    finally:
        event.remove(bind, "before_cursor_execute", record_statement)

    assert response.status_code == 200
    assert len(response.json()) == 12
    assert all(item["active_work_orders"] == 1 for item in response.json())
    assert all(len(item["skills"]) == 1 for item in response.json())
    assert len(statements) <= 4, statements


def test_fault_report_list_uses_constant_query_count(
    client, auth_supervisor, db, equipment_type
):
    for index in range(12):
        equipment = Equipment(
            code=f"FAULT-QUERY-EQ-{index:03d}",
            name=f"故障查询设备 {index}",
            equipment_type_id=equipment_type.id,
            qr_token=f"fault-query-equipment-{index}",
        )
        db.add(equipment)
        db.flush()
        fault_report = FaultReport(
            equipment_id=equipment.id,
            title=f"查询故障 {index}",
            description=f"故障列表查询测试 {index}",
        )
        db.add(fault_report)
        db.flush()
        db.add(
            WorkOrder(
                code=f"FAULT-QUERY-WO-{index:03d}",
                title=f"故障关联工单 {index}",
                equipment_id=equipment.id,
                fault_report_id=fault_report.id,
                status=WorkOrderStatusEnum.assigned,
            )
        )
    db.commit()
    db.expunge_all()

    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", record_statement)
    try:
        response = client.get(
            "/api/v1/fault-reports?page_size=100",
            headers=auth_supervisor,
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_statement)

    assert response.status_code == 200
    assert len(response.json()["items"]) == 12
    assert all(item["equipment_name"] for item in response.json()["items"])
    assert all(item["related_work_order_id"] for item in response.json()["items"])
    assert len(statements) <= 4, statements


def test_approval_list_uses_constant_query_count(
    client, auth_supervisor, db, equipment
):
    password = hash_password("test123")
    now = datetime.now(UTC)
    for index in range(12):
        reviewer = User(
            email=f"approval-reviewer-{index}@test.com",
            full_name=f"审批查询用户 {index}",
            hashed_password=password,
            role=RoleEnum.supervisor,
            is_active=True,
        )
        db.add(reviewer)
        db.flush()
        db.add(
            OperationApproval(
                equipment_id=equipment.id,
                command_type="shutdown",
                risk_level=RiskLevelEnum.high,
                risk_reason="审批列表常量查询测试",
                status="execution_failed",
                requested_by=reviewer.id,
                reviewed_by=reviewer.id,
                reconciled_by=reviewer.id,
                requested_at=now + timedelta(seconds=index),
                command_executed=False,
            )
        )
    db.commit()

    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", record_statement)
    try:
        response = client.get(
            "/api/v1/intelligence/approvals?limit=100",
            headers=auth_supervisor,
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_statement)

    assert response.status_code == 200
    assert len(response.json()) == 12
    assert response.json()[0]["reviewed_by_name"] == "审批查询用户 11"
    assert len(statements) <= 5, statements


def test_approval_list_rejects_unbounded_pagination(client, auth_supervisor):
    too_large = client.get(
        "/api/v1/intelligence/approvals?limit=501",
        headers=auth_supervisor,
    )
    negative_offset = client.get(
        "/api/v1/intelligence/approvals?offset=-1",
        headers=auth_supervisor,
    )

    assert too_large.status_code == 422
    assert negative_offset.status_code == 422


def test_approval_list_filters_action_required_on_server(
    client, auth_supervisor, db, equipment, supervisor
):
    now = datetime.now(UTC)
    for index, status in enumerate(["pending", "execution_unknown", "approved"]):
        db.add(
            OperationApproval(
                equipment_id=equipment.id,
                command_type="shutdown",
                risk_level=RiskLevelEnum.high,
                risk_reason="服务端待处理筛选测试",
                status=status,
                requested_by=supervisor.id,
                requested_at=now + timedelta(seconds=index),
                command_executed=status == "approved",
            )
        )
    db.commit()

    response = client.get(
        "/api/v1/intelligence/approvals?status=action_required",
        headers=auth_supervisor,
    )

    assert response.status_code == 200
    assert {item["status"] for item in response.json()} == {
        "pending",
        "execution_unknown",
    }


def test_technician_cannot_list_user_directory(client, auth_technician):
    response = client.get("/api/v1/users", headers=auth_technician)

    assert response.status_code == 403
    assert response.json()["detail"] == "权限不足"


def test_supervisor_can_list_user_directory(
    client, auth_supervisor, supervisor, technician
):
    response = client.get("/api/v1/users", headers=auth_supervisor)

    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == {
        supervisor.id,
        technician.id,
    }


def test_equipment_qrcode_rejects_unauthenticated_request(client, equipment):
    response = client.get(f"/api/v1/equipment/{equipment.id}/qrcode")

    assert response.status_code == 401


def test_equipment_qrcode_allows_authenticated_user(client, auth_technician, equipment):
    response = client.get(
        f"/api/v1/equipment/{equipment.id}/qrcode",
        headers=auth_technician,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_storage_path_accepts_real_child(tmp_path):
    base = tmp_path / "uploads"
    child = base / "workorders" / "evidence.pdf"
    child.parent.mkdir(parents=True)
    child.write_bytes(b"evidence")

    assert _resolve_storage_path(base, "workorders/evidence.pdf") == child.resolve()


def test_storage_path_rejects_sibling_with_same_prefix(tmp_path):
    base = tmp_path / "uploads"
    sibling = tmp_path / "uploads-private" / "secret.pdf"
    base.mkdir()
    sibling.parent.mkdir()
    sibling.write_bytes(b"secret")

    with pytest.raises(HTTPException) as exc_info:
        _resolve_storage_path(base, "../uploads-private/secret.pdf")

    assert exc_info.value.status_code == 403


def test_storage_path_rejects_parent_traversal(tmp_path):
    base = tmp_path / "uploads"
    base.mkdir()

    with pytest.raises(HTTPException) as exc_info:
        _resolve_storage_path(base, "../../outside.pdf")

    assert exc_info.value.status_code == 403
