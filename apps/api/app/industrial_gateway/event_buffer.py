"""事件缓冲（Event Buffer）：DataChange 事件进入快照构建前的最后一道聚合。

职责（需求第五阶段）：

- **batch aggregation**：同一 debounce 窗口内每个节点只保留最新值
  （例如 1 秒内 Temperature 变化 10 次 → 聚合为 1 个待发事件）；
- **debounce**：自窗口内最早事件起算，达到 ``debounce_seconds`` 才放行；
- **duplicate suppression**：同一节点时间戳未前进的事件直接抑制，
  与快照路径的质量去重规则保持一致。

不引入 Redis Stream / Kafka 等外部组件：纯进程内存缓冲 + 可注入时钟。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.industrial_gateway.opcua.subscription import NodeDataChange

OUTCOME_ACCEPTED = "accepted"
OUTCOME_DUPLICATE = "duplicate"


class EventBuffer:
    """有界按节点聚合的 DataChange 事件缓冲。"""

    def __init__(
        self,
        *,
        debounce_seconds: float = 1.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if debounce_seconds <= 0:
            raise ValueError("debounce_seconds 必须为正数")
        self._debounce_seconds = debounce_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._pending: dict[str, NodeDataChange] = {}
        self._last_timestamps: dict[str, datetime] = {}
        self.accepted_count = 0
        self.duplicate_count = 0

    @property
    def debounce_seconds(self) -> float:
        return self._debounce_seconds

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def add(self, event: NodeDataChange) -> str:
        """加入缓冲；返回 ``accepted`` 或 ``duplicate``。

        时间戳缺失时以当前时钟替代；同节点时间戳未前进视为重复并抑制。
        """
        timestamp = event.source_timestamp or self._clock()
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        last = self._last_timestamps.get(event.node_id)
        if last is not None and timestamp <= last:
            self.duplicate_count += 1
            return OUTCOME_DUPLICATE
        normalized = (
            NodeDataChange(
                node_id=event.node_id,
                value=event.value,
                source_timestamp=timestamp,
                status_code=event.status_code,
                quality=event.quality,
            )
            if event.source_timestamp is not timestamp
            else event
        )
        # batch aggregation：窗口内每节点只保留最新事件。
        self._pending[event.node_id] = normalized
        self._last_timestamps[event.node_id] = timestamp
        self.accepted_count += 1
        return OUTCOME_ACCEPTED

    def drain_due(self, now: datetime | None = None) -> list[NodeDataChange]:
        """返回到期批次的全部事件（每节点最新值）并清空 pending。"""
        if not self._pending:
            return []
        current = now or self._clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        timestamps = [
            event.source_timestamp
            for event in self._pending.values()
            if event.source_timestamp is not None
        ]
        if not timestamps:
            return []
        if (current - min(timestamps)).total_seconds() < self._debounce_seconds:
            return []
        drained = list(self._pending.values())
        self._pending.clear()
        return drained

    def force_drain(self) -> list[NodeDataChange]:
        """忽略 debounce 立即取走全部 pending（停止订阅 / 测试用）。"""
        drained = list(self._pending.values())
        self._pending.clear()
        return drained

    def reset(self) -> None:
        self._pending.clear()
        self._last_timestamps.clear()
