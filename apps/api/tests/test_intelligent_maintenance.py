"""智能运维闭环、仿真确定性与人工审批测试。"""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.ai.client import LLMClient
from app.gateways.equipment import MockEquipmentGateway, TelemetrySnapshot
from app.models.base import (
    KnowledgeCategoryEnum,
    WorkOrderStatusEnum,
)
from app.models.equipment import Equipment, EquipmentType, SparePart
from app.models.intelligence import (
    AgentRun,
    AnomalyEvent,
    FaultDiagnosis,
    OperationApproval,
    SparePartReservation,
    TelemetryRecord,
    ToolInvocation,
)
from app.models.knowledge import KnowledgeArticle
from app.models.workorder import WorkOrder
from app.seed import _seed
from app.services.intelligence_service import ingest_snapshot
from app.services.simulator import simulator_controller


@pytest.mark.asyncio
async def test_mock_gateway_is_deterministic():
    equipment_id = UUID("11111111-1111-1111-1111-111111111111")
    gateway = MockEquipmentGateway()
    gateway.configure([equipment_id], scenario="bearing_wear", seed=42)
    first_run = [await gateway.read_telemetry(equipment_id) for _ in range(4)]

    gateway.reset()
    second_run = [await gateway.read_telemetry(equipment_id) for _ in range(4)]

    assert [
        (item.vibration_rms, item.bearing_temperature, item.motor_current)
        for item in first_run
    ] == [
        (item.vibration_rms, item.bearing_temperature, item.motor_current)
        for item in second_run
    ]


def test_vibration_anomaly_creates_prediction_work_order_and_approval(
    client, db, equipment, auth_supervisor
):
    response = client.post(
        "/api/v1/intelligence/simulator/configure",
        headers=auth_supervisor,
        json={
            "equipment_ids": [equipment.id],
            "interval_seconds": 1,
            "scenario": "vibration_spike",
            "seed": 7,
            "auto_create_work_orders": True,
        },
    )
    assert response.status_code == 200

    for _ in range(3):
        tick = client.post(
            "/api/v1/intelligence/simulator/tick", headers=auth_supervisor
        )
        assert tick.status_code == 200

    assert db.query(TelemetryRecord).filter_by(equipment_id=equipment.id).count() == 3
    anomaly = db.query(AnomalyEvent).filter_by(equipment_id=equipment.id).one()
    assert anomaly.fault_type == "rotor_unbalance"
    work_order = (
        db.query(WorkOrder)
        .filter(WorkOrder.equipment_id == equipment.id)
        .filter(WorkOrder.title.contains("预测性维护"))
        .one()
    )
    assert work_order.ai_diagnosis_summary
    approval = db.query(OperationApproval).filter_by(work_order_id=work_order.id).one()
    assert approval.status == "pending"
    assert approval.command_executed is False
    assert (
        db.query(WorkOrder)
        .filter(WorkOrder.equipment_id == equipment.id)
        .filter(WorkOrder.title.contains("预测性维护"))
        .count()
        == 1
    )
    for _ in range(3):
        client.post("/api/v1/intelligence/simulator/tick", headers=auth_supervisor)
    assert (
        db.query(WorkOrder)
        .filter(WorkOrder.equipment_id == equipment.id)
        .filter(WorkOrder.title.contains("预测性维护"))
        .count()
        == 1
    )
    simulator_controller.reset()


