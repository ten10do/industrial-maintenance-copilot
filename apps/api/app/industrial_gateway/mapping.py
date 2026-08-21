"""设备映射：OPC UA NodeId ↔ 平台设备资产 + 指标。

映射完全配置化：

- 数据库表 ``opcua_node_mappings`` 是运行时唯一事实来源；
- YAML 配置（默认 ``configs/opcua-node-mapping.yaml``）用于初始化 /
  重新加载演示与现场映射，通过 :func:`seed_mappings_from_config` 落库；
- 不在任何业务代码中硬编码 NodeId。

指标名使用友好名（``temperature`` / ``vibration`` / ...），
经 :data:`SNAPSHOT_FIELD_BY_METRIC` 映射到平台遥测快照字段。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml
from sqlalchemy.orm import Session

from app.industrial_gateway.models import OpcUaNodeMapping
from app.models.equipment import Equipment

DEFAULT_MAPPING_CONFIG = Path("configs/opcua-node-mapping.yaml")

# 友好指标名 → TelemetrySnapshot 字段。不在表中的指标为 informational
# （如 running / alarm），仅展示，不进入遥测快照。
SNAPSHOT_FIELD_BY_METRIC: Final[dict[str, str]] = {
    "temperature": "bearing_temperature",
    "vibration": "vibration_rms",
    "current": "motor_current",
    "voltage": "motor_voltage",
    "speed": "rotational_speed",
    "load": "load_ratio",
    "ambient_temperature": "ambient_temperature",
}

INFORMATIONAL_METRICS: Final[frozenset[str]] = frozenset({"running", "alarm"})


def snapshot_field_for(metric_name: str) -> str | None:
    return SNAPSHOT_FIELD_BY_METRIC.get(metric_name.strip().lower())


@dataclass(slots=True, frozen=True)
class NodeMapping:
    """一条已解析的节点映射（设备已存在）。"""

    node_id: str
    equipment_id: int
    equipment_code: str
    metric_name: str
    unit: str
    scale: float = 1.0
    offset: float = 0.0
    enabled: bool = True
    informational: bool = False

    @property
    def snapshot_field(self) -> str | None:
        return None if self.informational else snapshot_field_for(self.metric_name)

    def apply_scaling(self, value: float) -> float:
        """应用 scale/offset 线性换算（工程值转换）。"""
        return value * self.scale + self.offset


@dataclass(slots=True)
class MappingSeedResult:
    created: int = 0
    updated: int = 0
    skipped: list[str] = field(default_factory=list)


def load_all_mappings(db: Session) -> list[NodeMapping]:
    """加载全部映射行（含禁用行），供节点列表展示。"""
    rows = (
        db.query(OpcUaNodeMapping, Equipment.code)
        .join(Equipment, Equipment.id == OpcUaNodeMapping.equipment_id)
        .order_by(OpcUaNodeMapping.node_id)
        .all()
    )
    return [_to_node_mapping(mapping, code) for mapping, code in rows]


def load_mappings(db: Session) -> list[NodeMapping]:
    """从数据库加载全部启用的节点映射（含设备信息）。"""
    rows = (
        db.query(OpcUaNodeMapping, Equipment.code)
        .join(Equipment, Equipment.id == OpcUaNodeMapping.equipment_id)
        .filter(OpcUaNodeMapping.enabled.is_(True))
        .order_by(OpcUaNodeMapping.node_id)
        .all()
    )
    return [_to_node_mapping(mapping, code) for mapping, code in rows]


def _to_node_mapping(mapping: OpcUaNodeMapping, equipment_code: str) -> NodeMapping:
    return NodeMapping(
        node_id=mapping.node_id,
        equipment_id=mapping.equipment_id,
        equipment_code=equipment_code,
        metric_name=mapping.metric_name,
        unit=mapping.unit,
        scale=mapping.scale,
        offset=mapping.offset,
        enabled=mapping.enabled,
        informational=mapping.informational,
    )


def seed_mappings_from_config(
    db: Session,
    config_path: str | Path = DEFAULT_MAPPING_CONFIG,
) -> MappingSeedResult:
    """把 YAML 映射配置同步进数据库（按 node_id upsert，幂等）。

    - ``equipment_code`` 必须能解析到平台设备，否则跳过并记录原因；
    - 已存在的 node_id 更新映射属性；新增的创建；
    - 不删除数据库中已有但配置中缺失的映射（现场手工映射优先）。
    """
    path = Path(config_path)
    payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries: list[dict[str, Any]] = list(payload.get("mappings") or [])
    result = MappingSeedResult()

    for entry in entries:
        node_id = str(entry.get("node_id", "")).strip()
        equipment_code = str(entry.get("equipment_code", "")).strip()
        metric = str(entry.get("metric", "")).strip().lower()
        unit = str(entry.get("unit", "")).strip()
        if not node_id or not equipment_code or not metric:
            result.skipped.append(f"{node_id or '<empty>'}: 配置缺少必填字段")
            continue

        equipment = db.query(Equipment).filter(Equipment.code == equipment_code).first()
        if equipment is None:
            result.skipped.append(
                f"{node_id}: 设备编码 {equipment_code} 在平台中不存在"
            )
            continue

        informational = (
            metric in INFORMATIONAL_METRICS or snapshot_field_for(metric) is None
        )
        defaults = {
            "equipment_id": equipment.id,
            "metric_name": metric,
            "unit": unit,
            "scale": float(entry.get("scale", 1.0)),
            "offset": float(entry.get("offset", 0.0)),
            "enabled": bool(entry.get("enabled", True)),
            "informational": bool(entry.get("informational", informational)),
        }
        existing = (
            db.query(OpcUaNodeMapping)
            .filter(OpcUaNodeMapping.node_id == node_id)
            .first()
        )
        if existing is None:
            db.add(OpcUaNodeMapping(node_id=node_id, **defaults))
            result.created += 1
        else:
            for key, value in defaults.items():
                setattr(existing, key, value)
            result.updated += 1

    db.commit()
    return result
