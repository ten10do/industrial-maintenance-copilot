"""工业事件链路追踪上下文（Trace Context）。

设计目标：

- 一次完整工业事件链（OPC UA DataChange → Telemetry → Anomaly →
  Prediction → Alarm → Analysis → Agent → Work Order → Approval）
  共享同一个 ``trace_id``；
- 基于 :mod:`contextvars`：天然 async-safe / request-safe /
  background-task-safe——每个 asyncio Task 派生时获得上下文副本，
  子任务内的绑定不会泄漏回父级，父级也不会污染子任务；
- 入口规则：
    * 已有 trace context → 复用；
    * 新工业事件入口（网关同步 / 订阅 flush / 手动遥测摄入）→ 生成新 trace_id；
    * 基于已有 Alarm 的分析 → 必须继承 Alarm 的 trace_id。

本模块不引入任何第三方依赖；OpenTelemetry 集成是可选的旁路
（见 ``app.core.otel``），失败不得影响业务链路。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import uuid4

logger = logging.getLogger("app.observability")

TRACE_ID_LENGTH = 36


def new_trace_id() -> str:
    """生成新的 trace_id（UUID4 字符串）。"""
    return str(uuid4())


@dataclass(frozen=True, slots=True)
class TraceContext:
    """一次工业事件链的追踪上下文。"""

    trace_id: str
    request_id: str | None = None
    source: str = "unknown"


_context: ContextVar[TraceContext | None] = ContextVar(
    "industrial_trace_context", default=None
)

# HTTP request_id 与工业业务 trace_id 语义严格分离：前者标识一次 HTTP
# 请求，后者标识一次跨系统工业事件链；二者不可互相覆盖。
_request_id_var: ContextVar[str | None] = ContextVar("http_request_id", default=None)


def current_request_id() -> str | None:
    """当前 HTTP request_id（由请求中间件设置）。"""
    return _request_id_var.get()


def set_request_id(value: str) -> object:
    """设置当前请求的 request_id，返回用于还原的 token。"""
    return _request_id_var.set(value)


def reset_request_id(token: object) -> None:
    """还原 request_id 上下文。"""
    _request_id_var.reset(token)  # type: ignore[arg-type]


def current_context() -> TraceContext | None:
    """返回当前上下文（无则 None）。只读，不创建。"""
    return _context.get()


def current_trace_id() -> str | None:
    """当前 trace_id；不在任何链路中时为 None。"""
    ctx = _context.get()
    return ctx.trace_id if ctx else None


def start_trace(source: str, *, request_id: str | None = None) -> TraceContext:
    """为新的工业事件入口生成并绑定全新 trace_id。

    仅在"入口"处调用（网关同步周期、订阅 flush、手动遥测摄入等）。
    """
    ctx = TraceContext(trace_id=new_trace_id(), request_id=request_id, source=source)
    _context.set(ctx)
    return ctx


def bind_trace(trace_id: str | None, *, source: str) -> TraceContext:
    """绑定一个已存在的 trace_id（例如继承自 Alarm 的分析链路）。

    若传入为空则生成新 id 并告警——调用方应显式决定入口语义，
    这里兜底以保证后续实体总能拿到非空 trace_id。
    """
    if not trace_id:
        logger.warning(
            "bind_trace called without trace_id (source=%s); generating new",
            source,
        )
        return start_trace(source)
    ctx = TraceContext(trace_id=str(trace_id), source=source)
    _context.set(ctx)
    return ctx


def reset_context(token: object) -> None:
    """配合 ``ContextVar.set`` 返回的 token 还原上下文（测试用）。"""
    # ContextVar.reset 需要 token 类型；这里收窄为 Any 以保持 API 简洁。
    _context.reset(token)  # type: ignore[arg-type]


def trace_attributes(**extra: object) -> dict[str, object]:
    """常用日志/span 属性组装：自动附带当前 trace_id。"""
    attrs: dict[str, object] = {}
    ctx = _context.get()
    if ctx:
        attrs["trace_id"] = ctx.trace_id
        if ctx.request_id:
            attrs["request_id"] = ctx.request_id
        attrs["trace_source"] = ctx.source
    attrs.update(extra)
    return attrs


class TraceLogFilter(logging.Filter):
    """把当前 trace_id / request_id 注入每条日志记录。

    未处于任何上下文时以 "-" 占位，保持日志行格式稳定。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = current_trace_id() or "-"
        record.request_id = current_request_id() or "-"
        return True
