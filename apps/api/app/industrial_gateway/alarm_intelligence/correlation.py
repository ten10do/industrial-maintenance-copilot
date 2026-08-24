"""Alarm Correlation Engine：把相关报警合并为一个关联事件组。

规则（确定性、可复现）：

- **same_equipment**：同一设备、时间间隔 ≤ ``window_seconds`` 的报警链入同组；
- **line_cascade**：不同设备但位于同一产线（``Equipment.production_line``）、
  且时间窗重叠 → 组间合并（级联/共性原因检测，如供电压降波及整线）；
- 组 ID 由成员 ID 排序后 uuid5 派生：同一成员集合永远得到同一 group_id。

纯函数、与数据库解耦：输入为报警快照，方便测试与复用。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from app.industrial_gateway.models import IndustrialAlarm

CORRELATION_SAME_EQUIPMENT: Final = "same_equipment"
CORRELATION_LINE_CASCADE: Final = "line_cascade"
DEFAULT_WINDOW_SECONDS: Final = 300.0

_UUID_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "industrial-maintenance:alarm-correlation"
)


@dataclass(slots=True, frozen=True)
class AlarmSnapshot:
    """关联引擎输入的报警快照（与 ORM 解耦）。"""

    id: int
    equipment_id: int
    severity: str
    message: str
    created_at: datetime
    alarm_type: str | None = None


@dataclass(slots=True)
class CorrelationGroup:
    """一个关联事件组（相关报警的合并视图）。"""

    group_id: str
    reason: str
    alarm_ids: list[int] = field(default_factory=list)
    equipment_ids: list[int] = field(default_factory=list)
    severity: str = "WARNING"
    window_start: datetime | None = None
    window_end: datetime | None = None

    @property
    def size(self) -> int:
        return len(self.alarm_ids)


def _group_id_for(alarm_ids: list[int]) -> str:
    members = ",".join(str(aid) for aid in sorted(alarm_ids))
    return uuid.uuid5(_UUID_NAMESPACE, members).hex


def _severity_rank(severity: str) -> int:
    return {"WARNING": 0, "CRITICAL": 1}.get(severity.upper(), 0)


def _snapshot_of(alarm: IndustrialAlarm) -> AlarmSnapshot:
    return AlarmSnapshot(
        id=alarm.id,
        equipment_id=alarm.equipment_id,
        severity=alarm.severity,
        message=alarm.message,
        created_at=alarm.created_at,
        alarm_type=_alarm_type_from_message(alarm.message),
    )


def _alarm_type_from_message(message: str) -> str:
    """从既有报警文本提取稳定的指标族，不引入第二套报警分类模型。"""
    normalized = message.lower()
    rules = (
        (("bearing", "轴承温度", "温升"), "bearing_temperature"),
        (("vibration", "振动"), "vibration"),
        (("current", "电流", "负载"), "motor_load"),
        (("voltage", "电压"), "voltage"),
        (("alarm 位", "alarm bit", "alarm）"), "alarm_bit"),
    )
    for keywords, alarm_type in rules:
        if any(keyword in normalized for keyword in keywords):
            return alarm_type
    return "unknown"


def _types_are_related(left: AlarmSnapshot, right: AlarmSnapshot) -> bool:
    left_type = left.alarm_type or _alarm_type_from_message(left.message)
    right_type = right.alarm_type or _alarm_type_from_message(right.message)
    if left_type == right_type or "unknown" in {left_type, right_type}:
        return True
    # 温升 + 振动是轴承退化的透明复合信号；Alarm 位可与同设备物理量关联。
    return {left_type, right_type} <= {
        "bearing_temperature",
        "vibration",
        "alarm_bit",
    }


def correlate_alarm_snapshots(
    snapshots: list[AlarmSnapshot],
    *,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    line_lookup: dict[int, list[str]] | None = None,
) -> list[CorrelationGroup]:
    """把报警快照按确定性规则合并为关联事件组。

    - 第一遍：same_equipment 链式分组（同设备间隔 ≤ window）；
    - 第二遍（可选）：line_cascade —— 提供 ``line_lookup``
      （equipment_id → 产线列表）时，同产线且时间窗重叠的组合并。

    返回按窗口起点排序的组列表；单条报警也形成单成员组（每个报警都可归属）。
    """
    ordered = sorted(snapshots, key=lambda item: (item.created_at, item.id))

    chains: list[list[AlarmSnapshot]] = []
    for snapshot in ordered:
        placed = False
        for chain in reversed(chains):
            tail = chain[-1]
            if tail.equipment_id != snapshot.equipment_id:
                continue
            if not _types_are_related(tail, snapshot):
                continue
            gap = (snapshot.created_at - tail.created_at).total_seconds()
            if 0 <= gap <= window_seconds:
                chain.append(snapshot)
                placed = True
                break
        if not placed:
            chains.append([snapshot])

    groups: list[CorrelationGroup] = [
        CorrelationGroup(
            group_id=_group_id_for([item.id for item in chain]),
            reason=CORRELATION_SAME_EQUIPMENT,
            alarm_ids=sorted(item.id for item in chain),
            equipment_ids=sorted({item.equipment_id for item in chain}),
            severity=max((item.severity for item in chain), key=_severity_rank),
            window_start=chain[0].created_at,
            window_end=chain[-1].created_at,
        )
        for chain in chains
    ]

    merged = _merge_line_cascades(groups, window_seconds, line_lookup or {})
    return sorted(merged, key=lambda group: (group.window_start, group.alarm_ids))


def _merge_line_cascades(
    groups: list[CorrelationGroup],
    window_seconds: float,
    line_lookup: dict[int, list[str]],
) -> list[CorrelationGroup]:
    """按产线级联合并组（无产线映射时原样返回）。"""
    if not line_lookup:
        return groups

    parent = list(range(len(groups)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def lines_of(group: CorrelationGroup) -> set[str]:
        result: set[str] = set()
        for equipment_id in group.equipment_ids:
            result.update(line_lookup.get(equipment_id, []))
        return result

    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            left, right = groups[i], groups[j]
            if not (lines_of(left) & lines_of(right)):
                continue
            assert left.window_start and left.window_end
            assert right.window_start and right.window_end
            overlap = (
                min(left.window_end, right.window_end)
                - max(left.window_start, right.window_start)
            ).total_seconds()
            if overlap >= -window_seconds:
                root_i, root_j = find(i), find(j)
                if root_i != root_j:
                    parent[max(root_i, root_j)] = min(root_i, root_j)

    buckets: dict[int, list[CorrelationGroup]] = {}
    for index, group in enumerate(groups):
        buckets.setdefault(find(index), []).append(group)

    result: list[CorrelationGroup] = []
    for members in buckets.values():
        if len(members) == 1:
            result.append(members[0])
            continue
        alarm_ids = sorted({aid for group in members for aid in group.alarm_ids})
        result.append(
            CorrelationGroup(
                group_id=_group_id_for(alarm_ids),
                reason=CORRELATION_LINE_CASCADE,
                alarm_ids=alarm_ids,
                equipment_ids=sorted(
                    {eid for group in members for eid in group.equipment_ids}
                ),
                severity=max((group.severity for group in members), key=_severity_rank),
                window_start=min(
                    (group.window_start for group in members if group.window_start),
                    default=None,
                ),
                window_end=max(
                    (group.window_end for group in members if group.window_end),
                    default=None,
                ),
            )
        )
    return result


def correlate_alarms(
    alarms: list[IndustrialAlarm],
    *,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    production_line_by_equipment: dict[int, str | None] | None = None,
) -> list[CorrelationGroup]:
    """便捷入口：对 ORM 报警行做关联（可选提供设备产线映射）。"""
    lines: dict[int, list[str]] = {}
    for equipment_id, line in (production_line_by_equipment or {}).items():
        if line:
            lines.setdefault(equipment_id, []).append(line)
    snapshots = [_snapshot_of(alarm) for alarm in alarms]
    return correlate_alarm_snapshots(
        snapshots, window_seconds=window_seconds, line_lookup=lines or None
    )