def test_high_risk_command_executes_only_after_human_approval(
    client, db, equipment, auth_supervisor
):
    client.post(
        "/api/v1/intelligence/simulator/configure",
        headers=auth_supervisor,
        json={
            "equipment_ids": [equipment.id],
            "scenario": "normal",
            "seed": 9,
        },
    )
    requested = client.post(
        "/api/v1/intelligence/approvals",
        headers=auth_supervisor,
        json={
            "equipment_id": equipment.id,
            "command_type": "shutdown",
            "command_payload": {"reason": "安全检修"},
            "risk_level": "high",
            "risk_reason": "停机影响产线，需主管确认",
        },
    )
    assert requested.status_code == 200
    approval_id = requested.json()["id"]
    assert requested.json()["command_executed"] is False
    duplicate = client.post(
        "/api/v1/intelligence/approvals",
        headers=auth_supervisor,
        json={
            "equipment_id": equipment.id,
            "command_type": "shutdown",
            "command_payload": {"reason": "安全检修"},
            "risk_level": "high",
            "risk_reason": "停机影响产线，需主管确认",
        },
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == approval_id

    approved = client.post(
        f"/api/v1/intelligence/approvals/{approval_id}/approve",
        headers=auth_supervisor,
        json={"note": "已确认维护窗口与 LOTO 负责人"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["command_executed"] is True
    assert approved.json()["command_result"]["data"]["running"] is False
    repeated = client.post(
        f"/api/v1/intelligence/approvals/{approval_id}/approve",
        headers=auth_supervisor,
        json={"note": "重复请求"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["command_result"] == approved.json()["command_result"]
    simulator_controller.reset()


def test_technician_cannot_approve_high_risk_operation(
    client, equipment, auth_supervisor, auth_technician
):
    client.post(
        "/api/v1/intelligence/simulator/configure",
        headers=auth_supervisor,
        json={"equipment_ids": [equipment.id], "scenario": "normal", "seed": 3},
    )
    requested = client.post(
        "/api/v1/intelligence/approvals",
        headers=auth_supervisor,
        json={
            "equipment_id": equipment.id,
            "command_type": "shutdown",
            "risk_level": "high",
            "risk_reason": "权限边界测试",
        },
    )

    denied = client.post(
        f"/api/v1/intelligence/approvals/{requested.json()['id']}/approve",
        headers=auth_technician,
        json={"note": "技术员尝试审批"},
    )

    assert denied.status_code == 403
    simulator_controller.reset()


def test_sensor_disconnect_marks_equipment_offline(
    client, db, equipment, auth_supervisor
):
    client.post(
        "/api/v1/intelligence/simulator/configure",
        headers=auth_supervisor,
        json={
            "equipment_ids": [equipment.id],
            "scenario": "sensor_disconnect",
            "seed": 11,
        },
    )
    for _ in range(3):
        client.post("/api/v1/intelligence/simulator/tick", headers=auth_supervisor)
    db.refresh(equipment)
    assert equipment.status.value == "offline"
    assert equipment.health_score == 42.0
    assert (
        db.query(AnomalyEvent)
        .filter_by(equipment_id=equipment.id, fault_type="sensor_abnormal")
        .count()
        == 1
    )
    simulator_controller.reset()


def test_seed_contains_motor_predictive_maintenance_demo(db):
    _seed(db)
    db.flush()

    motor_type = db.query(EquipmentType).filter_by(name="工业电机").one()
    motors = db.query(Equipment).filter_by(equipment_type_id=motor_type.id).all()
    assert len(motors) == 5
    assert (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.equipment_id.in_([item.id for item in motors]))
        .count()
        == 120
    )
    predictive_order = (
        db.query(WorkOrder).filter(WorkOrder.title.contains("预测性维护")).one()
    )
    approval = (
        db.query(OperationApproval)
        .filter_by(work_order_id=predictive_order.id, status="pending")
        .one()
    )
    assert approval.command_executed is False


def test_diagnosis_has_rag_citations_agent_audit_and_human_review(db, equipment):
    article = KnowledgeArticle(
        title="工业电机轴承振动诊断手册",
        category=KnowledgeCategoryEnum.manual,
        content="轴承振动升高时检查滚道磨损、润滑状态与转子平衡。",
        summary="轴承振动诊断",
        tags=["轴承", "振动"],
        equipment_type_id=equipment.equipment_type_id,
        source="测试手册",
        status="published",
    )
    db.add(article)
    db.commit()

    result = ingest_snapshot(
        db,
        equipment,
        _snapshot(equipment, scenario="normal", vibration=8.2),
    )

    assert result.anomaly is not None
    diagnosis = (
        db.query(FaultDiagnosis).filter_by(anomaly_event_id=result.anomaly.id).one()
    )
    assert diagnosis.rag_citations[0]["article_id"] == article.id
    assert diagnosis.requires_human_review is True
    run = db.query(AgentRun).filter_by(anomaly_event_id=result.anomaly.id).one()
    assert run.status == "completed"
    assert run.requires_human_review is True
    assert {
        item.tool_name
        for item in db.query(ToolInvocation).filter_by(agent_run_id=run.id).all()
    } >= {
        "anomaly_detector",
        "knowledge_search",
        "risk_predictor",
        "maintenance_strategy",
        "work_order_creator",
    }


def test_spare_part_shortage_is_recorded_without_negative_stock(db, equipment):
    part = SparePart(
        code="PART-BEARING-001",
        name="轴承 6205",
        stock_qty=0,
        unit="个",
    )
    db.add(part)
    db.commit()

    result = ingest_snapshot(
        db,
        equipment,
        _snapshot(equipment, scenario="vibration_spike", vibration=10.0),
    )

    assert result.work_order is not None
    reservation = (
        db.query(SparePartReservation)
        .filter_by(
            work_order_id=result.work_order.id,
            spare_part_id=part.id,
        )
        .one()
    )
    assert reservation.status == "shortage"
    assert reservation.reserved_qty == 0
    assert reservation.shortage_qty == 1
    db.refresh(part)
    assert part.stock_qty == 0


def test_failed_verification_reopens_work_order_and_creates_draft_case(
    client, db, equipment, auth_supervisor
):
    result = ingest_snapshot(
        db,
        equipment,
        _snapshot(equipment, scenario="vibration_spike", vibration=10.0),
    )
    assert result.work_order is not None
    result.work_order.status = WorkOrderStatusEnum.pending_acceptance
    db.commit()

    response = client.post(
        "/api/v1/intelligence/verifications",
        headers=auth_supervisor,
        json={"work_order_id": result.work_order.id},
    )

    assert response.status_code == 200
    assert response.json()["result"] == "failed"
    db.refresh(result.work_order)
    assert result.work_order.status == WorkOrderStatusEnum.returned
    assert result.work_order.needs_observation is True
    article = db.get(KnowledgeArticle, response.json()["knowledge_article_id"])
    assert article is not None
    assert article.status == "draft"


def test_successful_verification_closes_work_order_and_creates_draft_case(
    client, db, equipment, auth_supervisor
):
    result = ingest_snapshot(
        db,
        equipment,
        _snapshot(equipment, scenario="vibration_spike", vibration=10.0),
    )
    assert result.work_order is not None
    ingest_snapshot(
        db,
        equipment,
        _snapshot(equipment, scenario="normal", vibration=1.8),
    )
    result.work_order.status = WorkOrderStatusEnum.pending_acceptance
    db.commit()

    response = client.post(
        "/api/v1/intelligence/verifications",
        headers=auth_supervisor,
        json={"work_order_id": result.work_order.id},
    )

    assert response.status_code == 200
    assert response.json()["result"] == "passed"
    db.refresh(result.work_order)
    assert result.work_order.status == WorkOrderStatusEnum.completed
    article = db.get(KnowledgeArticle, response.json()["knowledge_article_id"])
    assert article is not None
    assert article.status == "draft"


def test_ai_provider_failure_degrades_to_mock(monkeypatch):
    client = LLMClient()
    client.enabled = True
    client.api_key = "test-placeholder"

    class FailingHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            raise RuntimeError("provider unavailable")

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr("app.ai.client.httpx.Client", FailingHttpClient)

    response = client.chat([{"role": "user", "content": "diagnose"}])

    assert response["is_mock"] is True
    assert response["content"] == ""
    assert "provider unavailable" in response["error"]


def _snapshot(
    equipment: Equipment,
    *,
    scenario: str,
    vibration: float,
) -> TelemetrySnapshot:
    return TelemetrySnapshot(
        equipment_id=UUID(equipment.asset_uuid),
        collected_at=datetime.now(UTC),
        vibration_rms=vibration,
        bearing_temperature=56.0,
        motor_current=18.0,
        motor_voltage=380.0,
        rotational_speed=1480.0,
        load_ratio=62.0,
        ambient_temperature=26.0,
        cumulative_runtime_hours=12480.0,
        scenario=scenario,
        quality=1.0,
    )
