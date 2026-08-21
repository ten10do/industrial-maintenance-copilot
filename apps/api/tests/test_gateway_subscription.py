"""OPC UA DataChange 订阅（事件驱动）测试。

覆盖（需求第十阶段 1/2/3/4/6/7/8）：

1. Subscription Mock callback；
2. DataChange → Telemetry（复用既有 AI 链路，无第二套 pipeline）；
3. Duplicate event suppression；
4. Bad quality event rejected；
6. Subscription failure recovery；
7. Polling fallback（订阅失败时轮询路径保持可用）；
8. Existing AI pipeline regression（fault 事件触发完整 AI 链路）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from app.industrial_gateway.models import (
    GATEWAY_STATUS_CONNECTED,
    GatewaySubscription,
)
from app.industrial_gateway.opcua.client import MockOpcUaClient
from app.industrial_gateway.opcua.models import NodeRead
from app.industrial_gateway.opcua.service import OpcUaGatewayService
from app.industrial_gateway.opcua.subscription import (
    SUBSCRIPTION_STATUS_ACTIVE,
    SUBSCRIPTION_STATUS_ERROR,
    MockSubscriptionClient,
    NodeDataChange,
)
from app.industrial_gateway.simulator.generator import MotorSimulator
from app.models.base import EquipmentStatusEnum, RiskLevelEnum
from app.models.equipment import Equipment
from app.models.intelligence import (
    AnomalyEvent,
    OperationApproval,
    RiskPrediction,
    TelemetryRecord,
)

FULL_NODES: list[tuple[str, str]] = [
    ("Temperature", "temperature"),
    ("Vibration", "vibration"),
    ("Current", "current"),
    ("Speed", "speed"),
    ("Voltage", "voltage"),
    ("LoadRatio", "load"),
]

METRIC_UNITS: dict[str, str] = {
    "temperature": "celsius",
    "vibration": "mm/s",
    "current": "A",
    "speed": "rpm",
    "voltage": "V",
    "load": "%",
}


class _ScriptedClock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def tick(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def _make_service(
    db,
    tmp_path: Path,
    *,
    scenario: str = "normal",
) -> tuple[OpcUaGatewayService, MotorSimulator, MockSubscriptionClient]:
    """构建带映射配置的网关服务 + Mock 订阅客户端。"""
    equipment = Equipment(
        code="EQ-SUB-01",
        name="订阅验证电机",
        status=EquipmentStatusEnum.running,
        risk_level=RiskLevelEnum.low,
        qr_token="qr-sub-01",
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
                "unit": METRIC_UNITS[metric],
            }
            for name, metric in FULL_NODES
        ]
    }
    config_path = tmp_path / f"sub-mapping-{scenario}.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    simulator = MotorSimulator(seed=42, scenario=scenario)

    def initial_provider(node_id: str) -> NodeRead:
        _, metric = next(
            (name, metric)
            for name, metric in FULL_NODES
            if node_id == f"ns=2;s=Motor001.{name}"
        )
        field_by_metric = {
            "temperature": "bearing_temperature",
            "vibration": "vibration_rms",
            "current": "motor_current",
            "speed": "rotational_speed",
            "voltage": "motor_voltage",
            "load": "load_ratio",
        }
        values = simulator.current_values()
        return NodeRead(
            node_id=node_id,
            value=values.get(field_by_metric[metric]),
            source_timestamp=datetime.now(UTC),
            quality="good",
        )

    subscription_client = MockSubscriptionClient(initial_provider=initial_provider)
    service = OpcUaGatewayService(
        MockOpcUaClient(value_provider=simulator.value_provider()),
        mode="mock",
        poll_interval_seconds=5.0,
        mapping_config_path=str(config_path),
        before_sync=simulator.advance,
        subscription_client_factory=lambda: subscription_client,
        subscription_sampling_ms=1000.0,
        subscription_debounce_ms=1000.0,
    )
    return service, simulator, subscription_client


def _publish_all(
    subscription_client: MockSubscriptionClient,
    simulator: MotorSimulator,
    clock: _ScriptedClock,
) -> int:
    """把当前 tick 的全部指标节点作为 DataChange 事件发布。"""
    values = simulator.current_values()
    published = 0
    for name, _metric in FULL_NODES:
        published += subscription_client.publish(
            NodeDataChange(
                node_id=f"ns=2;s=Motor001.{name}",
                value=values[name],
                source_timestamp=clock.tick(),
                status_code=0,
                quality="good",
            )
        )
    return published


@pytest.mark.asyncio
async def test_subscription_mock_callback_invoked(db, tmp_path):
    """1. Subscription Mock callback：subscribe 后 publish 触发回调。"""
    _service, simulator, sub_client = _make_service(db, tmp_path)
    received: list[NodeDataChange] = []
    await sub_client.connect()
    handle = await sub_client.subscribe(
        [f"ns=2;s=Motor001.{name}" for name, _ in FULL_NODES],
        received.append,
        sampling_interval_ms=1000.0,
    )
    assert handle.node_ids.__len__() == 6

    simulator.advance()
    delivered = _publish_all(sub_client, simulator, _ScriptedClock())

    assert delivered == 6
    assert len(received) == 6
    assert all(change.quality == "good" for change in received)


@pytest.mark.asyncio
async def test_datachange_events_ingest_telemetry_via_existing_pipeline(db, tmp_path):
    """2. DataChange → Telemetry：事件经缓冲进入既有 ingest_snapshot。"""
    service, simulator, sub_client = _make_service(db, tmp_path)
    result = await service.start_subscription(db, client=sub_client)
    assert result["ok"] is True
    assert result["subscription_status"] == SUBSCRIPTION_STATUS_ACTIVE
    assert len(result["active_nodes"]) == 6

    simulator.advance()
    _publish_all(sub_client, simulator, _ScriptedClock())
    flush = await service.flush_now(db)

    assert flush["events"] == 6
    assert flush["snapshots_ingested"] == 1
    telemetry = db.query(TelemetryRecord).one()
    assert telemetry.scenario == "opcua"
    values = simulator.current_values()
    assert telemetry.bearing_temperature == pytest.approx(values["Temperature"])
    # 订阅行已持久化并计数。
    rows = db.query(GatewaySubscription).all()
    assert len(rows) == 6
    assert all(row.status == "active" for row in rows)
    assert all(row.event_count >= 6 for row in rows)
    await service.stop_subscription(db)


@pytest.mark.asyncio
async def test_duplicate_events_are_suppressed(db, tmp_path):
    """3. Duplicate suppression：同节点时间戳未前进的事件被抑制。"""
    service, simulator, sub_client = _make_service(db, tmp_path)
    await service.start_subscription(db, client=sub_client)

    simulator.advance()
    clock = _ScriptedClock()
    values = simulator.current_values()
    stale_ts = clock.tick()
    for _ in range(5):
        sub_client.publish(
            NodeDataChange(
                node_id="ns=2;s=Motor001.Temperature",
                value=values["Temperature"],
                source_timestamp=stale_ts,
                status_code=0,
                quality="good",
            )
        )

    assert service._event_totals["received"] == 5
    assert service._event_totals["duplicates_suppressed"] == 4
    assert service._event_totals["accepted"] == 1
    flush = await service.flush_now(db)
    assert flush["events"] == 1  # batch aggregation：窗口内只保留最新值
    assert flush["snapshots_ingested"] == 0  # 快照不完整（仅温度）被跳过
    await service.stop_subscription(db)


@pytest.mark.asyncio
async def test_bad_quality_event_rejected(db, tmp_path):
    """4. Bad quality event rejected：坏质量事件不进入业务。"""
    service, simulator, sub_client = _make_service(db, tmp_path)
    await service.start_subscription(db, client=sub_client)

    simulator.advance()
    clock = _ScriptedClock()
    values = simulator.current_values()
    for name, _metric in FULL_NODES:
        quality = "bad" if name == "Temperature" else "good"
        sub_client.publish(
            NodeDataChange(
                node_id=f"ns=2;s=Motor001.{name}",
                value=None if name == "Current" else values[name],
                source_timestamp=clock.tick(),
                status_code=0x80AA_0000 if quality == "bad" else 0,
                quality=quality,
            )
        )

    assert service._event_totals["rejected"] == 2  # 坏质量温度 + 缺失电流
    flush = await service.flush_now(db)
    assert flush["snapshots_ingested"] == 0
    assert db.query(TelemetryRecord).count() == 0
    await service.stop_subscription(db)


@pytest.mark.asyncio
async def test_subscription_failure_recovery(db, tmp_path):
    """6. Subscription failure recovery：失败回退后可恢复订阅。"""
    service, _simulator, sub_client = _make_service(db, tmp_path)
    sub_client.set_available(False)

    failed = await service.start_subscription(db, client=sub_client)
    assert failed["ok"] is False
    assert failed["status"] == SUBSCRIPTION_STATUS_ERROR
    assert "不可达" in failed["error"]
    assert service.subscription_status()["read_only"] is True

    sub_client.set_available(True)
    recovered = await service.start_subscription(db, client=sub_client)
    assert recovered["ok"] is True
    assert recovered["subscription_status"] == SUBSCRIPTION_STATUS_ACTIVE

    stopped = await service.stop_subscription(db)
    assert stopped["ok"] is True
    rows = db.query(GatewaySubscription).all()
    assert rows and all(row.status == "inactive" for row in rows)


@pytest.mark.asyncio
async def test_polling_fallback_when_subscription_unavailable(db, tmp_path):
    """7. Polling fallback：订阅不可用时轮询路径照常入库。"""
    service, _simulator, sub_client = _make_service(db, tmp_path)
    sub_client.set_available(False)
    failed = await service.start_subscription(db, client=sub_client)
    assert failed["ok"] is False

    sync_result = await service.sync_once(db)
    assert sync_result.ok is True
    assert sync_result.snapshots_ingested == 1
    assert service.connection_status == GATEWAY_STATUS_CONNECTED
    assert db.query(TelemetryRecord).count() == 1


@pytest.mark.asyncio
async def test_fault_events_trigger_full_ai_chain_regression(db, tmp_path):
    """8. Existing AI pipeline regression：fault 事件走完整既有链路。"""
    service, simulator, sub_client = _make_service(db, tmp_path, scenario="fault")
    await service.start_subscription(db, client=sub_client)

    # 预热到强劣化区间后再发布事件。
    for _ in range(16):
        simulator.advance()
    _publish_all(sub_client, simulator, _ScriptedClock())
    flush = await service.flush_now(db)

    assert flush["snapshots_ingested"] == 1
    assert flush["anomalies"] == 1
    assert flush["work_orders_created"] == 1

    equipment = db.query(Equipment).filter(Equipment.code == "EQ-SUB-01").one()
    assert (
        db.query(AnomalyEvent).filter(AnomalyEvent.equipment_id == equipment.id).count()
        == 1
    )
    assert (
        db.query(RiskPrediction)
        .filter(RiskPrediction.equipment_id == equipment.id)
        .count()
        == 1
    )
    assert (
        db.query(OperationApproval)
        .filter(OperationApproval.equipment_id == equipment.id)
        .count()
        == 1
    )
    await service.stop_subscription(db)


@pytest.mark.asyncio
async def test_subscription_read_only_guard(db, tmp_path):
    """安全：订阅客户端显式拒绝写操作。"""
    _service, _simulator, sub_client = _make_service(db, tmp_path)
    await sub_client.connect()
    with pytest.raises(PermissionError, match="read-only"):
        await sub_client.write_node("ns=2;s=Motor001.Temperature", 999)
