"""Demo 编排端点（仅软件模拟器；Simulation only）。

安全边界：

- 场景控制只作用于进程内 ``MotorSimulator``（Mock 网关数据源）；
- ``GATEWAY_MODE=opcua``（真实 OPC UA 连接）时**拒绝服务**；
- 不调用 ``EquipmentGateway.execute_command`` / ``write_node``，
  不触碰 OperationApproval 之外的任何设备命令链；
- ``/demo/state`` 为只读聚合。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, supervisor_or_admin
from app.db.session import get_db
from app.industrial_gateway.simulator.generator import SUPPORTED_SCENARIOS
from app.models.user import User
from app.services.demo_service import get_demo_state

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoScenarioRequest(BaseModel):
    scenario: str = Field(max_length=32)
    ticks: int = Field(default=0, ge=1, le=24)
    equipment_code: str = Field(default="Motor001", max_length=64)


def _require_mock_gateway() -> Any:
    """校验当前为 Mock 软件网关；真实 OPC UA 模式拒绝 Demo 编排。"""
    from app.industrial_gateway.opcua.service import (
        get_gateway_runtime,
        get_mock_simulator,
    )

    if not settings.GATEWAY_ENABLED:
        raise HTTPException(
            status_code=409,
            detail=(
                "Demo simulator requires GATEWAY_ENABLED=true with "
                "GATEWAY_MODE=mock (simulation only)."
            ),
        )
    runtime = get_gateway_runtime()
    current_mode = runtime.status().get("mode")
    if current_mode != "mock":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Demo simulator refused: gateway mode is '{current_mode}'. "
                "Scenario control is simulation-only and never targets real OPC UA servers."
            ),
        )
    simulator = get_mock_simulator()
    if simulator is None:
        raise HTTPException(status_code=409, detail="Mock simulator unavailable")
    return runtime


def _default_ticks(scenario: str) -> int:
    # 确定性越过平台警告阈值所需 tick 数（与 generator 劣化曲线对齐）：
    # fault 需 elapsed≥7（+预热 3），warning 需 elapsed≥13（+预热 5）。
    return {"normal": 2, "warning": 20, "fault": 14}[scenario]


@router.get("/state")
def demo_state(
    equipment_code: str = Query(default="Motor001", max_length=64),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """聚合一次演示所需的全部真实状态（只读 read model）。"""
    return get_demo_state(db, equipment_code=equipment_code)


@router.post("/simulator/scenario")
async def set_demo_scenario(
    payload: DemoScenarioRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(supervisor_or_admin),
) -> dict[str, Any]:
    """切换软件模拟器工况并同步发布/冲刷一批 DataChange。

    Simulation only：仅推进进程内确定性仿真器并复用既有订阅→质量→
    快照→AI 链路；不产生任何 PLC / 设备写操作。
    """
    if payload.scenario not in SUPPORTED_SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的仿真场景: {payload.scenario}（支持: {sorted(SUPPORTED_SCENARIOS)}）",
        )
    runtime = _require_mock_gateway()

    from app.industrial_gateway.opcua.service import get_mock_simulator

    simulator = get_mock_simulator()
    assert simulator is not None  # _require_mock_gateway 已保证
    try:
        simulator.set_scenario(payload.scenario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ticks = payload.ticks or _default_ticks(payload.scenario)
    result = await runtime.demo_publish_ticks(db, ticks=ticks)
    return {
        "scenario": payload.scenario,
        "ticks": ticks,
        "simulation_only": True,
        **result,
    }
