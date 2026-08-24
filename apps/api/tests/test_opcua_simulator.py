"""OPC UA 设备模拟器测试：确定性、量程与场景行为。"""

from __future__ import annotations

import pytest

from app.industrial_gateway.simulator.generator import (
    METRIC_RANGES,
    SUPPORTED_SCENARIOS,
    MotorSimulator,
)
from app.industrial_gateway.simulator.opcua_server import (
    OpcUaSimulatorServer,
    parse_args,
)


def test_generator_is_reproducible_with_fixed_seed():
    a = MotorSimulator(seed=42, scenario="normal")
    b = MotorSimulator(seed=42, scenario="normal")
    for _ in range(20):
        assert a.advance() == b.advance()


def test_generator_differs_across_seeds():
    a = MotorSimulator(seed=1, scenario="normal")
    b = MotorSimulator(seed=999, scenario="normal")
    series_a = [a.advance()["Temperature"] for _ in range(10)]
    series_b = [b.advance()["Temperature"] for _ in range(10)]
    assert series_a != series_b


def test_normal_scenario_stays_within_spec_ranges_and_healthy():
    sim = MotorSimulator(seed=7, scenario="normal")
    for _ in range(50):
        values = sim.advance()
        assert values["RunningState"] is True
        assert values["Alarm"] is False
        for name, value in values.items():
            if name in METRIC_RANGES:
                low, high = METRIC_RANGES[name]
                assert low <= value <= high, f"{name}={value} 超出规格量程"
        # normal 工况不触发平台警告阈值（温度 75 / 振动 4.5）。
        assert values["Temperature"] < 75.0
        assert values["Vibration"] < 4.5


def test_warning_scenario_ramps_temperature_without_alarm():
    sim = MotorSimulator(seed=7, scenario="warning")
    crossed = False
    for _ in range(30):
        values = sim.advance()
        assert values["Alarm"] is False
        if values["Temperature"] > 75.0:
            crossed = True
    assert crossed, "warning 场景应使温度越过平台警告阈值"


def test_fault_scenario_raises_alarm_and_degrades():
    sim = MotorSimulator(seed=7, scenario="fault")
    alarms = 0
    max_temperature = 0.0
    for _ in range(25):
        values = sim.advance()
        alarms += int(values["Alarm"] is True)
        max_temperature = max(max_temperature, float(values["Temperature"]))
    assert alarms > 0, "fault 场景应置位 Alarm"
    assert max_temperature > 75.0
    # 即便强劣化也不得突破规格量程。
    low, high = METRIC_RANGES["Temperature"]
    assert low <= max_temperature <= high


def test_invalid_scenario_is_rejected():
    with pytest.raises(ValueError, match="不支持的仿真场景"):
        MotorSimulator(seed=1, scenario="overclock")


def test_node_ids_match_mapping_config_layout():
    sim = MotorSimulator(seed=1, scenario="normal")
    node_ids = sim.node_ids()
    assert "ns=2;s=Motor001.Temperature" in node_ids
    assert "ns=2;s=Motor001.Alarm" in node_ids
    assert len(node_ids) == 8


def test_value_provider_returns_same_tick_snapshot():
    sim = MotorSimulator(seed=3, scenario="normal")
    sim.advance()
    provider = sim.value_provider()
    temperature = provider("ns=2;s=Motor001.Temperature")
    vibration = provider("ns=2;s=Motor001.Vibration")
    unknown = provider("ns=3;s=Other.Temperature")

    snapshot = sim.current_values()
    assert temperature[0] == snapshot["Temperature"]
    assert vibration[0] == snapshot["Vibration"]
    assert temperature[1] == vibration[1]  # 同一 tick 时间戳一致
    assert unknown[0] is None


def test_server_cli_defaults_and_validation():
    args = parse_args([])
    assert args.host == "0.0.0.0"
    assert args.port == 4840
    assert args.seed == 42
    assert args.scenario == "normal"

    server = OpcUaSimulatorServer(port=4899, seed=11, scenario="fault")
    assert server.endpoint == "opc.tcp://0.0.0.0:4899/industrial-simulator/"
    assert server.simulator.scenario in SUPPORTED_SCENARIOS

    with pytest.raises(ValueError, match="不支持的仿真场景"):
        OpcUaSimulatorServer(scenario="storm")


@pytest.mark.asyncio
async def test_simulator_server_publishes_ticks_without_network():
    """不绑定端口，仅验证发布循环的变量写入逻辑。"""

    class RecordingVariables:
        def __init__(self) -> None:
            self.written: list[float | bool] = []

        async def write_value(self, value: float | bool) -> None:
            self.written.append(value)

    server = OpcUaSimulatorServer(seed=5, scenario="warning")
    server._variables = {name: RecordingVariables() for name in METRIC_RANGES}
    server._variables["RunningState"] = RecordingVariables()
    server._variables["Alarm"] = RecordingVariables()

    values = await server.publish_tick()

    for name, variable in server._variables.items():
        assert variable.written[-1] == values[name]
