"""工业网关 API 端点测试：状态 / 节点 / 测试连接 / 手动同步 / 权限。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from app.industrial_gateway.mapping import seed_mappings_from_config
from app.industrial_gateway.opcua.client import MockOpcUaClient
from app.industrial_gateway.opcua.service import OpcUaGatewayService
from app.industrial_gateway.simulator.generator import MotorSimulator
from app.models.intelligence import TelemetryRecord

GATEWAY_METRICS: list[tuple[str, str, str]] = [
    ("Temperature", "temperature", "celsius"),
    ("Vibration", "vibration", "mm/s"),
    ("Current", "current", "A"),
    ("Speed", "speed", "rpm"),
    ("Voltage", "voltage", "V"),
    ("LoadRatio", "load", "%"),
]


def _seed_runtime(db, tmp_path: Path, equipment_code: str) -> OpcUaGatewayService:
    """为 API 测试装配：映射配置落库 + Mock 运行时单例。"""
    config = {
        "mappings": [
            {
                "node_id": f"ns=2;s=Motor001.{name}",
                "equipment_code": equipment_code,
                "metric": metric,
                "unit": unit,
            }
            for name, metric, unit in GATEWAY_METRICS
        ]
    }
    config_path = tmp_path / "gateway-api-mapping.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    seed_mappings_from_config(db, config_path)

    simulator = MotorSimulator(seed=42, scenario="normal")
    base_provider = simulator.value_provider()
    clock = {"last": datetime.now(UTC)}

    def provider(node_id: str):
        value, _ = base_provider(node_id)
        timestamp = datetime.now(UTC)
        if timestamp <= clock["last"]:
            timestamp = clock["last"] + timedelta(microseconds=1)
        clock["last"] = timestamp
        return value, timestamp

    service = OpcUaGatewayService(
        MockOpcUaClient(value_provider=provider),
        mode="mock",
        poll_interval_seconds=5.0,
        mapping_config_path=str(config_path),
        before_sync=simulator.advance,
    )
    return service


@pytest.fixture
def gateway_runtime(db, tmp_path, equipment, monkeypatch):
    service = _seed_runtime(db, tmp_path, equipment.code)
    monkeypatch.setattr(
        "app.industrial_gateway.opcua.service._gateway_runtime", service
    )
    return service


def test_gateway_status_requires_auth(client):
    response = client.get("/api/v1/gateway/status")
    assert response.status_code == 401


def test_gateway_status_reports_read_only_connection(
    client, auth_supervisor, gateway_runtime
):
    response = client.get("/api/v1/gateway/status", headers=auth_supervisor)
    assert response.status_code == 200
    payload = response.json()
    assert payload["read_only"] is True
    assert payload["runtime"]["read_only"] is True
    assert payload["connection"]["protocol"] == "opcua"
    assert payload["connection"]["status"] == "disconnected"
    assert payload["connection"]["endpoint"].startswith("mock://")


def test_gateway_nodes_lists_mapped_devices(client, auth_technician, gateway_runtime):
    response = client.get("/api/v1/gateway/nodes", headers=auth_technician)
    assert response.status_code == 200
    nodes = response.json()["nodes"]
    assert len(nodes) == len(GATEWAY_METRICS)
    by_metric = {node["metric_name"]: node for node in nodes}
    assert by_metric["temperature"]["node_id"] == "ns=2;s=Motor001.Temperature"
    assert by_metric["temperature"]["equipment_code"] == "EQ-001"
    assert all(node["last_value"] is None for node in nodes)


def test_gateway_test_connect_round_trip(client, auth_supervisor, gateway_runtime):
    response = client.post("/api/v1/gateway/test-connect", headers=auth_supervisor)
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["probe_node"] == "ns=2;s=Motor001.Current"
    assert payload["error"] is None
    # 测试连接只读探测，不写遥测。
    assert payload["sample_value"] is not None


def test_gateway_sync_ingests_telemetry(
    client, auth_supervisor, gateway_runtime, db, equipment
):
    response = client.post("/api/v1/gateway/sync", headers=auth_supervisor)
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["snapshots_ingested"] == 1
    assert payload["accepted"] == len(GATEWAY_METRICS)

    telemetry = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.equipment_id == equipment.id)
        .all()
    )
    assert len(telemetry) == 1
    assert telemetry[0].scenario == "opcua"


def test_gateway_sync_forbidden_for_technician(
    client, auth_technician, gateway_runtime
):
    response = client.post("/api/v1/gateway/sync", headers=auth_technician)
    assert response.status_code == 403


def test_gateway_exposes_no_write_endpoints(client):
    """安全：网关 API 面上不允许出现任何写 PLC 的端点。

    订阅 start/stop 是网关自身的运行控制，不是设备写操作；
    任何 PUT/DELETE/PATCH 以及面向节点值的写端点都被禁止。
    """
    schema = client.get("/openapi.json").json()
    gateway_paths = {
        path: methods
        for path, methods in schema["paths"].items()
        if "/gateway/" in path
    }
    assert set(gateway_paths) == {
        "/api/v1/gateway/status",
        "/api/v1/gateway/nodes",
        "/api/v1/gateway/test-connect",
        "/api/v1/gateway/sync",
        "/api/v1/gateway/mappings/reload",
        "/api/v1/gateway/subscriptions",
        "/api/v1/gateway/subscriptions/start",
        "/api/v1/gateway/subscriptions/stop",
    }
    for _path, methods in gateway_paths.items():
        assert not ({"put", "delete", "patch"} & set(methods))
    # 不存在面向 NodeId 值的写端点。
    assert not any("write" in path for path in gateway_paths)
