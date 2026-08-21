"""OPC UA Client 抽象与实现。

安全约束（工业控制安全要求）：

- 网关**只读**：``OpcUaClient`` 协议不定义任何写方法；
- ``AsyncuaOpcUaClient`` 仅调用 ``read_data_value``，不持有可写句柄；
- 两个实现都显式提供 ``write_node`` 并直接抛出 :class:`PermissionError`，
  作为“read-only mode”的代码级防线；未来若支持写操作，必须先经过
  平台 Human Approval（OperationApproval）审批流，不允许绕过。

``asyncua`` 为可选依赖：仅在 ``opcua`` 模式下延迟导入；
Mock 模式（无真实 PLC / 未安装 asyncua）使用进程内 :class:`MockOpcUaClient`。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from app.industrial_gateway.opcua.models import (
    QUALITY_GOOD,
    NodeRead,
    quality_from_status_code,
)

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查需要
    from collections.abc import Callable

    # value_provider(node_id) -> (value, source_timestamp)
    ValueProvider = Callable[
        [str], tuple[float | bool | int | str | None, datetime | None]
    ]

READ_ONLY_MODE = "read-only"

_WRITE_REJECTED_MESSAGE = (
    "OPC UA Gateway 处于 read-only 模式：禁止写 PLC。"
    "写操作必须经过 Human Approval 审批流的独立通道。"
)


@runtime_checkable
class OpcUaClient(Protocol):
    """OPC UA 客户端最小协议（只读）。"""

    endpoint: str

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def read_node(self, node_id: str) -> NodeRead: ...


def _coerce_value(raw: Any) -> float | bool | int | str | None:
    """把 OPC UA DataValue 归一化为平台可处理的标量。"""
    if raw is None or isinstance(raw, bool | int | float | str):
        return raw
    if isinstance(raw, bytes):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AsyncuaOpcUaClient:
    """基于 ``asyncua`` 的真实 OPC UA 客户端（只读）。

    用于连接软件模拟器或现场 OPC UA Server / PLC 的 Server 接口。
    """

    def __init__(self, endpoint: str, *, timeout_seconds: float = 4.0) -> None:
        self.endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._client: Any | None = None

    @property
    def connected(self) -> bool:
        return self._client is not None

    async def connect(self) -> None:
        from asyncua import Client  # 延迟导入：Mock 模式无需安装 asyncua

        client = Client(self.endpoint, timeout=self._timeout_seconds)
        await client.connect()
        self._client = client

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    async def read_node(self, node_id: str) -> NodeRead:
        if self._client is None:
            raise ConnectionError("OPC UA 客户端未连接")
        node = self._client.get_node(node_id)
        data_value = await node.read_data_value()
        variant = getattr(data_value, "Value", None)
        raw_value = getattr(variant, "Value", None) if variant is not None else None
        status = getattr(data_value, "StatusCode", None)
        status_code = getattr(status, "value", None) if status is not None else None
        quality = quality_from_status_code(status_code)
        return NodeRead(
            node_id=node_id,
            value=_coerce_value(raw_value),
            source_timestamp=_as_utc(getattr(data_value, "SourceTimestamp", None)),
            status_code=status_code,
            quality=quality,
        )

    async def write_node(self, node_id: str, value: Any) -> None:
        """显式拒绝写入：网关 read-only，见模块 docstring。"""
        raise PermissionError(_WRITE_REJECTED_MESSAGE)


class MockOpcUaClient:
    """进程内 OPC UA 模拟客户端。

    不打开网络连接、不需要 ``asyncua``：从注入的 ``value_provider``
    读取确定性数值（通常来自 ``simulator.generator.MotorSimulator``），
    用于无真实 PLC 时的完整 Demo 与单元测试。
    """

    def __init__(
        self,
        endpoint: str = "mock://opcua-simulator",
        *,
        value_provider: ValueProvider | None = None,
    ) -> None:
        self.endpoint = endpoint
        self._value_provider = value_provider
        self._connected = False
        self._available = True

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def available(self) -> bool:
        return self._available

    def set_value_provider(self, provider: ValueProvider) -> None:
        self._value_provider = provider

    def set_available(self, available: bool) -> None:
        """注入连接故障，用于网关失败回退测试。"""
        self._available = available
        if not available:
            self._connected = False

    async def connect(self) -> None:
        if not self._available:
            raise ConnectionError(f"模拟 OPC UA Server 不可达: {self.endpoint}")
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def read_node(self, node_id: str) -> NodeRead:
        if not self._connected:
            raise ConnectionError("OPC UA 客户端未连接")
        if self._value_provider is None:
            raise ValueError("MockOpcUaClient 未配置 value_provider")
        value, timestamp = self._value_provider(node_id)
        return NodeRead(
            node_id=node_id,
            value=value,
            source_timestamp=_as_utc(timestamp),
            status_code=None,
            quality=QUALITY_GOOD,
        )

    async def write_node(self, node_id: str, value: Any) -> None:
        """显式拒绝写入：网关 read-only，见模块 docstring。"""
        raise PermissionError(_WRITE_REJECTED_MESSAGE)
