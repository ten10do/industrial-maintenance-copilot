"""设备接入网关及可重复的软件电机模拟器。"""

from __future__ import annotations

import asyncio
import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar, Protocol
from uuid import UUID


@dataclass(slots=True)
class TelemetrySnapshot:
    equipment_id: UUID
    collected_at: datetime
    vibration_rms: float | None
    bearing_temperature: float | None
    motor_current: float | None
    motor_voltage: float | None
    rotational_speed: float | None
    load_ratio: float | None
    ambient_temperature: float | None
    cumulative_runtime_hours: float
    scenario: str = "normal"
    quality: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["equipment_id"] = str(self.equipment_id)
        result["collected_at"] = self.collected_at.isoformat()
        return result


@dataclass(slots=True)
class EquipmentCommand:
    equipment_id: UUID
    command_type: str
    parameters: dict[str, Any]
    idempotency_key: str


@dataclass(slots=True)
class EquipmentCommandResult:
    equipment_id: UUID
    command_type: str
    success: bool
    message: str
    executed_at: datetime
    data: dict[str, Any] | None = None
    idempotency_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["equipment_id"] = str(self.equipment_id)
        result["executed_at"] = self.executed_at.isoformat()
        return result


class EquipmentGateway(Protocol):
    """设备适配器必须持久化幂等键，并为重复键返回首次执行结果。"""

    async def read_telemetry(
        self,
        equipment_id: UUID,
    ) -> TelemetrySnapshot: ...

    async def execute_command(
        self,
        command: EquipmentCommand,
    ) -> EquipmentCommandResult: ...


@dataclass
class _SimulationState:
    equipment_id: UUID
    seed: int
    scenario: str
    tick: int = 0
    runtime_hours: float = 12480.0
    running: bool = True

    def rng(self) -> random.Random:
        stable_equipment_seed = self.equipment_id.int & 0xFFFFFFFF
        return random.Random(self.seed + stable_equipment_seed + self.tick * 7919)


