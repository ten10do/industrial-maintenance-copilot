"""OPC UA 网关内部数据结构：节点读取结果与质量标记。

这里不依赖 ``asyncua``，保证 Mock 模式零额外依赖可运行。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# OPC UA 状态码分类位（OPC 10000-4 §8.41 简化版）：
#   bit31=1 → Bad；bit30=1 → Uncertain；否则 Good。
_STATUS_BAD_BIT = 0x8000_0000
_STATUS_UNCERTAIN_BIT = 0x4000_0000

QUALITY_GOOD = "good"
QUALITY_UNCERTAIN = "uncertain"
QUALITY_BAD = "bad"

# 遥测统一来源标记：写入 TelemetryRecord.scenario，用于区分 OPC UA 数据。
TELEMETRY_SOURCE_OPCUA = "opcua"


def quality_from_status_code(status_code: int | None) -> str:
    """把 OPC UA StatusCode 归类为 good / uncertain / bad。

    ``None`` 视为 Good：部分模拟服务器与 Mock 客户端不填充状态码。
    """
    if status_code is None:
        return QUALITY_GOOD
    if status_code & _STATUS_BAD_BIT:
        return QUALITY_BAD
    if status_code & _STATUS_UNCERTAIN_BIT:
        return QUALITY_UNCERTAIN
    return QUALITY_GOOD


@dataclass(slots=True, frozen=True)
class NodeRead:
    """一次 OPC UA 节点读取的原始结果（进入质量校验前）。"""

    node_id: str
    value: float | bool | int | str | None
    source_timestamp: datetime | None
    status_code: int | None = None
    quality: str = QUALITY_GOOD
    unit_hint: str | None = None

    @property
    def is_bad(self) -> bool:
        return self.quality == QUALITY_BAD


@dataclass(slots=True, frozen=True)
class RejectedRead:
    """被 Data Quality Layer 拒绝的读数与原因。"""

    node_id: str
    reason: str
    detail: str = ""


@dataclass(slots=True)
class NodeSnapshotEntry:
    """供 API 展示的“当前节点状态”（映射 + 最近一次读数 + 质量结论）。"""

    node_id: str
    equipment_code: str | None
    metric_name: str
    unit: str
    enabled: bool
    informational: bool
    last_value: float | bool | int | str | None = None
    last_quality: str | None = None
    last_timestamp: datetime | None = None
    last_error: str | None = None
