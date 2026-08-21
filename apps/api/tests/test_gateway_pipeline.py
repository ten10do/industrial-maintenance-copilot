"""OPC UA 网关链路集成测试。

覆盖（需求第十一阶段）：

1. OPC UA 连接 Mock；
2. 节点映射装载与解析；
3. OPC UA → 平台遥测转换并进入既有 AI 链路（Health Score /
   异常检测 / 故障预测 / 工单 / 审批）；
4. 坏质量数据不得写入业务；
5. 网关连接失败的回退行为。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from app.industrial_gateway.models import (
    GATEWAY_STATUS_CONNECTED,
    GATEWAY_STATUS_ERROR,
    GatewayConnection,
    OpcUaNodeMapping,
)
from app.industrial_gateway.opcua.client import MockOpcUaClient
from app.industrial_gateway.opcua.models import (
    QUALITY_BAD,
    TELEMETRY_SOURCE_OPCUA,
    NodeRead,
)
from app.industrial_gateway.opcua.service import OpcUaGatewayService
from app.industrial_gateway.simulator.generator import MotorSimulator
from app.models.base import EquipmentStatusEnum, RiskLevelEnum
from app.models.equipment import Equipment
from app.models.intelligence import (
    AnomalyEvent,
    MaintenanceRecommendation,
    OperationApproval,
    RiskPrediction,
    TelemetryRecord,
)

FULL_METRICS: list[tuple[str, str, str]] = [
    ("Temperature", "temperature", "celsius"),
    ("Vibration", "vibration", "mm/s"),
    ("Current", "current", "A"),
    ("Speed", "speed", "rpm"),
    ("Voltage", "voltage", "V"),
    ("LoadRatio", "load", "%"),
]


class _ScriptedClock:
    """确定性递增时间戳，避免跨同步重复。"""

    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def tick(self) -> datetime:
        self.now += timedelta(seconds=5)
        return self.now


class _BadQualityClient(MockOpcUaClient):
    """把指定后缀节点的读数注入为 OPC UA Bad 质量（测试用）。"""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.bad_suffix = "Temperature"

    async def read_node(self, node_id: str) -> NodeRead:
        read = await super().read_node(node_id)
        if node_id.endswith(self.bad_suffix):
            return NodeRead(
                node_id=node_id,
                value=read.value,
                source_timestamp=read.source_timestamp,
                status_code=0x80AA_0000,
                quality=QUALITY_BAD,
            )
        return read


def _make_equipment(db) -> Equipment:
    equipment = db.query(Equipment).filter(Equipment.code == "EQ-GW-01").first()
    if equipment is None:
        equipment = Equipment(
            code="EQ-GW-01",
            name="网关验证电机",
            status=EquipmentStatusEnum.running,
            risk_level=RiskLevelEnum.low,
            qr_token="qr-gw-01",
        )
        db.add(equipment)
        db.commit()
        db.refresh(equipment)
    return equipment


def _make_service(
    db,
    tmp_path: Path,
    *,
    scenario: str = "normal",
    metrics: list[tuple[str, str, str]] | None = None,
    value_override: Callable[[str, object], object] | None = None,
    client: MockOpcUaClient | None = None,
) -> tuple[OpcUaGatewayService, MotorSimulator]:
    """构建带临时映射配置的网关服务（Mock 客户端 + 确定性仿真）。"""
    equipment = _make_equipment(db)

    entries = metrics or FULL_METRICS
    config = {
        "mappings": [
            {
                "node_id": f"ns=2;s=Motor001.{name}",
                "equipment_code": equipment.code,
                "metric": metric,
                "unit": unit,
            }
            for name, metric, unit in entries
        ]
    }
    config_path = tmp_path / f"gw-mapping-{scenario}-{len(entries)}.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    simulator = MotorSimulator(seed=42, scenario=scenario)
    clock = _ScriptedClock()
    base_provider = simulator.value_provider()

    def provider(node_id: str):
        value, _ = base_provider(node_id)
        if value_override is not None:
            value = value_override(node_id, value)
        return value, clock.tick()

    if client is None:
        client = MockOpcUaClient(value_provider=provider)
    else:
        client.set_value_provider(provider)

    service = OpcUaGatewayService(
        client,
        mode="mock",
        poll_interval_seconds=5.0,
        mapping_config_path=str(config_path),
        before_sync=simulator.advance,
    )
    return service, simulator


@pytest.mark.asyncio
async def test_opcua_telemetry_conversion_ingests_into_ai_chain(db, tmp_path):
    """正常读数 → 质量校验 → 遥测入库（scenario=opcua）。"""
    service, simulator = _make_service(db, tmp_path)
    service.ensure_seed(db)
    assert db.query(OpcUaNodeMapping).count() == len(FULL_METRICS)

    result = await service.sync_once(db)

    assert result.ok is True
    assert result.reads_total == len(FULL_METRICS)
    assert result.accepted == len(FULL_METRICS)
    assert result.rejected == 0
    assert result.snapshots_ingested == 1
    assert len(result.telemetry_ids) == 1

    telemetry = db.get(TelemetryRecord, result.telemetry_ids[0])
    assert telemetry is not None
    assert telemetry.scenario == TELEMETRY_SOURCE_OPCUA
    # 转换正确性：节点值一一对应平台遥测字段。
    values = simulator.current_values()
    assert telemetry.bearing_temperature == pytest.approx(values["Temperature"])
    assert telemetry.vibration_rms == pytest.approx(values["Vibration"])
    assert telemetry.motor_current == pytest.approx(values["Current"])
    assert telemetry.rotational_speed == pytest.approx(values["Speed"])
    assert telemetry.motor_voltage == pytest.approx(values["Voltage"])
    assert telemetry.load_ratio == pytest.approx(values["LoadRatio"])
    assert telemetry.quality == pytest.approx(1.0)

    connection = db.query(GatewayConnection).one()
    assert connection.status == GATEWAY_STATUS_CONNECTED
    assert connection.last_connected_at is not None
    assert connection.last_sync_at is not None


@pytest.mark.asyncio
async def test_unit_conversion_applied_before_ingestion(db, tmp_path):
    """华氏温度按映射单位换算为摄氏后再入库。"""
    metrics = [
        ("Temperature", "temperature", "fahrenheit"),
        ("Vibration", "vibration", "mm/s"),
        ("Current", "current", "A"),
        ("Speed", "speed", "rpm"),
        ("Voltage", "voltage", "V"),
        ("LoadRatio", "load", "%"),
    ]
    service, simulator = _make_service(db, tmp_path, metrics=metrics)
    service.ensure_seed(db)

    result = await service.sync_once(db)

    assert result.ok is True
    assert result.snapshots_ingested == 1
    telemetry = db.query(TelemetryRecord).one()
    raw_fahrenheit = float(simulator.current_values()["Temperature"])
    assert telemetry.bearing_temperature == pytest.approx(
        (raw_fahrenheit - 32.0) * 5.0 / 9.0, abs=1e-3
    )


@pytest.mark.asyncio
async def test_opcua_fault_scenario_triggers_full_ai_chain(db, tmp_path):
    """fault 场景读数进入既有 AI 链路：异常 → 预测 → 策略 → 工单 → 审批。"""
    service, simulator = _make_service(db, tmp_path, scenario="fault")
    service.ensure_seed(db)

    # 预热到强劣化区间（温度逼近量程上限、振动越限）。
    for _ in range(16):
        simulator.advance()

    result = await service.sync_once(db)

    assert result.ok is True
    assert result.snapshots_ingested == 1
    assert result.anomalies == 1
    assert result.work_orders_created == 1

    equipment = db.query(Equipment).filter(Equipment.code == "EQ-GW-01").one()
    anomaly = (
        db.query(AnomalyEvent).filter(AnomalyEvent.equipment_id == equipment.id).one()
    )
    assert anomaly.fault_type in {"bearing_overheat", "bearing_wear"}
    prediction = (
        db.query(RiskPrediction)
        .filter(RiskPrediction.equipment_id == equipment.id)
        .count()
        == 1
    )
    assert prediction is True
    assert (
        db.query(MaintenanceRecommendation)
        .filter(MaintenanceRecommendation.equipment_id == equipment.id)
        .count()
        == 1
    )
    assert (
        db.query(OperationApproval)
        .filter(OperationApproval.equipment_id == equipment.id)
        .count()
        == 1
    )
    assert equipment.health_score < 100.0
    assert equipment.risk_level in {RiskLevelEnum.high, RiskLevelEnum.critical}


@pytest.mark.asyncio
async def test_bad_quality_and_missing_data_never_reach_business(db, tmp_path):
    """坏质量 / 缺失值被拒绝，业务表零写入。"""
    service, _ = _make_service(
        db,
        tmp_path,
        value_override=lambda node_id, value: (
            float("nan") if node_id.endswith("Current") else value
        ),
        client=_BadQualityClient(),
    )
    service.ensure_seed(db)

    result = await service.sync_once(db)

    assert result.ok is True
    assert result.rejected >= 2  # 坏质量温度 + NaN 电流
    assert "bad_quality" in result.reject_reasons
    assert "non_numeric" in result.reject_reasons
    # 快照不完整 → 整批跳过，业务零写入。
    assert result.snapshots_ingested == 0
    assert any("快照不完整" in detail for detail in result.skipped_details)
    assert db.query(TelemetryRecord).count() == 0


@pytest.mark.asyncio
async def test_partial_mapping_produces_no_snapshot(db, tmp_path):
    """只映射部分评估指标时，不完整快照不入库（防止误判传感器故障）。"""
    service, _ = _make_service(
        db, tmp_path, metrics=[("Temperature", "temperature", "celsius")]
    )
    service.ensure_seed(db)
    assert db.query(OpcUaNodeMapping).count() == 1

    result = await service.sync_once(db)

    assert result.ok is True
    assert result.accepted == 1
    assert result.snapshots_ingested == 0
    assert result.snapshots_skipped == 1
    assert db.query(TelemetryRecord).count() == 0


@pytest.mark.asyncio
async def test_gateway_failure_fallback_then_recovery(db, tmp_path):
    """连接失败：安全回退（无业务写入、状态 error）；恢复后继续工作。"""
    service, _ = _make_service(db, tmp_path)
    service.ensure_seed(db)

    service.client.set_available(False)
    failed = await service.sync_once(db)
    assert failed.ok is False
    assert failed.error is not None
    assert "不可达" in failed.error
    assert service.connection_status == GATEWAY_STATUS_ERROR
    assert db.query(TelemetryRecord).count() == 0
    row = db.query(GatewayConnection).one()
    assert row.status == GATEWAY_STATUS_ERROR
    assert row.last_error is not None

    # 恢复后同一运行时可继续采集。
    service.client.set_available(True)
    recovered = await service.sync_once(db)
    assert recovered.ok is True
    assert recovered.snapshots_ingested == 1
    assert service.connection_status == GATEWAY_STATUS_CONNECTED
    assert db.query(TelemetryRecord).count() == 1
