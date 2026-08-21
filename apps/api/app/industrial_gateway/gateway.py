"""工业协议网关门面：配置解析与客户端工厂。

配置全部来自环境变量（见 ``app.core.config.Settings`` 的 ``GATEWAY_*``），
默认关闭（``GATEWAY_ENABLED=false``），不影响既有 Mock 链路。
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

GATEWAY_MODE_MOCK: Final = "mock"
GATEWAY_MODE_OPCUA: Final = "opcua"
SUPPORTED_GATEWAY_MODES: Final[frozenset[str]] = frozenset(
    {GATEWAY_MODE_MOCK, GATEWAY_MODE_OPCUA}
)

DEFAULT_ENDPOINT = "opc.tcp://127.0.0.1:4840/industrial-simulator/"


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
                else "mock://opcua-simulator"
            )
        return cls(
            enabled=settings.GATEWAY_ENABLED,
            mode=mode,
            endpoint=endpoint,
            poll_interval_seconds=max(settings.GATEWAY_POLL_INTERVAL_SECONDS, 1.0),
            auto_ingest=settings.GATEWAY_AUTO_INGEST,
            mapping_config_path=settings.GATEWAY_MAPPING_CONFIG,
            timeout_seconds=settings.GATEWAY_TIMEOUT_SECONDS,
        )


def build_client(config: GatewayConfig) -> OpcUaClient:
    """按模式构建只读 OPC UA 客户端。"""
    if config.mode == GATEWAY_MODE_OPCUA:
        return AsyncuaOpcUaClient(
            config.endpoint, timeout_seconds=config.timeout_seconds
        )
    return MockOpcUaClient(endpoint=config.endpoint)
