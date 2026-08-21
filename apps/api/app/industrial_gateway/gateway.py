"""工业协议网关门面：配置解析与客户端工厂。

配置全部来自环境变量（见 ``app.core.config.Settings`` 的 ``GATEWAY_*``），
默认关闭（``GATEWAY_ENABLED=false``），不影响既有 Mock 链路。

订阅（事件驱动）客户端与轮询客户端并列存在：
轮询用于 ``sync_once`` 周期读取，订阅用于 DataChange 事件驱动接入，
两者共享下游质量层与 AI 链路。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.core.config import Settings
from app.industrial_gateway.opcua.client import (
    AsyncuaOpcUaClient,
    MockOpcUaClient,
    OpcUaClient,
)
from app.industrial_gateway.opcua.subscription import (
    AsyncuaSubscriptionClient,
    MockSubscriptionClient,
    OpcUaSubscriptionClient,
)

GATEWAY_MODE_MOCK: Final = "mock"
GATEWAY_MODE_OPCUA: Final = "opcua"
SUPPORTED_GATEWAY_MODES: Final[frozenset[str]] = frozenset(
    {GATEWAY_MODE_MOCK, GATEWAY_MODE_OPCUA}
)

DEFAULT_ENDPOINT = "opc.tcp://127.0.0.1:4840/industrial-simulator/"
DEFAULT_MOCK_ENDPOINT = "mock://opcua-simulator"
DEFAULT_SUBSCRIPTION_MOCK_ENDPOINT = "mock://opcua-subscription"


@dataclass(slots=True, frozen=True)
class GatewayConfig:
    """网关运行配置（由 Settings 派生，只读）。"""

    enabled: bool
    mode: str
    endpoint: str
    poll_interval_seconds: float
    auto_ingest: bool
    mapping_config_path: str
    timeout_seconds: float
    subscription_enabled: bool = False
    subscription_sampling_ms: float = 1000.0
    subscription_debounce_ms: float = 1000.0
    read_only: bool = True

    @classmethod
    def from_settings(cls, settings: Settings) -> GatewayConfig:
        mode = settings.GATEWAY_MODE.strip().lower()
        if mode not in SUPPORTED_GATEWAY_MODES:
            raise ValueError(
                f"GATEWAY_MODE 仅支持 {sorted(SUPPORTED_GATEWAY_MODES)}，当前为 {mode!r}"
            )
        endpoint = settings.GATEWAY_ENDPOINT.strip()
        if not endpoint:
            endpoint = (
                DEFAULT_ENDPOINT
                if mode == GATEWAY_MODE_OPCUA
                else DEFAULT_MOCK_ENDPOINT
            )
        return cls(
            enabled=settings.GATEWAY_ENABLED,
            mode=mode,
            endpoint=endpoint,
            poll_interval_seconds=max(settings.GATEWAY_POLL_INTERVAL_SECONDS, 1.0),
            auto_ingest=settings.GATEWAY_AUTO_INGEST,
            mapping_config_path=settings.GATEWAY_MAPPING_CONFIG,
            timeout_seconds=settings.GATEWAY_TIMEOUT_SECONDS,
            subscription_enabled=settings.GATEWAY_SUBSCRIPTION_ENABLED,
            subscription_sampling_ms=settings.GATEWAY_SUBSCRIPTION_SAMPLING_MS,
            subscription_debounce_ms=settings.GATEWAY_SUBSCRIPTION_DEBOUNCE_MS,
        )


def build_client(config: GatewayConfig) -> OpcUaClient:
    """按模式构建只读 OPC UA 轮询客户端。"""
    if config.mode == GATEWAY_MODE_OPCUA:
        return AsyncuaOpcUaClient(
            config.endpoint, timeout_seconds=config.timeout_seconds
        )
    return MockOpcUaClient(endpoint=config.endpoint)


def build_subscription_client(config: GatewayConfig) -> OpcUaSubscriptionClient:
    """按模式构建只读 OPC UA 订阅客户端（事件驱动）。"""
    if config.mode == GATEWAY_MODE_OPCUA:
        return AsyncuaSubscriptionClient(
            config.endpoint, timeout_seconds=config.timeout_seconds
        )
    return MockSubscriptionClient(endpoint=DEFAULT_SUBSCRIPTION_MOCK_ENDPOINT)
