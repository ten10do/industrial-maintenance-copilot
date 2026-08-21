"""Alarm Intelligence 端到端集成测试（关联 + 理解 + 根因 + 决策支持 + API）。

定位约束验证：分析只写平台内记录，不创建/执行任何设备控制。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.industrial_gateway.models import AlarmAnalysisRecord, IndustrialAlarm
from app.models.base import EquipmentStatusEnum, PriorityEnum, RiskLevelEnum
from app.models.equipment import Equipment
from app.models.intelligence import TelemetryRecord
from app.models.workorder import WorkOrder, WorkOrderStatusEnum, WorkOrderTypeEnum


def _setup(db) -> tuple[Equipment, IndustrialAlarm]:
    equipment = Equipment(
        code="EQ-AI-01",
        name="报警智能验证电机",
        status=EquipmentStatusEnum.running,
        risk_level=RiskLevelEnum.high,
        production_line="Line-AI",
        qr_token="qr-ai-01",
    )
    db.add(equipment)
    db.flush()
    db.add(
        TelemetryRecord(
            equipment_id=equipment.id,
            collected_at=datetime.now(UTC),
            bearing_temperature=92.0,
            vibration_rms=4.9,
            motor_current=19.0,
            motor_voltage=381.0,
            load_ratio=66.0,
            cumulative_runtime_hours=500.0,
        )
    )
    alarm = IndustrialAlarm(
        equipment_id=equipment.id,
        severity="CRITICAL",
        message="工业报警升级为 CRITICAL：设备报警位（Alarm）已置位",
        source="opcua-subscription",
    )
    db.add(alarm)
    db.commit()
    db.refresh(alarm)
    return equipment, alarm


def test_analyze_endpoint_persists_full_intelligence(
    client, db, supervisor, equipment_type
):
    equipment, alarm = _setup(db)
    equipment.equipment_type_id = equipment_type.id
    db.commit()

    from app.core.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token(str(supervisor.id))}"}

    response = client.post(f"/api/v1/alarms/{alarm.id}/analyze", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    # 理解：摘要包含越限指标。
    assert "轴承温度=92.0" in payload["summary"]
    assert payload["confidence"] > 0.5
    # 根因：温度越限映射到轴承过热假设，并复用平台处置知识。
    assert payload["root_cause_hypothesis"]
    assert any(
        factor.startswith("轴承温度") for factor in payload["contributing_factors"]
    )
    # 决策支持：建议行动非空 + 优先级 + 人工审批边界声明存在于记录中。
    assert payload["recommended_actions"]
    assert payload["suggested_priority"] in {"P1", "P2"}
    assert payload["requires_human_review"] is True
    assert payload["is_mock"] is True
    assert payload["model_version"] == "deterministic-rules-v1"
    # 关联组：单设备单报警也形成组。
    assert payload["correlation_group_id"]

    record = db.query(AlarmAnalysisRecord).filter_by(alarm_id=alarm.id).one()
    # 决策支持证据已随分析持久化（含建议优先级与关联工单提示）。
    assert "suggested_priority" in record.evidence["decision_support"]
    assert record.recommended_actions
    # 幂等：重复分析覆盖同一记录。
    again = client.post(f"/api/v1/alarms/{alarm.id}/analyze", headers=headers)
    assert again.status_code == 200
    assert db.query(AlarmAnalysisRecord).count() == 1


def test_analyze_forbidden_for_technician(client, db, technician):
    _equipment, alarm = _setup(db)
    from app.core.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token(str(technician.id))}"}
    response = client.post(f"/api/v1/alarms/{alarm.id}/analyze", headers=headers)
    assert response.status_code == 403


def test_get_analysis_requires_existing_record(client, db, supervisor):
    _equipment, alarm = _setup(db)
    from app.core.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token(str(supervisor.id))}"}
    missing = client.get(f"/api/v1/alarms/{alarm.id}/analysis", headers=headers)
    assert missing.status_code == 404

    client.post(f"/api/v1/alarms/{alarm.id}/analyze", headers=headers)
    found = client.get(f"/api/v1/alarms/{alarm.id}/analysis", headers=headers)
    assert found.status_code == 200
    assert found.json()["alarm_id"] == alarm.id


def test_correlate_groups_active_alarms(client, db, supervisor):
    equipment, first = _setup(db)
    second = IndustrialAlarm(
        equipment_id=equipment.id,
        severity="WARNING",
        message="工业报警升级为 WARNING：轴承温度=80.0",
        source="opcua-subscription",
        created_at=datetime.now(UTC) + timedelta(seconds=60),
    )
    db.add(second)
    other_line = Equipment(
        code="EQ-AI-02",
        name="另一产线电机",
        status=EquipmentStatusEnum.running,
        risk_level=RiskLevelEnum.low,
        production_line="Line-Other",
        qr_token="qr-ai-02",
    )
    db.add(other_line)
    db.flush()
    third = IndustrialAlarm(
        equipment_id=other_line.id,
        severity="WARNING",
        message="工业报警升级为 WARNING：振动 RMS=4.8",
        source="opcua-subscription",
        created_at=datetime.now(UTC) + timedelta(seconds=90),
    )
    db.add(third)
    db.commit()

    from app.core.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token(str(supervisor.id))}"}
    response = client.post(
        "/api/v1/alarms/correlate?window_seconds=300", headers=headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_alarms"] == 3
    same_line_groups = [
        group for group in payload["groups"] if group["reason"] == "same_equipment"
    ]
    cascade_groups = [
        group for group in payload["groups"] if group["reason"] == "line_cascade"
    ]
    # 同设备两条合并为一组。
    assert any(
        group["alarm_ids"] == sorted([first.id, second.id])
        for group in same_line_groups
    )
    # 同产线级联把三台设备的报警并为一个大组（Line-AI 两条 + Line-Other 一条
    # 不在同产线，因此 Line-Other 单独成组；这里验证级联只发生在 Line-AI）。
    assert all(
        set(group["equipment_ids"]) != {equipment.id, other_line.id}
        for group in cascade_groups
    )


def test_decision_support_links_open_work_order(client, db, supervisor, equipment_type):
    equipment, alarm = _setup(db)
    equipment.equipment_type_id = equipment_type.id
    work_order = WorkOrder(
        code="WO-AI-001",
        title="轴承温度越限点检",
        equipment_id=equipment.id,
        order_type=WorkOrderTypeEnum.preventive,
        priority=PriorityEnum.P2,
        status=WorkOrderStatusEnum.in_progress,
    )
    db.add(work_order)
    db.commit()

    from app.core.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token(str(supervisor.id))}"}
    response = client.post(f"/api/v1/alarms/{alarm.id}/analyze", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["related_work_order_id"] == work_order.id

    record = db.query(AlarmAnalysisRecord).filter_by(alarm_id=alarm.id).one()
    related = record.evidence["decision_support"]["related_work_orders"]
    assert any(item["code"] == "WO-AI-001" for item in related)


def test_no_device_control_endpoints_added(client):
    """安全：Alarm Intelligence 不引入任何设备控制端点。"""
    schema = client.get("/openapi.json").json()
    alarm_paths = {path for path in schema["paths"] if "/alarms" in path}
    assert alarm_paths == {
        "/api/v1/alarms",
        "/api/v1/alarms/correlate",
        "/api/v1/alarms/{alarm_id}/acknowledge",
        "/api/v1/alarms/{alarm_id}/analyze",
        "/api/v1/alarms/{alarm_id}/analysis",
    }
    for path in alarm_paths:
        assert "write" not in path
        assert "execute" not in path
