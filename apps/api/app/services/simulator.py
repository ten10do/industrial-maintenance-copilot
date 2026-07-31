"""可启动、暂停、重置并手动推进的设备仿真控制器。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.gateways.equipment import MockEquipmentGateway, equipment_gateway
from app.models.equipment import Equipment
from app.services.intelligence_service import ingest_snapshot


@dataclass
class SimulatorController:
    interval_seconds: float = 5.0
    scenario: str = "normal"
    seed: int = 20260731
    equipment_ids: list[int] = field(default_factory=list)
    generated_points: int = 0
    auto_create_work_orders: bool = True
    running: bool = False
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)

    @property
    def gateway(self) -> MockEquipmentGateway:
        return cast(MockEquipmentGateway, equipment_gateway)

    def configure(
        self,
        db: Session,
        *,
        equipment_ids: list[int],
        interval_seconds: float,
        scenario: str,
        seed: int,
        auto_create_work_orders: bool,
    ) -> None:
        equipment = db.query(Equipment).filter(Equipment.id.in_(equipment_ids)).all()
        found = {item.id for item in equipment}
        missing = sorted(set(equipment_ids) - found)
        if missing:
            raise ValueError(f"设备不存在: {missing}")
        self.equipment_ids = list(dict.fromkeys(equipment_ids))
        self.interval_seconds = interval_seconds
        self.scenario = scenario
        self.seed = seed
        self.auto_create_work_orders = auto_create_work_orders
        self.generated_points = 0
        self.gateway.configure(
            [UUID(item.asset_uuid) for item in equipment],
            scenario=scenario,
            seed=seed,
        )

    def start(self) -> None:
        if not self.equipment_ids:
            raise ValueError("请先配置仿真设备")
        self.running = True
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._run_loop())

    def pause(self) -> None:
        self.running = False

    def reset(self) -> None:
        self.running = False
        self.generated_points = 0
        self.gateway.reset()

    async def tick(self, db: Session) -> dict[str, Any]:
        generated = 0
        anomalies = 0
        work_orders_created = 0
        processed_ids: list[int] = []
        for equipment_id in self.equipment_ids:
            equipment = db.get(Equipment, equipment_id)
            if not equipment:
                continue
            snapshot = await self.gateway.read_telemetry(UUID(equipment.asset_uuid))
            result = ingest_snapshot(
                db,
                equipment,
                snapshot,
                auto_create_work_orders=self.auto_create_work_orders,
            )
            generated += 1
            anomalies += int(result.anomaly is not None)
            work_orders_created += int(result.work_order is not None)
            processed_ids.append(equipment_id)
        self.generated_points += generated
        return {
            "generated": generated,
            "anomalies": anomalies,
            "work_orders_created": work_orders_created,
            "equipment_ids": processed_ids,
        }

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "interval_seconds": self.interval_seconds,
            "scenario": self.scenario,
            "seed": self.seed,
            "equipment_ids": self.equipment_ids,
            "generated_points": self.generated_points,
            "auto_create_work_orders": self.auto_create_work_orders,
        }

    async def _run_loop(self) -> None:
        while self.running:
            db = SessionLocal()
            try:
                await self.tick(db)
            except Exception:
                db.rollback()
            finally:
                db.close()
            await asyncio.sleep(self.interval_seconds)


simulator_controller = SimulatorController()
