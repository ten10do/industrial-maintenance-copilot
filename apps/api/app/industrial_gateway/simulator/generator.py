"""确定性工业电机仿真生成器（纯函数，无网络依赖）。

设计约束：

- **可复现**：数值只由 ``(seed, scenario, tick)`` 决定，
  固定随机种子后任意两次运行结果完全一致；
- **量程符合规格**：Temperature 20-100 ℃、Vibration 0-5 mm/s、
  Current 0-20 A、Speed 0-3000 rpm；
- **三种状态**：normal / warning / fault（warning 与 fault 从预热 tick
  开始渐变劣化，fault 置位 Alarm）。

该生成器同时供两处使用：

1. ``simulator.opcua_server``：把数值发布到真实 OPC UA Server；
2. ``opcua.client.MockOpcUaClient``：进程内 Mock 模式（未安装 asyncua 时）。
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

SCENARIO_NORMAL: Final = "normal"
SCENARIO_WARNING: Final = "warning"
SCENARIO_FAULT: Final = "fault"
SUPPORTED_SCENARIOS: Final[frozenset[str]] = frozenset(
    {SCENARIO_NORMAL, SCENARIO_WARNING, SCENARIO_FAULT}
)

# 节点名与 NodeId 后缀（ns 由 OPC UA Server 注册时决定，演示环境为 ns=2）。
NODE_NAMES: Final[tuple[str, ...]] = (
    "Temperature",
    "Vibration",
    "Current",
    "Speed",
    "Voltage",
    "LoadRatio",
    "RunningState",
    "Alarm",
)

# 规格量程（含演示用电压 / 负载率扩展节点）。
METRIC_RANGES: Final[dict[str, tuple[float, float]]] = {
    "Temperature": (20.0, 100.0),
    "Vibration": (0.0, 5.0),
    "Current": (0.0, 20.0),
    "Speed": (0.0, 3000.0),
    "Voltage": (340.0, 420.0),
    "LoadRatio": (0.0, 120.0),
}

# normal 工况基线（全部位于平台健康阈值内）。
_BASELINE: Final[dict[str, float]] = {
    "Temperature": 55.0,
    "Vibration": 1.8,
    "Current": 12.0,
    "Speed": 1480.0,
    "Voltage": 380.0,
    "LoadRatio": 60.0,
}

# 各工况开始劣化的预热 tick 数。
_WARMUP_TICKS: Final[dict[str, int]] = {
    SCENARIO_NORMAL: 0,
    SCENARIO_WARNING: 5,
    SCENARIO_FAULT: 3,
}


def _clamp(name: str, value: float) -> float:
    low, high = METRIC_RANGES[name]
    return min(max(value, low), high)


@dataclass(slots=True)
class MotorSimulator:
    """Industrial Motor 确定性仿真器。"""

    seed: int = 42
    scenario: str = SCENARIO_NORMAL
    prefix: str = "Motor001"
    _tick: int = field(default=0, init=False)
    _current: dict[str, float | bool] = field(default_factory=dict, init=False)
    _current_at: datetime | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.scenario not in SUPPORTED_SCENARIOS:
            raise ValueError(
                f"不支持的仿真场景: {self.scenario}（支持: {sorted(SUPPORTED_SCENARIOS)}）"
            )
        self.advance()

    @property
    def tick(self) -> int:
        return self._tick

    def node_ids(self, namespace: int = 2) -> list[str]:
        """该设备暴露的全部字符串 NodeId（默认 ns=2）。"""
        return [f"ns={namespace};s={self.prefix}.{name}" for name in NODE_NAMES]

    def advance(self) -> dict[str, float | bool]:
        """推进一个采样周期并返回当前值快照（确定性）。"""
        rng = random.Random(f"{self.seed}:{self.scenario}:{self._tick}")
        values: dict[str, float | bool] = {
            "Temperature": _BASELINE["Temperature"] + rng.uniform(-0.8, 0.8),
            "Vibration": _BASELINE["Vibration"] + rng.uniform(-0.15, 0.15),
            "Current": _BASELINE["Current"] + rng.uniform(-0.4, 0.4),
            "Speed": _BASELINE["Speed"] + rng.uniform(-8.0, 8.0),
            "Voltage": _BASELINE["Voltage"] + rng.uniform(-2.0, 2.0),
            "LoadRatio": _BASELINE["LoadRatio"] + rng.uniform(-2.0, 2.0),
            "RunningState": True,
            "Alarm": False,
        }

        warmup = _WARMUP_TICKS[self.scenario]
        elapsed = max(self._tick - warmup, 0)
        if self.scenario == SCENARIO_WARNING and elapsed > 0:
            # 轴承温度缓慢爬升越过平台警告阈值（>75 ℃），振动中度上升。
            values["Temperature"] += min(elapsed * 1.6, 32.0)
            values["Vibration"] += min(elapsed * 0.12, 1.6)
            values["LoadRatio"] += min(elapsed * 0.4, 6.0)
        elif self.scenario == SCENARIO_FAULT and elapsed > 0:
            # 强劣化：温升 + 振动 + 过流，置位报警。
            values["Temperature"] += min(elapsed * 3.2, 44.0)
            values["Vibration"] += min(elapsed * 0.55, 3.1)
            values["Current"] += min(elapsed * 0.9, 7.5)
            values["Speed"] -= min(elapsed * 12.0, 120.0)
            values["Alarm"] = True

        for name in METRIC_RANGES:
            values[name] = round(_clamp(name, float(values[name])), 2)

        self._tick += 1
        self._current = values
        self._current_at = datetime.now(UTC)
        return dict(values)

    def current_values(self) -> dict[str, float | bool]:
        """最近一次 advance() 的值快照。"""
        return dict(self._current)

    def value_provider(
        self,
    ) -> Callable[[str], tuple[float | bool | None, datetime | None]]:
        """返回适配 ``MockOpcUaClient`` 的按节点取值函数。

        返回值始终来自同一 tick 快照，保证一次网关同步内各节点一致。
        """

        def provider(node_id: str) -> tuple[float | bool | None, datetime | None]:
            prefix, _, name = node_id.rpartition(".")
            if prefix != f"ns=2;s={self.prefix}" or name not in NODE_NAMES:
                return None, self._current_at
            return self._current.get(name), self._current_at

        return provider
