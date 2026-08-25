"""可选 OpenTelemetry 集成（默认关闭）。

原则：

- ``OTEL_ENABLED=false``（默认）：零依赖路径——本模块的
  :func:`industrial_span` 返回空操作上下文，业务行为完全不变；
- ``OTEL_ENABLED=true``：初始化 TracerProvider + OTLP HTTP Exporter；
  Collector 不可达时**仅记录告警并继续**，绝不抛错阻断工业链路；
- 采样率由 ``OTEL_TRACE_SAMPLE_RATE`` 控制（0.0~1.0）。

只覆盖关键工业阶段，不给每行代码打 span：
    gateway.receive / gateway.quality_check / gateway.buffer_flush /
    telemetry.ingest / anomaly.detect / prediction.infer /
    alarm.evaluate / alarm.correlate / alarm.analyze / rag.retrieve /
    agent.run / tool.invoke / work_order.create / approval.review
"""

from __future__ import annotations

import contextlib
import functools
import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from app.core.config import settings

logger = logging.getLogger("app.observability")

_state_lock = threading.Lock()
_tracer: Any | None = None
_initialised = False


def _initialise() -> Any | None:
    """懒加载并初始化 OTel TracerProvider；失败时返回 None 并降级。"""
    global _tracer, _initialised
    with _state_lock:
        if _initialised:
            return _tracer
        _initialised = True
        if not settings.OTEL_ENABLED:
            return None
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.trace.sampling import (
                ParentBased,
                TraceIdRatioBased,
            )

            resource = Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
            provider = TracerProvider(
                resource=resource,
                sampler=ParentBased(
                    TraceIdRatioBased(
                        max(0.0, min(settings.OTEL_TRACE_SAMPLE_RATE, 1.0))
                    )
                ),
            )
            endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
            exporter = (
                OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            _tracer = trace.get_tracer("app.industrial")
            logger.info(
                "OpenTelemetry enabled (service=%s endpoint=%s sample=%.2f)",
                settings.OTEL_SERVICE_NAME,
                endpoint or "(default)",
                settings.OTEL_TRACE_SAMPLE_RATE,
            )
        except Exception as exc:
            logger.warning("OpenTelemetry init failed; continuing without: %s", exc)
            _tracer = None
        return _tracer


@contextmanager
def industrial_span(
    name: str, attributes: dict[str, Any] | None = None
) -> Iterator[Any]:
    """关键工业阶段的 span 上下文；未启用时为无开销空操作。

    任何 OTel 相关异常都被吞掉并降级为空操作——观测绝不阻断业务。
    """
    tracer = _initialise() if settings.OTEL_ENABLED else None
    if tracer is None:
        yield None
        return
    try:
        with tracer.start_as_current_span(name) as span:
            for key, value in (attributes or {}).items():
                if value is not None:
                    # 属性设置失败不影响链路（观测降级）。
                    with contextlib.suppress(Exception):
                        span.set_attribute(key, value)
            yield span
    except Exception as exc:
        logger.warning("span %s failed: %s", name, exc)
        yield None


def traced_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """函数级 span 装饰器（同步函数）。

    用于以一行成本覆盖关键工业阶段；attributes 为静态属性字典。
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with industrial_span(name, attributes):
                return func(*args, **kwargs)

        return wrapper

    return decorator
