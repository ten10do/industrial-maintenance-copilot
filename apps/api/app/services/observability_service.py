"""Observability 服务：从真实领域对象重建工业事件链时间线。

原则：

- **不生成任何虚假 trace event**：timeline 完全由带 trace_id 的
  真实 Domain Object 聚合而成；某阶段没有实体就不出现在结果中；
- 排序确定性：(timestamp, stage_order, entity_id)——避免
  PostgreSQL 同 timestamp 下顺序不稳定；
- ToolInvocation 通过 ``agent_run_id → AgentRun.trace_id`` 关联，
  不复制 trace 字段。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.industrial_gateway.models import AlarmAnalysisRecord, IndustrialAlarm
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

# 阶段展示顺序（与工业语义一致，仅用于排序）。
STAGE_ORDER: dict[str, int] = {
    "telemetry": 10,
    "anomaly": 20,
    "prediction": 30,
    "recommendation": 40,
    "alarm": 50,
    "analysis": 60,
    "rag": 65,
    "tool": 70,
    "agent": 75,
    "work_order": 80,
    "approval": 90,
}

MAX_LIMIT = 200


def _ts(value: datetime | None) -> datetime:
    """非空时间戳兜底（排序键必须可比较）。"""
    return value or datetime(1970, 1, 1)


def _entry(
    *,
    stage: str,
    entity_type: str,
    entity_id: int,
    timestamp: datetime | None,
    equipment_id: int | None,
    status: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "stage": stage,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "timestamp": timestamp.isoformat() if timestamp else None,
        "equipment_id": equipment_id,
        "status": status,
    }
    if extra:
        entry.update(extra)
    return entry


def build_timeline(db: Session, trace_id: str) -> list[dict[str, Any]]:
    """按 trace_id 从真实领域对象重建时间线。"""
    entries: list[dict[str, Any]] = []

    for record in (
        db.query(TelemetryRecord).filter(TelemetryRecord.trace_id == trace_id).all()
    ):
        entries.append(
            _entry(
                stage="telemetry",
                entity_type="telemetry",
                entity_id=record.id,
                timestamp=record.collected_at,
                equipment_id=record.equipment_id,
                status="accepted",
                extra={
                    "quality": record.quality,
                    "scenario": record.scenario,
                    "is_anomaly": record.is_anomaly,
                },
            )
        )

    for anomaly in (
        db.query(AnomalyEvent).filter(AnomalyEvent.trace_id == trace_id).all()
    ):
        entries.append(
            _entry(
                stage="anomaly",
                entity_type="anomaly_event",
                entity_id=anomaly.id,
                timestamp=anomaly.detected_at,
                equipment_id=anomaly.equipment_id,
                status=anomaly.status,
                extra={
                    "fault_type": anomaly.fault_type,
                    "severity": anomaly.severity.value if anomaly.severity else None,
                    "confidence": anomaly.confidence,
                },
            )
        )

    for prediction in (
        db.query(RiskPrediction).filter(RiskPrediction.trace_id == trace_id).all()
    ):
        entries.append(
            _entry(
                stage="prediction",
                entity_type="risk_prediction",
                entity_id=prediction.id,
                timestamp=prediction.created_at,
                equipment_id=prediction.equipment_id,
                status="completed",
                extra={
                    "model_name": "risk-prediction",
                    "model_version": prediction.model_version,
                    "failure_mode": prediction.failure_mode,
                    "probability": prediction.probability,
                    "remaining_useful_life_hours": prediction.remaining_useful_life_hours,
                    "is_mock": prediction.is_mock,
                },
            )
        )

    for recommendation in (
        db.query(MaintenanceRecommendation)
        .filter(MaintenanceRecommendation.trace_id == trace_id)
        .all()
    ):
        entries.append(
            _entry(
                stage="recommendation",
                entity_type="maintenance_recommendation",
                entity_id=recommendation.id,
                timestamp=recommendation.generated_at,
                equipment_id=recommendation.equipment_id,
                status=recommendation.status,
                extra={
                    "title": recommendation.title,
                    "priority": recommendation.priority,
                    "auto_work_order_id": recommendation.auto_work_order_id,
                },
            )
        )

    for alarm in (
        db.query(IndustrialAlarm).filter(IndustrialAlarm.trace_id == trace_id).all()
    ):
        entries.append(
            _entry(
                stage="alarm",
                entity_type="industrial_alarm",
                entity_id=alarm.id,
                timestamp=alarm.created_at,
                equipment_id=alarm.equipment_id,
                status="cleared" if alarm.cleared_at else "active",
                extra={
                    "severity": alarm.severity,
                    "message": alarm.message[:160],
                    "acknowledged": alarm.acknowledged,
                    "source": alarm.source,
                },
            )
        )

    analyses = (
        db.query(AlarmAnalysisRecord)
        .filter(AlarmAnalysisRecord.trace_id == trace_id)
        .all()
    )
    analysis_agent_ids: set[int] = set()
    for record in analyses:
        if record.agent_run_id:
            analysis_agent_ids.add(record.agent_run_id)
        entries.append(
            _entry(
                stage="analysis",
                entity_type="alarm_analysis_record",
                entity_id=record.id,
                timestamp=record.created_at,
                equipment_id=None,
                status=record.analysis_status,
                extra={
                    "alarm_id": record.alarm_id,
                    "correlation_group_id": record.correlation_group_id,
                    "root_cause_hypothesis": (record.root_cause_hypothesis or "")[:200],
                    "confidence": record.confidence,
                    "risk_level": record.risk_level,
                    "citations_count": len(record.citations or []),
                    "review_status": record.review_status,
                    "model_version": record.model_version,
                },
            )
        )
        # RAG 证据作为独立只读条目（引用真实 citation 数据）。
        for citation in (record.citations or [])[:10]:
            entries.append(
                _entry(
                    stage="rag",
                    entity_type="rag_citation",
                    entity_id=record.id,
                    timestamp=record.created_at,
                    equipment_id=None,
                    status="retrieved",
                    extra={
                        "article_id": citation.get("article_id"),
                        "document_id": citation.get("document_id"),
                        "source": citation.get("source"),
                        "section": citation.get("section"),
                        "snippet": (citation.get("snippet") or "")[:160],
                        "score": citation.get("score"),
                        "analysis_id": record.id,
                    },
                )
            )

    agent_runs = db.query(AgentRun).filter(AgentRun.trace_id == trace_id).all()
    run_ids = [run.id for run in agent_runs]
    tools_by_run: dict[int, list[ToolInvocation]] = {}
    if run_ids:
        invocations = (
            db.query(ToolInvocation)
            .filter(ToolInvocation.agent_run_id.in_(run_ids))
            .order_by(ToolInvocation.id)
            .all()
        )
        for invocation in invocations:
            tools_by_run.setdefault(invocation.agent_run_id, []).append(invocation)

    for run in agent_runs:
        latency_ms = None
        if run.finished_at and run.started_at:
            latency_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
        entries.append(
            _entry(
                stage="agent",
                entity_type="agent_run",
                entity_id=run.id,
                timestamp=run.started_at,
                equipment_id=run.equipment_id,
                status=run.status,
                extra={
                    "goal": run.goal,
                    "provider": run.provider,
                    "confidence": run.confidence,
                    "latency_ms": latency_ms,
                    "requires_human_review": run.requires_human_review,
                    "linked_analysis": run.id in analysis_agent_ids,
                },
            )
        )
        for invocation in tools_by_run.get(run.id, []):
            entries.append(
                _entry(
                    stage="tool",
                    entity_type="tool_invocation",
                    entity_id=invocation.id,
                    timestamp=invocation.created_at,
                    equipment_id=None,
                    status=invocation.status,
                    extra={
                        "tool_name": invocation.tool_name,
                        "duration_ms": invocation.duration_ms,
                        "agent_run_id": invocation.agent_run_id,
                    },
                )
            )

    for order in db.query(WorkOrder).filter(WorkOrder.trace_id == trace_id).all():
        entries.append(
            _entry(
                stage="work_order",
                entity_type="work_order",
                entity_id=order.id,
                timestamp=order.created_at,
                equipment_id=order.equipment_id,
                status=order.status.value if order.status else None,
                extra={
                    "code": order.code,
                    "title": order.title,
                    "priority": order.priority.value if order.priority else None,
                    "assignee_id": order.assignee_id,
                },
            )
        )

    for approval in (
        db.query(OperationApproval).filter(OperationApproval.trace_id == trace_id).all()
    ):
        reviewed_at = approval.reviewed_at or approval.requested_at
        entries.append(
            _entry(
                stage="approval",
                entity_type="operation_approval",
                entity_id=approval.id,
                timestamp=reviewed_at,
                equipment_id=approval.equipment_id,
                status=approval.status,
                extra={
                    "command_type": approval.command_type,
                    "risk_level": approval.risk_level.value
                    if approval.risk_level
                    else None,
                    "work_order_id": approval.work_order_id,
                    "command_executed": approval.command_executed,
                    "requested_at": approval.requested_at.isoformat()
                    if approval.requested_at
                    else None,
                    "reviewed_at": approval.reviewed_at.isoformat()
                    if approval.reviewed_at
                    else None,
                },
            )
        )

    # 确定性排序：时间 → 阶段语义序 → 实体 id。
    entries.sort(
        key=lambda item: (
            _ts(
                datetime.fromisoformat(item["timestamp"]) if item["timestamp"] else None
            ),
            STAGE_ORDER.get(item["stage"], 999),
            item["entity_id"],
            item["stage"],
        )
    )
    return entries


def derive_final_status(timeline: list[dict[str, Any]]) -> str:
    """从 timeline 推导链路最终状态（用于搜索过滤）。"""
    by_stage: dict[str, list[dict[str, Any]]] = {}
    for entry in timeline:
        by_stage.setdefault(entry["stage"], []).append(entry)

    approvals = by_stage.get("approval", [])
    if any(entry["status"] == "approved" for entry in approvals):
        return "approved"
    if any(entry["status"] == "pending" for entry in approvals):
        return "pending_approval"
    if by_stage.get("work_order"):
        return "work_order_created"
    analyses = by_stage.get("analysis", [])
    if any(entry["status"] == "WAITING_REVIEW" for entry in analyses):
        return "waiting_review"
    if by_stage.get("alarm"):
        return "alarm_raised"
    if by_stage.get("anomaly"):
        return "anomaly_detected"
    if by_stage.get("telemetry"):
        return "telemetry_ingested"
    return "empty"


def get_trace(db: Session, trace_id: str) -> dict[str, Any] | None:
    """返回单条链路概览 + 时间线；不存在任何实体时为 None。"""
    timeline = build_timeline(db, trace_id)
    if not timeline:
        return None

    timestamps = [
        datetime.fromisoformat(entry["timestamp"])
        for entry in timeline
        if entry["timestamp"]
    ]
    equipment_ids = sorted(
        {
            entry["equipment_id"]
            for entry in timeline
            if entry.get("equipment_id") is not None
        }
    )
    started_at = min(timestamps) if timestamps else None
    finished_at = max(timestamps) if timestamps else None
    duration_ms = (
        int((finished_at - started_at).total_seconds() * 1000)
        if started_at and finished_at and finished_at > started_at
        else 0
    )
    return {
        "trace_id": trace_id,
        "started_at": started_at.isoformat() if started_at else None,
        "finished_at": finished_at.isoformat() if finished_at else None,
        "duration_ms": duration_ms,
        "equipment_ids": equipment_ids,
        "final_status": derive_final_status(timeline),
        "stage_count": len({entry["stage"] for entry in timeline}),
        "event_count": len(timeline),
        "timeline": timeline,
    }


def search_traces(
    db: Session,
    *,
    trace_id: str | None = None,
    equipment_id: int | None = None,
    status: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """分页搜索链路。锚点：各核心表的非空 trace_id 并集。

    为避免无限查询：limit 上限 MAX_LIMIT，默认 50；
    返回 total（过滤后的候选总数）与 items（当前页概要）。
    """
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)

    # (model, 是否具有 equipment_id 列)
    anchors: list[tuple[Any, bool]] = [
        (TelemetryRecord, True),
        (AnomalyEvent, True),
        (RiskPrediction, True),
        (MaintenanceRecommendation, True),
        (IndustrialAlarm, True),
        (AlarmAnalysisRecord, False),
        (WorkOrder, True),
        (OperationApproval, True),
        (AgentRun, True),
    ]

    candidates: dict[str, dict[str, Any]] = {}

    def _absorb(trace: str, equipment: int | None, last_at: datetime) -> None:
        info = candidates.setdefault(
            trace, {"trace_id": trace, "equipment_ids": set(), "last_at": last_at}
        )
        info["last_at"] = max(info["last_at"], last_at)
        if equipment is not None:
            info["equipment_ids"].add(equipment)

    for model, has_equipment in anchors:
        columns: list[Any] = [model.trace_id, model.created_at]
        if has_equipment:
            columns.append(model.equipment_id)
        query = db.query(*columns).filter(model.trace_id.is_not(None))
        if trace_id:
            query = query.filter(model.trace_id == trace_id)
        if occurred_from is not None:
            query = query.filter(model.created_at >= occurred_from)
        if occurred_to is not None:
            query = query.filter(model.created_at <= occurred_to)
        for row in query.all():
            eq = row[2] if has_equipment else None
            _absorb(row[0], eq, row[1] or datetime(1970, 1, 1))

    results: list[dict[str, Any]] = []
    for info in candidates.values():
        if equipment_id is not None and equipment_id not in info["equipment_ids"]:
            continue
        results.append(info)

    # 按“最近活动时间”倒序，稳定排序键 (last_at, trace_id)。
    results.sort(key=lambda item: (item["last_at"], item["trace_id"]), reverse=True)
    total = len(results)
    page = results[offset : offset + limit]

    items: list[dict[str, Any]] = []
    for info in page:
        timeline = build_timeline(db, info["trace_id"])
        final_status = derive_final_status(timeline)
        if status and final_status != status:
            continue
        timestamps = [
            datetime.fromisoformat(entry["timestamp"])
            for entry in timeline
            if entry["timestamp"]
        ]
        items.append(
            {
                "trace_id": info["trace_id"],
                "started_at": min(timestamps).isoformat() if timestamps else None,
                "last_activity_at": info["last_at"].isoformat(),
                "equipment_ids": sorted(info["equipment_ids"]),
                "final_status": final_status,
                "stage_count": len({entry["stage"] for entry in timeline}),
                "event_count": len(timeline),
            }
        )

    # status 过滤在 Python 侧生效后修正 total。
    if status:
        total = len(items)

    return {"total": total, "limit": limit, "offset": offset, "items": items}
