"""工业 AI 运行时 Prometheus 指标（集中定义，registry 可注入）。

设计约束：

- **集中定义**：所有 metric 在本模块构建一次；业务代码通过
  ``get_metrics()`` 取用，禁止在各 service 里散落同名全局指标
  （否则 ``prometheus_client`` 会抛 Duplicated timeseries）；
- **registry 可注入**：应用默认使用模块级 registry；
  测试用 :func:`build_metrics` 构建独立 registry 实例实现隔离，
  不用 try/except 吞掉重复注册问题；
- **低基数标签**：只允许 protocol/mode/status/severity/risk_level/
  reason/model_family/agent_name/order_type 等有限集合；
  禁止 trace_id/equipment_id/alarm_id/work_order_id/rag query 作为标签。
"""

from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

__all__ = [
    "IndustrialMetrics",
    "build_metrics",
    "get_metrics",
    "render_metrics",
]


@dataclass(slots=True)
class IndustrialMetrics:
    """工业链路运行指标的集中容器。"""

    # Gateway
    gateway_connected: Gauge
    gateway_events_total: Counter
    gateway_quality_rejected_total: Counter
    gateway_event_buffer_size: Gauge
    gateway_flush_latency_seconds: Histogram

    # Telemetry
    telemetry_ingest_total: Counter
    telemetry_ingest_latency_seconds: Histogram
    telemetry_rejected_total: Counter

    # ML 推理（当前运行时为确定性规则预测器）
    ml_inference_total: Counter
    ml_inference_latency_seconds: Histogram
    ml_inference_errors_total: Counter

    # Alarm Intelligence
    industrial_alarm_total: Counter
    alarm_analysis_total: Counter
    alarm_analysis_latency_seconds: Histogram
    alarm_manual_review_total: Counter

    # RAG
    rag_retrieval_total: Counter
    rag_retrieval_latency_seconds: Histogram
    rag_empty_result_total: Counter
    rag_result_count: Histogram

    # Agent
    agent_runs_total: Counter
    agent_run_latency_seconds: Histogram
    agent_run_failures_total: Counter

    # Workflow
    work_orders_created_total: Counter
    human_review_total: Counter
    operation_approval_total: Counter


