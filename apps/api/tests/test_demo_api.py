"""Demo 编排 API 测试（Simulation only）。

重点：

1. 场景白名单校验；
2. 非 Mock 网关模式拒绝（不得指向真实 OPC UA Server）；
3. 全链路：fault 场景产生 Telemetry/Anomaly/Prediction/Alarm/
   WorkOrder 且共享同一 trace_id；
4. Demo 流程零 PLC write（write_node 间谍断言）；
5. 权限：supervisor 可编排，technician 只读；
6. /demo/state 聚合真实领域记录；无数据时字段为 null。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.core.config import settings
from app.core.security import create_access_token
from app.industrial_gateway.models import IndustrialAlarm
from app.industrial_gateway.opcua.client import MockOpcUaClient
from app.industrial_gateway.opcua.service import reset_gateway_runtime
from app.models.base import EquipmentStatusEnum, RiskLevelEnum
from app.models.equipment import Equipment
from app.models.intelligence import (
    AnomalyEvent,
    OperationApproval,
    RiskPrediction,
    TelemetryRecord,
)
from app.models.workorder import WorkOrder

MOTOR_CODE = "MOTOR-001"


def _auth_headers(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


def _setup_mock_gateway(monkeypatch, db, tmp_path: Path) -> Equipment:
    """启用 Mock 网关并把 Motor001 映射到测试设备。"""
    equipment = Equipment(
        code=MOTOR_CODE,
        name="演示电机",
        status=EquipmentStatusEnum.running,
        risk_level=RiskLevelEnum.low,
        qr_token="qr-motor-demo",
    )
    db.add(equipment)
    db.commit()
    db.refresh(equipment)

    config = {
        "mappings": [
            {
                "node_id": f"ns=2;s=Motor001.{name}",
                "equipment_code": MOTOR_CODE,
                "metric": metric,
                "unit": unit,
            }
            for name, metric, unit in [
                ("Temperature", "temperature", "celsius"),
                ("Vibration", "vibration", "mm/s"),
                ("Current", "current", "A"),
                ("Speed", "speed", "rpm"),
                ("Voltage", "voltage", "V"),
                ("LoadRatio", "load", "%"),
                ("RunningState", "running", ""),
                ("Alarm", "alarm", ""),
            ]
        ]
    }
    mapping_path = tmp_path / "demo-mapping.yaml"
    mapping_path.write_text(
        yaml.safe_dump(config, allow_unicode=True), encoding="utf-8"
    )

    monkeypatch.setattr(settings, "GATEWAY_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_MODE", "mock")
    monkeypatch.setattr(settings, "GATEWAY_MAPPING_CONFIG", str(mapping_path))
    reset_gateway_runtime()
    return equipment


@pytest.fixture(autouse=True)
def _reset_runtime_after_test():
    yield
    reset_gateway_runtime()


def test_invalid_scenario_rejected_400(client, supervisor):
    response = client.post(
        "/api/v1/demo/simulator/scenario",
        json={"scenario": "explode"},
        headers=_auth_headers(supervisor),
    )
    assert response.status_code == 400


def test_scenario_requires_enabled_mock_gateway(client, supervisor, monkeypatch):
    """GATEWAY_ENABLED=false 时拒绝并给出配置指引。"""
    monkeypatch.setattr(settings, "GATEWAY_ENABLED", False)
    response = client.post(
        "/api/v1/demo/simulator/scenario",
        json={"scenario": "fault"},
        headers=_auth_headers(supervisor),
    )
    assert response.status_code == 409
    assert "simulation only" in response.json()["detail"]


def test_scenario_refused_in_real_opcua_mode(
    client, supervisor, db, tmp_path, monkeypatch
):
    """GATEWAY_MODE=opcua（真实连接）时 Demo 编排必须拒绝。"""
    _setup_mock_gateway(monkeypatch, db, tmp_path)
    monkeypatch.setattr(settings, "GATEWAY_MODE", "opcua")
    reset_gateway_runtime()

    response = client.post(
        "/api/v1/demo/simulator/scenario",
        json={"scenario": "fault"},
        headers=_auth_headers(supervisor),
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "opcua" in detail
    assert "never targets real OPC UA servers" in detail


def test_fault_scenario_full_chain_with_shared_trace(
    client, supervisor, db, tmp_path, monkeypatch
):
    """fault 场景：DataChange → …→ Alarm/WO 共享同一 trace_id；零 write_node。"""
    equipment = _setup_mock_gateway(monkeypatch, db, tmp_path)

    write_calls: list[tuple] = []
    monkeypatch.setattr(
        MockOpcUaClient,
        "write_node",
        lambda self, node_id, value: write_calls.append((node_id, value)),
    )

    response = client.post(
        "/api/v1/demo/simulator/scenario",
        json={"scenario": "fault", "equipment_code": MOTOR_CODE},
        headers=_auth_headers(supervisor),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario"] == "fault"
    assert payload["simulation_only"] is True
    assert payload["published_events"] > 0
    assert payload["snapshots_ingested"] == 1
    trace_id = payload["trace_id"]
    assert trace_id

    # 零 PLC write。
    assert write_calls == []

    # 领域实体全部存在且共享 trace。
    print(
        "DBG counts:",
        {
            "telemetry": db.query(TelemetryRecord).count(),
            "anomaly": db.query(AnomalyEvent).count(),
            "prediction": db.query(RiskPrediction).count(),
            "alarm": db.query(IndustrialAlarm).count(),
            "work_order": db.query(WorkOrder).count(),
            "approval": db.query(OperationApproval).count(),
            "eq_id": equipment.id,
            "telemetry_rows": [
                (t.equipment_id, t.is_anomaly, t.bearing_temperature, t.vibration_rms)
                for t in db.query(TelemetryRecord).all()
            ],
        },
    )
    telemetry = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.equipment_id == equipment.id)
        .one()
    )
    anomaly = (
        db.query(AnomalyEvent).filter(AnomalyEvent.equipment_id == equipment.id).one()
    )
    prediction = (
        db.query(RiskPrediction)
        .filter(RiskPrediction.equipment_id == equipment.id)
        .one()
    )
    alarm = (
        db.query(IndustrialAlarm)
        .filter(IndustrialAlarm.equipment_id == equipment.id)
        .one()
    )
    work_order = (
        db.query(WorkOrder).filter(WorkOrder.equipment_id == equipment.id).one()
    )
    approval = (
        db.query(OperationApproval)
        .filter(OperationApproval.equipment_id == equipment.id)
        .one()
    )
    shared = {
        telemetry.trace_id,
        anomaly.trace_id,
        prediction.trace_id,
        alarm.trace_id,
        work_order.trace_id,
        approval.trace_id,
        trace_id,
    }
    assert None not in shared
    assert len(shared) == 1


def test_normal_and_warning_scenarios_are_supported(
    client, supervisor, db, tmp_path, monkeypatch
):
    """normal/warning 同样受支持且确定性执行。"""
    _setup_mock_gateway(monkeypatch, db, tmp_path)

    for scenario in ("normal", "warning"):
        response = client.post(
            "/api/v1/demo/simulator/scenario",
            json={"scenario": scenario},
            headers=_auth_headers(supervisor),
        )
        assert response.status_code == 200
        assert response.json()["trace_id"]


def test_demo_state_aggregates_real_records(
    client, supervisor, db, tmp_path, monkeypatch
):
    """/demo/state 返回真实领域对象；trace 与工单一致。"""
    _setup_mock_gateway(monkeypatch, db, tmp_path)
    headers = _auth_headers(supervisor)

    empty_state = client.get("/api/v1/demo/state", headers=headers)
    assert empty_state.status_code == 200
    assert empty_state.json()["telemetry"] is None
    assert empty_state.json()["alarm"] is None

    created = client.post(
        "/api/v1/demo/simulator/scenario",
        json={"scenario": "fault", "equipment_code": MOTOR_CODE},
        headers=headers,
    )
    assert created.status_code == 200

    state = client.get(
        f"/api/v1/demo/state?equipment_code={MOTOR_CODE}", headers=headers
    ).json()
    assert state["equipment"]["code"] == MOTOR_CODE
    assert state["telemetry"]["id"] > 0
    assert state["anomaly"]["id"] > 0
    assert state["prediction"]["model_version"]
    assert state["alarm"]["severity"] in {"WARNING", "CRITICAL"}
    assert state["work_order"]["code"]
    assert state["analysis"] is not None or state["prediction"] is not None
    # 演示状态里的 trace 与真实工单一致。
    if state["work_order"]["trace_id"]:
        assert state["trace_id"] == state["work_order"]["trace_id"]


def test_scenario_permissions(
    client, supervisor, technician, db, tmp_path, monkeypatch
):
    """technician 不能编排场景（403）；可以读取演示状态。"""
    _setup_mock_gateway(monkeypatch, db, tmp_path)

    forbidden = client.post(
        "/api/v1/demo/simulator/scenario",
        json={"scenario": "fault"},
        headers=_auth_headers(technician),
    )
    assert forbidden.status_code == 403

    allowed_read = client.get("/api/v1/demo/state", headers=_auth_headers(technician))
    assert allowed_read.status_code == 200
