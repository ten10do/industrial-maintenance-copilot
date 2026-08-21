"""工业协议网关单元测试（客户端 Mock、映射、数据质量、只读安全）。

集成链路（OPC UA → Telemetry → AI）见 test_gateway_pipeline.py。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from app.industrial_gateway.gateway import GatewayConfig, build_client
from app.industrial_gateway.mapping import (
    NodeMapping,
    load_mappings,
    seed_mappings_from_config,
)
from app.industrial_gateway.models import OpcUaNodeMapping
from app.industrial_gateway.opcua.client import AsyncuaOpcUaClient, MockOpcUaClient
from app.industrial_gateway.opcua.models import (
    QUALITY_BAD,
    QUALITY_GOOD,
    QUALITY_UNCERTAIN,
    NodeRead,
    quality_from_status_code,
)
from app.industrial_gateway.quality import (
    DataQualityLayer,
    UnitConversionError,
    convert_value,
)
from app.models.base import EquipmentStatusEnum, RiskLevelEnum
from app.models.equipment import Equipment


def _make_equipment(db, code: str = "EQ-MTR01") -> Equipment:
    equipment = Equipment(
        code=code,
        name="演示电机",
        status=EquipmentStatusEnum.running,
        risk_level=RiskLevelEnum.low,
        qr_token=f"qr-{code.lower()}",
    )
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment


def _write_mapping_config(path: Path, equipment_code: str) -> Path:
    config = {
        "mappings": [
            {
                "node_id": "ns=2;s=Motor001.Temperature",
                "equipment_code": equipment_code,
                "metric": "temperature",
                "unit": "celsius",
            },
            {
                "node_id": "ns=2;s=Motor001.Vibration",
                "equipment_code": equipment_code,
                "metric": "vibration",
                "unit": "mm/s",
            },
            {
                "node_id": "ns=2;s=Motor001.RunningState",
                "equipment_code": equipment_code,
                "metric": "running",
                "unit": "",
                "informational": True,
            },
            {
                "node_id": "ns=2;s=Ghost001.Temperature",
                "equipment_code": "EQ-NOT-EXIST",
                "metric": "temperature",
                "unit": "celsius",
            },
        ]
    }
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. OPC UA 连接（Mock）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_opcua_client_connect_and_read():
    now = datetime.now(UTC)
    client = MockOpcUaClient(value_provider=lambda node_id: (72.5, now))
    await client.connect()
    assert client.connected is True

    read = await client.read_node("ns=2;s=Motor001.Temperature")
    assert read.value == 72.5
    assert read.quality == QUALITY_GOOD
    assert read.source_timestamp == now

    await client.disconnect()
    assert client.connected is False


@pytest.mark.asyncio
async def test_mock_opcua_client_connection_failure_is_explicit():
    client = MockOpcUaClient()
    client.set_available(False)
    with pytest.raises(ConnectionError, match="不可达"):
        await client.connect()
    with pytest.raises(ConnectionError, match="未连接"):
        await client.read_node("ns=2;s=Motor001.Temperature")


@pytest.mark.asyncio
async def test_asyncua_client_is_lazy_and_read_only():
    client = AsyncuaOpcUaClient("opc.tcp://127.0.0.1:4840/industrial-simulator/")
    # 未连接时读取直接失败，不触发 asyncua 导入。
    with pytest.raises(ConnectionError):
        await client.read_node("ns=2;s=Motor001.Temperature")
    # read-only mode：写操作被代码级拒绝。
    with pytest.raises(PermissionError, match="read-only"):
        await client.write_node("ns=2;s=Motor001.Temperature", 999)


@pytest.mark.asyncio
async def test_mock_client_rejects_write_operations():
    client = MockOpcUaClient(value_provider=lambda node_id: (1.0, None))
    await client.connect()
    with pytest.raises(PermissionError, match="read-only"):
        await client.write_node("ns=2;s=Motor001.RunningState", False)


def test_quality_from_status_code_classification():
    assert quality_from_status_code(None) == QUALITY_GOOD
    assert quality_from_status_code(0x0000_0000) == QUALITY_GOOD
    assert quality_from_status_code(0x4000_0000) == QUALITY_UNCERTAIN
    assert quality_from_status_code(0x8000_0000) == QUALITY_BAD
    assert quality_from_status_code(0x80AA_0000) == QUALITY_BAD


# ---------------------------------------------------------------------------
# 2. 节点映射
# ---------------------------------------------------------------------------


def test_seed_and_load_node_mappings(db, tmp_path):
    equipment = _make_equipment(db)
    config_path = _write_mapping_config(tmp_path / "mapping.yaml", equipment.code)

    result = seed_mappings_from_config(db, config_path)
    assert result.created == 3
    assert result.updated == 0
    assert len(result.skipped) == 1
    assert "EQ-NOT-EXIST" in result.skipped[0]

    mappings = {item.node_id: item for item in load_mappings(db)}
    temperature = mappings["ns=2;s=Motor001.Temperature"]
    assert temperature.equipment_id == equipment.id
    assert temperature.metric_name == "temperature"
    assert temperature.snapshot_field == "bearing_temperature"
    assert temperature.informational is False

    running = mappings["ns=2;s=Motor001.RunningState"]
    assert running.informational is True
    assert running.snapshot_field is None

    # 幂等：重复加载只更新，不重复创建。
    again = seed_mappings_from_config(db, config_path)
    assert again.created == 0
    assert again.updated == 3
    assert db.query(OpcUaNodeMapping).count() == 3


def test_node_mapping_scaling_and_disabled_rows(db, tmp_path):
    equipment = _make_equipment(db)
    config = {
        "mappings": [
            {
                "node_id": "ns=2;s=Motor001.Temperature",
                "equipment_code": equipment.code,
                "metric": "temperature",
                "unit": "celsius",
                "scale": 0.1,
                "offset": -5.0,
                "enabled": False,
            }
        ]
    }
    config_path = tmp_path / "mapping.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    seed_mappings_from_config(db, config_path)

    # enabled=false 的映射不参与运行时读取。
    assert load_mappings(db) == []

    mapping = NodeMapping(
        node_id="ns=2;s=Motor001.Temperature",
        equipment_id=equipment.id,
        equipment_code=equipment.code,
        metric_name="temperature",
        unit="celsius",
        scale=0.1,
        offset=-5.0,
    )
    assert mapping.apply_scaling(100.0) == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# 3. 数据质量层
# ---------------------------------------------------------------------------


def _read(
    node_id: str,
    value,
    *,
    ts: datetime | None,
    quality: str = QUALITY_GOOD,
    status: int | None = 0,
) -> NodeRead:
    return NodeRead(
        node_id=node_id,
        value=value,
        source_timestamp=ts,
        status_code=status,
        quality=quality,
    )


def test_quality_layer_accepts_good_reads():
    now = datetime.now(UTC)
    layer = DataQualityLayer()
    report = layer.process(
        [
            _read("ns=2;s=Motor001.Temperature", 71.2, ts=now - timedelta(seconds=1)),
            _read("ns=2;s=Motor001.Vibration", 1.9, ts=now - timedelta(seconds=1)),
        ],
        received_at=now,
    )
    assert len(report.accepted) == 2
    assert report.rejected == []
    assert report.corrections == []


def test_quality_layer_rejects_bad_missing_and_non_numeric():
    now = datetime.now(UTC)
    layer = DataQualityLayer()
    report = layer.process(
        [
            _read(
                "ns=2;s=Motor001.Temperature",
                71.2,
                ts=now,
                quality=QUALITY_BAD,
                status=0x80AA_0000,
            ),
            _read("ns=2;s=Motor001.Vibration", None, ts=now),
            _read("ns=2;s=Motor001.Current", float("nan"), ts=now),
            _read("ns=2;s=Motor001.Speed", "n/a", ts=now),
        ],
        received_at=now,
    )
    assert report.accepted == []
    reasons = {item.node_id: item.reason for item in report.rejected}
    assert reasons["ns=2;s=Motor001.Temperature"] == "bad_quality"
    assert reasons["ns=2;s=Motor001.Vibration"] == "missing_value"
    assert reasons["ns=2;s=Motor001.Current"] == "non_numeric"
    assert reasons["ns=2;s=Motor001.Speed"] == "non_numeric"


def test_quality_layer_handles_invalid_timestamps():
    now = datetime.now(UTC)
    layer = DataQualityLayer()
    report = layer.process(
        [
            # 未来时间戳 → 拒绝
            _read(
                "ns=2;s=Motor001.Temperature",
                70.0,
                ts=now + timedelta(minutes=10),
            ),
            # 过期时间戳 → 拒绝
            _read(
                "ns=2;s=Motor001.Vibration",
                2.0,
                ts=now - timedelta(minutes=30),
            ),
            # 缺失时间戳 → 用接收时间替代并记录修正
            _read("ns=2;s=Motor001.Current", 12.1, ts=None),
        ],
        received_at=now,
    )
    assert [item.reason for item in report.rejected] == [
        "future_timestamp",
        "stale_timestamp",
    ]
    assert len(report.accepted) == 1
    assert report.accepted[0].source_timestamp == now
    assert report.corrections and "Motor001.Current" in report.corrections[0]


def test_quality_layer_rejects_duplicate_timestamps():
    now = datetime.now(UTC)
    layer = DataQualityLayer()
    first = layer.process(
        [_read("ns=2;s=Motor001.Temperature", 70.0, ts=now)], received_at=now
    )
    assert len(first.accepted) == 1

    duplicate = layer.process(
        [_read("ns=2;s=Motor001.Temperature", 70.0, ts=now)],
        received_at=now + timedelta(seconds=5),
    )
    assert duplicate.accepted == []
    assert duplicate.rejected[0].reason == "duplicate_timestamp"

    # 时间戳前进后恢复接受。
    advanced = layer.process(
        [_read("ns=2;s=Motor001.Temperature", 71.0, ts=now + timedelta(seconds=1))],
        received_at=now + timedelta(seconds=6),
    )
    assert len(advanced.accepted) == 1


# ---------------------------------------------------------------------------
# 4. 单位换算
# ---------------------------------------------------------------------------


def test_convert_value_temperature_units():
    assert convert_value("temperature", "celsius", 75.0) == pytest.approx(75.0)
    assert convert_value("temperature", "°C", 75.0) == pytest.approx(75.0)
    assert convert_value("temperature", "fahrenheit", 167.0) == pytest.approx(75.0)
    assert convert_value("temperature", "kelvin", 348.15) == pytest.approx(75.0)


def test_convert_value_rejects_unknown_or_mismatched_units():
    with pytest.raises(UnitConversionError):
        convert_value("temperature", "furlong", 1.0)
    with pytest.raises(UnitConversionError):
        convert_value("vibration", "celsius", 2.0)
    with pytest.raises(UnitConversionError):
        convert_value("unknown_metric", "celsius", 2.0)
    assert convert_value("vibration", "mm/s", 2.0) == 2.0
    assert convert_value("speed", "RPM", 1480.0) == 1480.0


# ---------------------------------------------------------------------------
# 5. 网关配置与客户端工厂
# ---------------------------------------------------------------------------


def test_gateway_config_defaults_and_factory():
    from app.core.config import Settings

    settings = Settings(GATEWAY_ENABLED=False)
    config = GatewayConfig.from_settings(settings)
    assert config.enabled is False
    assert config.mode == "mock"
    assert config.endpoint == "mock://opcua-simulator"
    assert config.read_only is True

    client = build_client(config)
    assert isinstance(client, MockOpcUaClient)

    opcua_config = GatewayConfig.from_settings(
        Settings(GATEWAY_MODE="opcua", GATEWAY_ENABLED=True)
    )
    assert opcua_config.endpoint == ("opc.tcp://127.0.0.1:4840/industrial-simulator/")
    assert isinstance(build_client(opcua_config), AsyncuaOpcUaClient)

    with pytest.raises(ValueError, match="GATEWAY_MODE"):
        GatewayConfig.from_settings(Settings(GATEWAY_MODE="modbus"))