def build_metrics(registry: CollectorRegistry | None = None) -> IndustrialMetrics:
    """在指定 registry 上构建全部指标（测试注入独立 registry）。"""
    reg = registry or CollectorRegistry(auto_describe=True)
    buckets = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
    return IndustrialMetrics(
        gateway_connected=Gauge(
            "industrial_gateway_connected",
            "Industrial gateway connection state (1 connected / 0 not).",
            labelnames=["protocol", "mode"],
            registry=reg,
        ),
        gateway_events_total=Counter(
            "industrial_gateway_events_total",
            "Industrial gateway DataChange/read events processed.",
            labelnames=["protocol", "mode", "status"],
            registry=reg,
        ),
        gateway_quality_rejected_total=Counter(
            "industrial_gateway_quality_rejected_total",
            "Readings rejected by the data quality layer.",
            labelnames=["reason"],
            registry=reg,
        ),
        gateway_event_buffer_size=Gauge(
            "industrial_gateway_event_buffer_size",
            "Current subscription event buffer size.",
            registry=reg,
        ),
        gateway_flush_latency_seconds=Histogram(
            "industrial_gateway_flush_latency_seconds",
            "Subscription event-buffer flush latency.",
            buckets=buckets,
            registry=reg,
        ),
        telemetry_ingest_total=Counter(
            "telemetry_ingest_total",
            "Telemetry snapshots ingested into the AI pipeline.",
            labelnames=["status"],
            registry=reg,
        ),
        telemetry_ingest_latency_seconds=Histogram(
            "telemetry_ingest_latency_seconds",
            "Telemetry ingest (assess + persist + downstream chain) latency.",
            buckets=buckets,
            registry=reg,
        ),
        telemetry_rejected_total=Counter(
            "telemetry_rejected_total",
            "Telemetry snapshots skipped before ingestion.",
            labelnames=["reason"],
            registry=reg,
        ),
        ml_inference_total=Counter(
            "ml_inference_total",
            "Runtime prediction inferences performed.",
            labelnames=["model_family", "status"],
            registry=reg,
        ),
        ml_inference_latency_seconds=Histogram(
            "ml_inference_latency_seconds",
            "Runtime prediction inference latency.",
            labelnames=["model_family"],
            buckets=buckets,
            registry=reg,
        ),
        ml_inference_errors_total=Counter(
            "ml_inference_errors_total",
            "Runtime prediction inference failures.",
            labelnames=["model_family"],
            registry=reg,
        ),
        industrial_alarm_total=Counter(
            "industrial_alarm_total",
            "Industrial alarms raised by severity transition.",
            labelnames=["severity"],
            registry=reg,
        ),
        alarm_analysis_total=Counter(
            "alarm_analysis_total",
            "Alarm intelligence analyses completed.",
            labelnames=["status"],
            registry=reg,
        ),
        alarm_analysis_latency_seconds=Histogram(
            "alarm_analysis_latency_seconds",
            "End-to-end alarm analysis latency.",
            buckets=buckets,
            registry=reg,
        ),
        alarm_manual_review_total=Counter(
            "alarm_manual_review_total",
            "Analyses flagged for mandatory human review.",
            labelnames=["risk_level"],
            registry=reg,
        ),
        rag_retrieval_total=Counter(
            "rag_retrieval_total",
            "Knowledge retrieval executions.",
            labelnames=["status"],
            registry=reg,
        ),
        rag_retrieval_latency_seconds=Histogram(
            "rag_retrieval_latency_seconds",
            "Knowledge retrieval latency.",
            buckets=buckets,
            registry=reg,
        ),
        rag_empty_result_total=Counter(
            "rag_empty_result_total",
            "Retrievals returning zero results.",
            registry=reg,
        ),
        rag_result_count=Histogram(
            "rag_result_count",
            "Distribution of retrieval result counts.",
            buckets=(0, 1, 2, 3, 5, 8, 10, 20),
            registry=reg,
        ),
        agent_runs_total=Counter(
            "agent_runs_total",
            "Agent runs executed.",
            labelnames=["agent_name", "status"],
            registry=reg,
        ),
        agent_run_latency_seconds=Histogram(
            "agent_run_latency_seconds",
            "Agent run wall-clock latency.",
            labelnames=["agent_name"],
            buckets=buckets,
            registry=reg,
        ),
        agent_run_failures_total=Counter(
            "agent_run_failures_total",
            "Agent runs ended in error.",
            labelnames=["agent_name"],
            registry=reg,
        ),
        work_orders_created_total=Counter(
            "work_orders_created_total",
            "Work orders created by source workflow.",
            labelnames=["source"],
            registry=reg,
        ),
        human_review_total=Counter(
            "human_review_total",
            "Human review decisions on analyses.",
            labelnames=["action"],
            registry=reg,
        ),
        operation_approval_total=Counter(
            "operation_approval_total",
            "Operation approval requests by status/risk.",
            labelnames=["status", "risk_level"],
            registry=reg,
        ),
    )


_default_metrics: IndustrialMetrics | None = None
_default_registry: CollectorRegistry | None = None


def get_metrics() -> IndustrialMetrics:
    """进程级共享指标实例（懒加载，供业务代码使用）。"""
    global _default_metrics, _default_registry
    if _default_metrics is None or _default_registry is None:
        _default_registry = CollectorRegistry(auto_describe=True)
        _default_metrics = build_metrics(_default_registry)
    return _default_metrics


def render_metrics() -> tuple[bytes, str]:
    """渲染应用指标为 Prometheus 文本格式。（不含任何敏感数据）"""
    if _default_registry is None:
        return b"", CONTENT_TYPE_LATEST
    return generate_latest(_default_registry), CONTENT_TYPE_LATEST
