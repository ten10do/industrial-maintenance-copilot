"""端到端 Trace 传播测试：真实工作流产生的领域实体共享同一 trace_id。

原则：所有实体均由真实业务路径产生（Mock 订阅 → 质量闸门 → 快照 →
既有 AI 链路 → 报警状态机；HTTP 报警分析 → 人工复核 → 工单创建）。
不伪造任何数据库记录；某阶段未产生则不断言该阶段。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from app.core.security import create_access_token
from app.industrial_gateway.models import AlarmAnalysisRecord, IndustrialAlarm
from app.industrial_gateway.opcua.client import MockOpcUaClient
from app.industrial_gateway.opcua.models import NodeRead
from app.industrial_gateway.opcua.service import OpcUaGatewayService
from app.industrial_gateway.opcua.subscription import (
    MockSubscriptionClient,
    NodeDataChange,
)
from app.industrial_gateway.simulator.generator import MotorSimulator
from app.models.base import EquipmentStatusEnum, RiskLevelEnum
from app.models.equipment import Equipment
from app.models.intelligence import (
    AgentRun,
    AnomalyEvent,
    MaintenanceRecommendation,
    OperationApproval,
    RiskPrediction,
    TelemetryRecord,
    ToolInvocation,
)
from app.models.workorder import WorkOrder

# ---- 与 test_gateway_subscription 相同的确定性脚手架（本地内联） ----

_FULL_NODES = [
    ("Temperature", "temperature"),
    ("Vibration", "vibration"),
    ("Current", "current"),
    ("Speed", "speed"),
    ("Voltage", "voltage"),
    ("LoadRatio", "load"),
]
_METRIC_UNITS = {
    "temperature": "celsius",
    "vibration": "mm/s",
    "current": "A",
    "speed": "rpm",
    "voltage": "V",
    "load": "%",
}
_FIELD_BY_METRIC = {
    "temperature": "bearing_temperature",
    "vibration": "vibration_rms",
    "current": "motor_current",
    "speed": "rotational_speed",
    "voltage": "motor_voltage",
    "load": "load_ratio",
}


class _ScriptedClock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def tick(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def _make_service(db, tmp_path: Path, *, scenario: str):
    equipment = Equipment(
        code="EQ-TRACE-01",
        name="链路追踪验证电机",
        status=EquipmentStatusEnum.running,
        risk_level=RiskLevelEnum.low,
        qr_token="qr-trace-01",
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
                "unit": _METRIC_UNITS[metric],
            }
            for name, metric in _FULL_NODES
        ]
    }
    config_path = tmp_path / f"trace-mapping-{scenario}.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    simulator = MotorSimulator(seed=42, scenario=scenario)

    def initial_provider(node_id: str) -> NodeRead:
        _, metric = next(
            (name, metric)
            for name, metric in _FULL_NODES
            if node_id == f"ns=2;s=Motor001.{name}"
        )
        values = simulator.current_values()
        return NodeRead(
            node_id=node_id,
            value=values.get(_FIELD_BY_METRIC[metric]),
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
        # 后台任务绑定测试同一内存数据库。
        session_factory=lambda: __import__(
            "sqlalchemy.orm", fromlist=["Session"]
        ).Session(bind=db.get_bind(), autoflush=False),
    )
    return service, simulator, subscription_client, equipment


def _publish_all(
    subscription_client: MockSubscriptionClient,
    simulator: MotorSimulator,
    clock: _ScriptedClock,
) -> None:
    values = simulator.current_values()
    for name, _metric in _FULL_NODES:
        subscription_client.publish(
            NodeDataChange(
                node_id=f"ns=2;s=Motor001.{name}",
                value=values[name],
                source_timestamp=clock.tick(),
                status_code=0,
                quality="good",
            )
        )


async def _run_fault_flush(db, tmp_path: Path):
    """真实订阅故障链：预热 → 发布 → flush。返回 (service, equipment)。"""
    service, simulator, sub_client, equipment = _make_service(
        db, tmp_path, scenario="fault"
    )
    await service.start_subscription(db, client=sub_client)
    for _ in range(16):
        simulator.advance()
    _publish_all(sub_client, simulator, _ScriptedClock())
    flush = await service.flush_now(db)
    await service.stop_subscription(db)
    assert flush["snapshots_ingested"] == 1
    assert flush["anomalies"] == 1
    assert flush["work_orders_created"] == 1
    return service, equipment


def _trace_ids(rows) -> set:
    return {row.trace_id for row in rows}


@pytest.mark.asyncio
async def test_subscription_fault_chain_shares_single_trace(db, tmp_path):
    """DataChange → Telemetry → Anomaly → Prediction → Recommendation →
    Alarm → WorkOrder → Approval → AgentRun 全链共享同一 trace_id。"""
    _service, _equipment = await _run_fault_flush(db, tmp_path)

    telemetry = db.query(TelemetryRecord).one()
    anomaly = db.query(AnomalyEvent).one()
    prediction = db.query(RiskPrediction).one()
    recommendation = db.query(MaintenanceRecommendation).one()
    alarms = db.query(IndustrialAlarm).all()
    work_orders = db.query(WorkOrder).all()
    approvals = db.query(OperationApproval).all()
    agent_runs = db.query(AgentRun).all()

    # 关键实体必须共享同一个非空 trace_id。
    shared = {
        telemetry.trace_id,
        anomaly.trace_id,
        prediction.trace_id,
        recommendation.trace_id,
        *(_trace_ids(alarms)),
        *(_trace_ids(work_orders)),
        *(_trace_ids(approvals)),
        *(_trace_ids(agent_runs)),
    }
    assert None not in shared
    assert len(shared) == 1
    trace_id = next(iter(shared))

    # ToolInvocation 通过 agent_run 间接关联到同一条链路。
    tools = (
        db.query(ToolInvocation)
        .join(AgentRun)
        .filter(AgentRun.trace_id == trace_id)
        .all()
    )
    assert tools, "fault 链路应记录工具调用"
    tool_run_ids = {tool.agent_run_id for tool in tools}
    tool_runs = db.query(AgentRun).filter(AgentRun.id.in_(tool_run_ids)).all()
    assert all(run.trace_id == trace_id for run in tool_runs)


@pytest.mark.asyncio
async def test_alarm_analysis_review_workorder_inherit_trace(
    db, tmp_path, client, supervisor, equipment_type
):
    """IndustrialAlarm → Analysis → Review → WorkOrder 继承同一 trace_id。

    Alarm 由真实订阅故障链产生；分析/复核/工单走真实 HTTP 流程。
    """
    _service, equipment = await _run_fault_flush(db, tmp_path)

    alarm = db.query(IndustrialAlarm).one()
    assert alarm.trace_id
    trace_id = alarm.trace_id

    equipment = db.get(Equipment, alarm.equipment_id)
    equipment.equipment_type_id = equipment_type.id
    db.commit()

    headers = {"Authorization": f"Bearer {create_access_token(str(supervisor.id))}"}

    # 1. 报警分析：继承报警 trace_id。
    response = client.post(f"/api/v1/alarms/{alarm.id}/analyze", headers=headers)
    assert response.status_code == 200
    record = db.query(AlarmAnalysisRecord).one()
    assert record.trace_id == trace_id
    agent_run = db.get(AgentRun, record.agent_run_id)
    assert agent_run is not None and agent_run.trace_id == trace_id

    # 2. 人工复核批准：不改变 trace_id，不绕过 gate。
    review = client.post(
        f"/api/v1/alarms/{alarm.id}/review",
        json={"action": "approve", "note": "证据充分，批准"},
        headers=headers,
    )
    assert review.status_code == 200
    db.refresh(record)
    assert record.analysis_status == "APPROVED"
    assert record.trace_id == trace_id

    # 3. 经批准创建工单：继承同一 trace_id；审批 gate 保持生效。
    created = client.post(
        f"/api/v1/alarms/{alarm.id}/create-work-order", headers=headers
    )
    assert created.status_code == 200
    work_order = db.query(WorkOrder).order_by(WorkOrder.id.desc()).first()
    assert work_order is not None and work_order.trace_id == trace_id

    # 未批准时不可创建（gate 回归）：独立入口报警（无工业链路，trace 为空）
    # 走同样链路但不批准——Observability 不绕过任何审批。
    db.add(
        IndustrialAlarm(
            equipment_id=equipment.id,
            severity="WARNING",
            message="工业报警升级为 WARNING：轴承温度=80.0",
            source="manual-entry",
        )
    )
    db.commit()
    alarm2 = (
        db.query(IndustrialAlarm)
        .filter(
            IndustrialAlarm.severity == "WARNING",
            IndustrialAlarm.trace_id.is_(None),
        )
        .one()
    )
    analyze2 = client.post(f"/api/v1/alarms/{alarm2.id}/analyze", headers=headers)
    assert analyze2.status_code == 200
    blocked = client.post(
        f"/api/v1/alarms/{alarm2.id}/create-work-order", headers=headers
    )
    assert blocked.status_code == 409
