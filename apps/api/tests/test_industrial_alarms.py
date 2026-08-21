"""工业报警（Industrial Alarm）事件流水线测试。

覆盖（需求第十阶段 5：Alarm generation）：

- 报警状态判定（NORMAL/WARNING/CRITICAL）；
- fault 事件产生 CRITICAL 报警；
- 状态未变化时不重复产生；
- 恢复正常后报警被解除（cleared_at）；
- /alarms API 与人工确认权限。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from sqlalchemy.orm import Session

from app.industrial_gateway.alarms import (
    ALARM_STATE_CRITICAL,
    ALARM_STATE_NORMAL,
    ALARM_STATE_WARNING,
    build_alarm_message,
    evaluate_alarm_state,
)
from app.industrial_gateway.models import IndustrialAlarm
from app.industrial_gateway.opcua.client import MockOpcUaClient
from app.industrial_gateway.opcua.models import NodeRead
from app.industrial_gateway.opcua.service import OpcUaGatewayService
from app.industrial_gateway.opcua.subscription import (
    MockSubscriptionClient,
    NodeDataChange,
)
from app.industrial_gateway.simulator.generator import MotorSimulator
from app.models.base import EquipmentStatusEnum, RiskLevelEnum
from app.models.equipment import Equipment

HEALTHY_FIELDS: dict[str, float | bool] = {
    "bearing_temperature": 55.0,
    "vibration_rms": 1.8,
    "motor_current": 12.0,
    "load_ratio": 60.0,
    "motor_voltage": 380.0,
}

METRIC_UNITS: dict[str, str] = {
    "temperature": "celsius",
    "vibration": "mm/s",
    "current": "A",
    "speed": "rpm",
    "voltage": "V",
    "load": "%",
}


def test_evaluate_alarm_state_classification():
    assert (
        evaluate_alarm_state(dict(HEALTHY_FIELDS), alarm_active=False)
        == ALARM_STATE_NORMAL
    )
    warning = {**HEALTHY_FIELDS, "bearing_temperature": 80.0}
    assert evaluate_alarm_state(warning, alarm_active=False) == ALARM_STATE_WARNING
    overcurrent = {**HEALTHY_FIELDS, "motor_current": 30.0}
    assert evaluate_alarm_state(overcurrent, alarm_active=False) == ALARM_STATE_WARNING
    low_voltage = {**HEALTHY_FIELDS, "motor_voltage": 330.0}
    assert evaluate_alarm_state(low_voltage, alarm_active=False) == ALARM_STATE_WARNING
    critical = {**HEALTHY_FIELDS}
    assert evaluate_alarm_state(critical, alarm_active=True) == ALARM_STATE_CRITICAL


def test_build_alarm_message_contains_offenders():
    warning = {**HEALTHY_FIELDS, "bearing_temperature": 82.5, "vibration_rms": 4.8}
    message = build_alarm_message(ALARM_STATE_WARNING, warning, alarm_active=False)
    assert "WARNING" in message
    assert "轴承温度=82.5" in message
    assert "振动 RMS=4.8" in message


def _setup_equipment_with_alarm_node(db) -> Equipment:
    equipment = Equipment(
        code="EQ-ALM-01",
        name="报警验证电机",
        status=EquipmentStatusEnum.running,
        risk_level=RiskLevelEnum.low,
        qr_token="qr-alm-01",
    )
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment


def _make_alarm_service(db, tmp_path: Path, equipment: Equipment):
    """构建带 Alarm 节点映射的订阅服务。"""
    entries = [
        ("Temperature", "temperature"),
        ("Vibration", "vibration"),
        ("Current", "current"),
        ("Speed", "speed"),
        ("Voltage", "voltage"),
        ("LoadRatio", "load"),
        ("Alarm", "alarm"),  # informational：报警位
    ]
    config = {
        "mappings": [
            {
                "node_id": f"ns=2;s=Motor001.{name}",
                "equipment_code": equipment.code,
                "metric": metric,
                "unit": METRIC_UNITS.get(metric, ""),
                **({"informational": True} if metric == "alarm" else {}),
            }
            for name, metric in entries
        ]
    }
    config_path = tmp_path / "alarm-mapping.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    simulator = MotorSimulator(seed=42, scenario="normal")
    clock = {"now": datetime.now(UTC)}

    def initial_provider(node_id: str) -> NodeRead:
        name = node_id.rsplit(".", 1)[-1]
        value: float | bool
        if name == "Alarm":
            value = False
        elif name == "RunningState":
            value = True
        else:
            metric = next(m for n, m in entries if n == name)
            field_by_metric = {
                "temperature": "bearing_temperature",
                "vibration": "vibration_rms",
                "current": "motor_current",
                "speed": "rotational_speed",
                "voltage": "motor_voltage",
                "load": "load_ratio",
            }
            value = float(HEALTHY_FIELDS[field_by_metric[metric]])
        return NodeRead(
            node_id=node_id, value=value, source_timestamp=clock["now"], quality="good"
        )

    sub_client = MockSubscriptionClient(initial_provider=initial_provider)
    service = OpcUaGatewayService(
        MockOpcUaClient(value_provider=simulator.value_provider()),
        mode="mock",
        poll_interval_seconds=5.0,
        mapping_config_path=str(config_path),
        before_sync=simulator.advance,
        subscription_client_factory=lambda: sub_client,
        session_factory=lambda: Session(bind=db.get_bind(), autoflush=False),
    )
    return service, sub_client


def _publish_values(
    sub_client: MockSubscriptionClient,
    fields: dict[str, float | bool],
    *,
    alarm_active: bool,
    clock: dict,
) -> None:
    payload = {
        "ns=2;s=Motor001.Temperature": fields["bearing_temperature"],
        "ns=2;s=Motor001.Vibration": fields["vibration_rms"],
        "ns=2;s=Motor001.Current": fields["motor_current"],
        "ns=2;s=Motor001.Speed": 1480.0,
        "ns=2;s=Motor001.Voltage": fields["motor_voltage"],
        "ns=2;s=Motor001.LoadRatio": fields["load_ratio"],
        "ns=2;s=Motor001.Alarm": alarm_active,
    }
    for node_id, value in payload.items():
        clock["now"] += timedelta(seconds=1)
        sub_client.publish(
            NodeDataChange(
                node_id=node_id,
                value=value,
                source_timestamp=clock["now"],
                status_code=0,
                quality="good",
            )
        )


@pytest.mark.asyncio
async def test_fault_events_generate_critical_alarm_once(db, tmp_path):
    """fault 值 + Alarm 位 → CRITICAL 报警；状态不变则不重复产生。"""
    equipment = _setup_equipment_with_alarm_node(db)
    service, sub_client = _make_alarm_service(db, tmp_path, equipment)
    result = await service.start_subscription(db, client=sub_client)
    assert result["ok"] is True

    clock = {"now": datetime.now(UTC)}
    fault_fields = {
        "bearing_temperature": 96.0,
        "vibration_rms": 4.9,
        "motor_current": 19.5,
        "load_ratio": 66.0,
        "motor_voltage": 380.0,
    }
    _publish_values(sub_client, fault_fields, alarm_active=True, clock=clock)
    flush = await service.flush_now(db)

    assert flush["snapshots_ingested"] == 1
    alarms = db.query(IndustrialAlarm).all()
    assert len(alarms) == 1
    assert alarms[0].severity == ALARM_STATE_CRITICAL
    assert alarms[0].source == "opcua-subscription"
    assert alarms[0].acknowledged is False
    assert alarms[0].cleared_at is None
    assert "CRITICAL" in alarms[0].message

    # 状态未变化：继续发布同类事件不重复产生报警。
    _publish_values(sub_client, fault_fields, alarm_active=True, clock=clock)
    await service.flush_now(db)
    assert db.query(IndustrialAlarm).count() == 1
    await service.stop_subscription(db)


@pytest.mark.asyncio
async def test_warning_alarm_raised_and_cleared_on_recovery(db, tmp_path):
    """温度越限 → WARNING；恢复正常 → cleared_at 回填。"""
    equipment = _setup_equipment_with_alarm_node(db)
    service, sub_client = _make_alarm_service(db, tmp_path, equipment)
    await service.start_subscription(db, client=sub_client)

    clock = {"now": datetime.now(UTC)}
    warning_fields = {
        "bearing_temperature": 82.0,
        "vibration_rms": 2.0,
        "motor_current": 12.5,
        "load_ratio": 61.0,
        "motor_voltage": 380.0,
    }
    _publish_values(sub_client, warning_fields, alarm_active=False, clock=clock)
    await service.flush_now(db)

    alarms = db.query(IndustrialAlarm).all()
    assert len(alarms) == 1
    assert alarms[0].severity == ALARM_STATE_WARNING
    assert "轴承温度" in alarms[0].message

    # 恢复正常 → 解除。
    _publish_values(sub_client, HEALTHY_FIELDS, alarm_active=False, clock=clock)
    await service.flush_now(db)
    db.refresh(alarms[0])
    assert alarms[0].cleared_at is not None
    assert db.query(IndustrialAlarm).count() == 1
    await service.stop_subscription(db)


@pytest.mark.asyncio
async def test_polling_only_path_does_not_create_gateway_alarms(db, tmp_path):
    """轮询路径保持既有行为：不产生工业报警记录（告警仍走 AnomalyEvent）。"""
    equipment = _setup_equipment_with_alarm_node(db)
    service, _sub_client = _make_alarm_service(db, tmp_path, equipment)
    # 不启动订阅，仅轮询同步。
    sync_result = await service.sync_once(db)
    assert sync_result.ok is True
    assert db.query(IndustrialAlarm).count() == 0


def test_alarms_api_requires_auth(client):
    assert client.get("/api/v1/alarms").status_code == 401


def test_alarms_acknowledge_permission(client, db, supervisor, technician, equipment):
    alarm = IndustrialAlarm(
        equipment_id=equipment.id,
        severity=ALARM_STATE_WARNING,
        message="测试报警",
        source="opcua-subscription",
    )
    db.add(alarm)
    db.commit()
    db.refresh(alarm)

    from app.core.security import create_access_token

    tech_headers = {
        "Authorization": f"Bearer {create_access_token(str(technician.id))}"
    }
    sup_headers = {"Authorization": f"Bearer {create_access_token(str(supervisor.id))}"}

    # 工程师无权确认。
    denied = client.post(f"/api/v1/alarms/{alarm.id}/acknowledge", headers=tech_headers)
    assert denied.status_code == 403

    ok = client.post(f"/api/v1/alarms/{alarm.id}/acknowledge", headers=sup_headers)
    assert ok.status_code == 200
    assert ok.json()["acknowledged"] is True

    listing = client.get("/api/v1/alarms?status=acknowledged", headers=sup_headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
