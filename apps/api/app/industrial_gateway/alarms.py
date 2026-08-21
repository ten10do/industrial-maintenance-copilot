"""工业报警（Industrial Alarm）事件流水线。

把 OPC UA DataChange / Alarm 信号转换为平台工业报警记录：

- 状态机：NORMAL → WARNING → CRITICAL（可回落 NORMAL 表示解除）；
- **仅状态跃迁时**产生/解除报警，避免高频事件刷屏；
- 判定阈值与平台 ``SENSOR_DEFINITIONS`` 警告阈值对齐；
- ``Alarm`` 布尔节点置位时直接判定为 CRITICAL（现场急停/报警位语义）。

只读约束：本模块只产生平台内的报警记录，不向设备写入任何内容。
"""

from __future__ import annotations

from typing import Final

ALARM_STATE_NORMAL: Final = "NORMAL"
ALARM_STATE_WARNING: Final = "WARNING"
ALARM_STATE_CRITICAL: Final = "CRITICAL"
ALARM_STATES: Final[frozenset[str]] = frozenset(
    {ALARM_STATE_NORMAL, ALARM_STATE_WARNING, ALARM_STATE_CRITICAL}
)

# 与 intelligence_service.SENSOR_DEFINITIONS 的警告阈值保持一致。
_WARNING_THRESHOLDS: Final[dict[str, tuple[bool, float]]] = {
    # field: (is_upper_bound, threshold)
    "bearing_temperature": (True, 75.0),
    "vibration_rms": (True, 4.5),
    "motor_current": (True, 27.0),
    "load_ratio": (True, 100.0),
}
VOLTAGE_LOWER: Final = 342.0
VOLTAGE_UPPER: Final = 418.0


def evaluate_alarm_state(
    snapshot_fields: dict[str, float | bool | None],
    *,
    alarm_active: bool,
) -> str:
    """根据快照指标与 Alarm 位判定当前报警状态。

    ``snapshot_fields`` 使用平台遥测字段名（bearing_temperature 等）。
    """
    if alarm_active:
        return ALARM_STATE_CRITICAL
    for field_name, (is_upper, threshold) in _WARNING_THRESHOLDS.items():
        value = snapshot_fields.get(field_name)
        if isinstance(value, bool) or value is None:
            continue
        if is_upper and value > threshold:
            return ALARM_STATE_WARNING
    voltage = snapshot_fields.get("motor_voltage")
    if isinstance(voltage, (int, float)) and not (
        VOLTAGE_LOWER <= float(voltage) <= VOLTAGE_UPPER
    ):
        return ALARM_STATE_WARNING
    return ALARM_STATE_NORMAL


def build_alarm_message(
    state: str,
    snapshot_fields: dict[str, float | bool | None],
    *,
    alarm_active: bool,
) -> str:
    """生成报警消息（中文，含越限指标明细）。"""
    if state == ALARM_STATE_CRITICAL:
        detail = "设备报警位（Alarm）已置位" if alarm_active else "指标进入临界区间"
        return f"工业报警升级为 CRITICAL：{detail}"
    if state == ALARM_STATE_WARNING:
        offenders: list[str] = []
        label_by_field = {
            "bearing_temperature": "轴承温度",
            "vibration_rms": "振动 RMS",
            "motor_current": "电机电流",
            "load_ratio": "负载率",
        }
        for field_name, (is_upper, threshold) in _WARNING_THRESHOLDS.items():
            value = snapshot_fields.get(field_name)
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and is_upper
                and float(value) > threshold
            ):
                offenders.append(f"{label_by_field[field_name]}={float(value):.1f}")
        voltage = snapshot_fields.get("motor_voltage")
        if (
            isinstance(voltage, (int, float))
            and not isinstance(voltage, bool)
            and not (VOLTAGE_LOWER <= float(voltage) <= VOLTAGE_UPPER)
        ):
            offenders.append(f"电机电压={float(voltage):.1f}V")
        detail = "、".join(offenders) or "多项指标越限"
        return f"工业报警升级为 WARNING：{detail}"
    return "工业报警解除：指标恢复正常区间"
