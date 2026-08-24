"""Alarm Correlation Engine 测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.industrial_gateway.alarm_intelligence.correlation import (
    CORRELATION_LINE_CASCADE,
    CORRELATION_SAME_EQUIPMENT,
    AlarmSnapshot,
    correlate_alarm_snapshots,
)


def _snap(
    alarm_id: int,
    equipment_id: int,
    offset_seconds: float,
    *,
    severity: str = "WARNING",
    base: datetime | None = None,
) -> AlarmSnapshot:
    return AlarmSnapshot(
        id=alarm_id,
        equipment_id=equipment_id,
        severity=severity,
        message=f"alarm-{alarm_id}",
        created_at=(base or datetime.now(UTC)) + timedelta(seconds=offset_seconds),
    )


def test_same_equipment_within_window_chains_into_one_group():
    base = datetime.now(UTC)
    groups = correlate_alarm_snapshots(
        [
            _snap(1, 10, 0, base=base),
            _snap(2, 10, 60, severity="CRITICAL", base=base),
            _snap(3, 10, 150, base=base),
        ],
        window_seconds=300,
    )
    assert len(groups) == 1
    group = groups[0]
    assert group.reason == CORRELATION_SAME_EQUIPMENT
    assert group.alarm_ids == [1, 2, 3]
    assert group.severity == "CRITICAL"  # 组严重度取最高
    assert group.size == 3


def test_gap_beyond_window_splits_groups():
    base = datetime.now(UTC)
    groups = correlate_alarm_snapshots(
        [
            _snap(1, 10, 0, base=base),
            _snap(2, 10, 600, base=base),  # 超出 300s 窗口
        ],
        window_seconds=300,
    )
    assert len(groups) == 2
    assert {group.reason for group in groups} == {CORRELATION_SAME_EQUIPMENT}


def test_different_equipment_not_grouped_without_line_info():
    base = datetime.now(UTC)
    groups = correlate_alarm_snapshots(
        [
            _snap(1, 10, 0, base=base),
            _snap(2, 20, 5, base=base),
        ],
        window_seconds=300,
    )
    assert len(groups) == 2


def test_line_cascade_merges_cross_equipment_groups():
    base = datetime.now(UTC)
    snapshots = [
        _snap(1, 10, 0, base=base),
        _snap(2, 20, 30, base=base),
    ]
    line_lookup = {10: ["Line-1"], 20: ["Line-1"]}
    groups = correlate_alarm_snapshots(
        snapshots, window_seconds=300, line_lookup=line_lookup
    )
    assert len(groups) == 1
    group = groups[0]
    assert group.reason == CORRELATION_LINE_CASCADE
    assert group.equipment_ids == [10, 20]
    assert group.alarm_ids == [1, 2]


def test_different_lines_do_not_merge():
    base = datetime.now(UTC)
    snapshots = [_snap(1, 10, 0, base=base), _snap(2, 20, 30, base=base)]
    line_lookup = {10: ["Line-1"], 20: ["Line-2"]}
    groups = correlate_alarm_snapshots(
        snapshots, window_seconds=300, line_lookup=line_lookup
    )
    assert len(groups) == 2


def test_group_id_is_deterministic_for_same_members():
    base = datetime.now(UTC)
    snapshots_a = [_snap(1, 10, 0, base=base), _snap(2, 10, 60, base=base)]
    snapshots_b = [_snap(2, 10, 60, base=base), _snap(1, 10, 0, base=base)]
    group_a = correlate_alarm_snapshots(snapshots_a)[0]
    group_b = correlate_alarm_snapshots(snapshots_b)[0]
    assert group_a.group_id == group_b.group_id


def test_unrelated_metric_families_on_same_equipment_are_not_merged():
    base = datetime.now(UTC)
    groups = correlate_alarm_snapshots(
        [
            AlarmSnapshot(1, 10, "WARNING", "轴承温度=82", base),
            AlarmSnapshot(2, 10, "WARNING", "电压异常=450", base),
        ],
        window_seconds=300,
    )
    assert len(groups) == 2