class MockEquipmentGateway:
    """首期设备 Provider：不连接 PLC，仅生成电机及轴承时序数据。"""

    SUPPORTED_SCENARIOS: ClassVar[set[str]] = {
        "normal",
        "temperature_rise",
        "vibration_spike",
        "current_overload",
        "bearing_wear",
        "voltage_fluctuation",
        "sensor_disconnect",
        "composite_anomaly",
    }

    def __init__(self) -> None:
        self._states: dict[UUID, _SimulationState] = {}
        self._command_results: dict[str, EquipmentCommandResult] = {}
        self._command_fingerprints: dict[str, str] = {}
        self._command_locks: dict[str, asyncio.Lock] = {}

    def configure(
        self, equipment_ids: list[UUID], scenario: str = "normal", seed: int = 20260731
    ) -> None:
        if scenario not in self.SUPPORTED_SCENARIOS:
            raise ValueError(f"不支持的仿真场景: {scenario}")
        self._states = {
            equipment_id: _SimulationState(
                equipment_id=equipment_id, seed=seed, scenario=scenario
            )
            for equipment_id in equipment_ids
        }

    def reset(self) -> None:
        for state in self._states.values():
            state.tick = 0
            state.runtime_hours = 12480.0
            state.running = True

    async def read_telemetry(self, equipment_id: UUID) -> TelemetrySnapshot:
        state = self._states.get(equipment_id)
        if not state:
            state = _SimulationState(
                equipment_id=equipment_id, seed=20260731, scenario="normal"
            )
            self._states[equipment_id] = state

        rng = state.rng()
        tick = state.tick
        state.tick += 1
        if state.running:
            state.runtime_hours += 1 / 60

        vibration = 1.8 + rng.uniform(-0.16, 0.16)
        temperature = 56.0 + rng.uniform(-0.8, 0.8)
        current = 18.0 + rng.uniform(-0.5, 0.5)
        voltage = 380.0 + rng.uniform(-2.5, 2.5)
        speed = 1480.0 + rng.uniform(-8.0, 8.0)
        load = 62.0 + rng.uniform(-2.5, 2.5)
        ambient = 26.0 + rng.uniform(-0.6, 0.6)
        quality = 1.0

        if not state.running:
            vibration, current, speed, load = 0.0, 0.0, 0.0, 0.0
            temperature = max(ambient, temperature - min(tick, 20) * 0.8)

        scenario = state.scenario
        if scenario == "temperature_rise":
            temperature += min(tick * 1.4, 32)
        elif scenario == "vibration_spike":
            vibration += 0 if tick < 2 else 6.2 + rng.uniform(-0.3, 0.3)
        elif scenario == "current_overload":
            current += 12.0 + min(tick * 0.25, 5)
            load += 44.0
            temperature += min(tick * 0.5, 12)
        elif scenario == "bearing_wear":
            vibration += min(tick * 0.45, 7.0)
            temperature += min(tick * 0.55, 19)
        elif scenario == "voltage_fluctuation":
            voltage += math.sin(tick * 1.7) * 42
        elif scenario == "sensor_disconnect" and tick >= 2:
            return TelemetrySnapshot(
                equipment_id=equipment_id,
                collected_at=datetime.now(UTC),
                vibration_rms=None,
                bearing_temperature=None,
                motor_current=None,
                motor_voltage=None,
                rotational_speed=None,
                load_ratio=None,
                ambient_temperature=None,
                cumulative_runtime_hours=round(state.runtime_hours, 2),
                scenario=scenario,
                quality=0.0,
            )
        elif scenario == "composite_anomaly":
            vibration += min(tick * 0.6, 8)
            temperature += min(tick * 0.9, 25)
            current += 10
            load += 38
            voltage += math.sin(tick * 1.5) * 32

        return TelemetrySnapshot(
            equipment_id=equipment_id,
            collected_at=datetime.now(UTC),
            vibration_rms=_rounded(vibration),
            bearing_temperature=_rounded(temperature),
            motor_current=_rounded(current),
            motor_voltage=_rounded(voltage),
            rotational_speed=_rounded(speed),
            load_ratio=_rounded(load),
            ambient_temperature=_rounded(ambient),
            cumulative_runtime_hours=round(state.runtime_hours, 2),
            scenario=scenario,
            quality=quality,
        )

    async def execute_command(
        self, command: EquipmentCommand
    ) -> EquipmentCommandResult:
        fingerprint = json.dumps(
            {
                "equipment_id": str(command.equipment_id),
                "command_type": command.command_type,
                "parameters": command.parameters,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        lock = self._command_locks.setdefault(command.idempotency_key, asyncio.Lock())
        async with lock:
            previous_fingerprint = self._command_fingerprints.get(
                command.idempotency_key
            )
            if previous_fingerprint and previous_fingerprint != fingerprint:
                raise ValueError("同一幂等键不能用于不同的设备命令")
            if cached := self._command_results.get(command.idempotency_key):
                return cached

            result = self._execute_command(command)
            self._command_fingerprints[command.idempotency_key] = fingerprint
            self._command_results[command.idempotency_key] = result
            return result

    def _execute_command(self, command: EquipmentCommand) -> EquipmentCommandResult:
        state = self._states.get(command.equipment_id)
        if not state:
            return EquipmentCommandResult(
                equipment_id=command.equipment_id,
                command_type=command.command_type,
                success=False,
                message="设备未接入模拟网关",
                executed_at=datetime.now(UTC),
                idempotency_key=command.idempotency_key,
            )

        if command.command_type in {"shutdown", "emergency_stop"}:
            state.running = False
        elif command.command_type in {"restart", "start"}:
            state.running = True
        elif command.command_type == "reset_alarm":
            state.scenario = "normal"
            state.tick = 0
        else:
            return EquipmentCommandResult(
                equipment_id=command.equipment_id,
                command_type=command.command_type,
                success=False,
                message="模拟网关不支持该命令",
                executed_at=datetime.now(UTC),
                idempotency_key=command.idempotency_key,
            )

        return EquipmentCommandResult(
            equipment_id=command.equipment_id,
            command_type=command.command_type,
            success=True,
            message="命令已由 Mock Equipment Gateway 执行",
            executed_at=datetime.now(UTC),
            data={"running": state.running, "scenario": state.scenario},
            idempotency_key=command.idempotency_key,
        )


def _rounded(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


equipment_gateway: EquipmentGateway = MockEquipmentGateway()
