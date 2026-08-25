"""Observability API：Trace Explorer 与系统运行健康概览。

安全边界（重要）：

- 本路由**只读**：不提供任何 PLC 写、设备命令、审批或工单创建端点；
- 所有端点要求已认证用户；
- 返回内容经过脱敏（无 token / 密钥 / 原始凭证）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.industrial_gateway.models import (
    GATEWAY_STATUS_CONNECTED,
    AlarmAnalysisRecord,
    GatewayConnection,
    IndustrialAlarm,
)
from app.models.intelligence import AgentRun, TelemetryRecord
from app.models.user import User
from app.models.workorder import WorkOrder, WorkOrderStatusEnum
from app.services.observability_service import MAX_LIMIT, get_trace, search_traces

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/traces/{trace_id}")
def get_trace_detail(
    trace_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """按 trace_id 重建完整工业事件链时间线（真实领域对象聚合）。"""
    detail = get_trace(db, trace_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="未找到该 trace_id 的任何链路记录")
    return detail


@router.get("/traces")
def search_trace_list(
    trace_id: str | None = None,
    equipment_id: int | None = None,
    status: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """分页搜索工业事件链路（默认按最近活动倒序）。"""
    return search_traces(
        db,
        trace_id=trace_id,
        equipment_id=equipment_id,
        status=status,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
        offset=offset,
    )


@router.get("/metrics-summary")
def metrics_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """核心运行指标 JSON 汇总（供前端概览；Prometheus 原文走 /metrics）。"""

    def _count(model, *filters):  # type: ignore[no-untyped-def]
        query = db.query(func.count(model.id))
        for condition in filters:
            query = query.filter(condition)
        return int(query.scalar() or 0)

    try:
        telemetry_events = _count(TelemetryRecord)
        alarms_total = _count(IndustrialAlarm)
        alarms_active = _count(IndustrialAlarm, IndustrialAlarm.cleared_at.is_(None))
        work_orders_total = _count(WorkOrder)
        work_orders_open = _count(
            WorkOrder,
            WorkOrder.status.notin_(
                [
                    WorkOrderStatusEnum.completed,
                    WorkOrderStatusEnum.cancelled,
                ]
            ),
        )
        waiting_review = _count(
            AlarmAnalysisRecord,
            AlarmAnalysisRecord.analysis_status == "WAITING_REVIEW",
        )
        agent_runs = _count(AgentRun)

        latencies = (
            db.query(AgentRun.started_at, AgentRun.finished_at)
            .filter(
                AgentRun.started_at.is_not(None),
                AgentRun.finished_at.is_not(None),
            )
            .limit(500)
            .all()
        )
        durations = [
            (finished - started).total_seconds() * 1000
            for started, finished in latencies
            if finished and started
        ]
        agent_avg_latency_ms = (
            round(sum(durations) / len(durations), 1) if durations else None
        )

        trace_rows = (
            db.query(func.count(func.distinct(TelemetryRecord.trace_id)))
            .filter(TelemetryRecord.trace_id.is_not(None))
            .scalar()
        )
        traces_tracked = int(trace_rows or 0)

        return {
            "telemetry_events": telemetry_events,
            "alarms_total": alarms_total,
            "alarms_active": alarms_active,
            "work_orders_total": work_orders_total,
            "work_orders_open": work_orders_open,
            "analyses_waiting_review": waiting_review,
            "agent_runs_total": agent_runs,
            "agent_avg_latency_ms": agent_avg_latency_ms,
            "traces_tracked": traces_tracked,
        }
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503, detail=f"数据库暂不可用: {exc.__class__.__name__}"
        ) from exc


@router.get("/health")
def observability_health(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """平台运行健康概览。

    与 ``/health``（进程存活）、``/ready``（就绪探针）互补；
    只报告有真实探测证据的组件；无法探测的组件如实标记 unknown。
    """
    components: dict[str, dict[str, Any]] = {}

    # 数据库：真实执行一次轻量查询。
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        components["database"] = {"status": "healthy"}
    except SQLAlchemyError as exc:
        components["database"] = {
            "status": "unavailable",
            "error_type": type(exc).__name__,
        }

    # Redis：配置了才探测；未配置如实标记。
    if settings.REDIS_URL:
        try:
            Redis.from_url(settings.REDIS_URL).ping()
            components["redis"] = {"status": "healthy"}
        except RedisError as exc:
            components["redis"] = {
                "status": "unavailable",
                "error_type": type(exc).__name__,
            }
    else:
        components["redis"] = {"status": "unknown", "detail": "not_configured"}

    # 网关：读取连接状态行（含禁用语义）。探测 = 真实 DB 状态。
    row = db.query(GatewayConnection).first()
    if not settings.GATEWAY_ENABLED:
        gateway_status: Literal["healthy", "degraded", "unavailable", "unknown"] = (
            "unknown"
        )
        gateway_detail = "disabled"
    elif row is None:
        gateway_status = "unknown"
        gateway_detail = "no_connection_record"
    else:
        gateway_status = {
            GATEWAY_STATUS_CONNECTED: "healthy",
            "disconnected": "degraded",
            "error": "unavailable",
        }.get(row.status, "unknown")
        gateway_detail = f"status={row.status};mode={row.mode}"
    components["gateway"] = {"status": gateway_status, "detail": gateway_detail}

    # Worker / Scheduler：Redis 心跳新鲜度（与 app.runtime 心跳键一致）。
    if settings.REDIS_URL:
        now = datetime.now().astimezone()
        for role in ("worker", "scheduler"):
            key = f"intelligent-maintenance:{role}:heartbeat"
            try:
                value = Redis.from_url(settings.REDIS_URL).get(key)
            except RedisError as exc:
                components[role] = {
                    "status": "unavailable",
                    "error_type": type(exc).__name__,
                }
                continue
            if not isinstance(value, str):
                components[role] = {"status": "unavailable", "detail": "no_heartbeat"}
                continue
            heartbeat = datetime.fromisoformat(value)
            age_seconds = abs((now - heartbeat).total_seconds())
            components[role] = {
                "status": "healthy" if age_seconds < 60 else "degraded",
                "heartbeat_age_seconds": round(age_seconds, 1),
            }
    else:
        components["worker"] = {"status": "unknown", "detail": "not_configured"}
        components["scheduler"] = {"status": "unknown", "detail": "not_configured"}

    # ML 推理 / RAG 检索：仅报告可验证的事实，不伪造健康状态。
    components["ml_inference"] = {
        "status": "unknown",
        "detail": (
            "ai_provider_mock"
            if not settings.ai_actually_enabled
            else "provider_configured"
        ),
    }
    components["rag"] = {
        "status": "healthy"
        if components["database"]["status"] == "healthy"
        else "unavailable",
        "detail": "keyword_baseline_over_knowledge_base",
    }
    components["opentelemetry"] = {
        "status": "unknown" if not settings.OTEL_ENABLED else "healthy",
        "detail": "exporter_disabled"
        if not settings.OTEL_ENABLED
        else "otlp_configured",
        "sample_rate": settings.OTEL_TRACE_SAMPLE_RATE,
    }

    overall = "healthy"
    statuses = [value["status"] for value in components.values()]
    if any(status == "unavailable" for status in statuses) or any(
        status == "degraded" for status in statuses
    ):
        overall = "degraded"

    return {
        "status": overall,
        "checked_at": datetime.now().astimezone().isoformat(),
        "components": components,
    }
