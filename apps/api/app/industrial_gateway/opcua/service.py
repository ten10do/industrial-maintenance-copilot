"""OPC UA 网关服务编排：读取 → 质量校验 → 映射聚合 → 遥测入库。

职责：

- 维护连接状态与失败回退（连接失败不产生任何业务写入，退避重试）；
- 每个同步周期读取全部映射节点，交给 :class:`DataQualityLayer` 校验；
- 把通过校验的读数按设备聚合成 ``TelemetrySnapshot``；
- 调用既有 ``intelligence_service.ingest_snapshot`` 进入 AI 链路，
  **不旁路** Health Score / 异常检测 / 故障预测 / 工单生成。

安全：本服务只调用客户端的 ``read_node``，不存在任何写路径。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.gateways.equipment import TelemetrySnapshot
from app.industrial_gateway.gateway import GatewayConfig
from app.industrial_gateway.mapping import (
    NodeMapping,
    load_all_mappings,
    load_mappings,
    seed_mappings_from_config,
)
from app.industrial_gateway.models import (
    GATEWAY_STATUS_CONNECTED,
    GATEWAY_STATUS_DISCONNECTED,
    GATEWAY_STATUS_ERROR,
    GatewayConnection,
)
from app.industrial_gateway.opcua.client import OpcUaClient
from app.industrial_gateway.opcua.models import (
    QUALITY_UNCERTAIN,
    TELEMETRY_SOURCE_OPCUA,
    NodeRead,
    NodeSnapshotEntry,
)
from app.industrial_gateway.quality import (
    DataQualityLayer,
    UnitConversionError,
    convert_value,
)
from app.models.equipment import Equipment
from app.services.intelligence_service import ingest_snapshot

logger = logging.getLogger("app.industrial_gateway")

DEFAULT_CONNECTION_NAME = "primary-opcua"

# 组成完整评估快照所必需的平台指标字段（与 assess_snapshot 对齐：
# 任一缺失都会被判定为传感器故障，因此不完整快照整批跳过）。
REQUIRED_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "vibration_rms",
    "bearing_temperature",
    "motor_current",
    "motor_voltage",
    "load_ratio",
)


@dataclass(slots=True)
class GatewaySyncResult:
    """一次网关同步（读取→校验→入库）的完整结论。"""

    ok: bool = False
    error: str | None = None
    reads_total: int = 0
    accepted: int = 0
    rejected: int = 0
    corrections: int = 0
    reject_reasons: dict[str, int] = field(default_factory=dict)
    snapshots_ingested: int = 0
    snapshots_skipped: int = 0
    anomalies: int = 0
    work_orders_created: int = 0
    telemetry_ids: list[int] = field(default_factory=list)
    skipped_details: list[str] = field(default_factory=list)
    duration_ms: float = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error": self.error,
            "reads_total": self.reads_total,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "corrections": self.corrections,
            "reject_reasons": self.reject_reasons,
            "snapshots_ingested": self.snapshots_ingested,
            "snapshots_skipped": self.snapshots_skipped,
            "anomalies": self.anomalies,
            "work_orders_created": self.work_orders_created,
            "telemetry_ids": self.telemetry_ids,
            "skipped_details": self.skipped_details,
            "duration_ms": self.duration_ms,
        }


class OpcUaGatewayService:
    """OPC UA 网关运行时：可手动同步，也可后台轮询。"""

    def __init__(
        self,
        client: OpcUaClient,
        *,
        mode: str,
        poll_interval_seconds: float = 5.0,
        auto_ingest: bool = True,
        mapping_config_path: str,
        connection_name: str = DEFAULT_CONNECTION_NAME,
        before_sync: Any = None,
    ) -> None:
        self._client = client
        self._mode = mode
        self._poll_interval_seconds = poll_interval_seconds
        self._auto_ingest = auto_ingest
        self._mapping_config_path = mapping_config_path
        self._connection_name = connection_name
        # Mock 模式下用于在每次同步前推进确定性仿真 tick。
        self._before_sync = before_sync

        self._quality = DataQualityLayer()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._running = False

        self._status = GATEWAY_STATUS_DISCONNECTED
        self._last_error: str | None = None
        self._last_connected_at: datetime | None = None
        self._last_sync_at: datetime | None = None
        self._consecutive_failures = 0
        self._seed_error: str | None = None

        self._node_entries: dict[str, NodeSnapshotEntry] = {}
        self._last_result: GatewaySyncResult | None = None
        self._totals = {
            "reads_total": 0,
            "accepted": 0,
            "rejected": 0,
            "snapshots_ingested": 0,
            "snapshots_skipped": 0,
            "anomalies": 0,
            "work_orders_created": 0,
        }

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    @property
    def client(self) -> OpcUaClient:
        return self._client

    @property
    def connection_status(self) -> str:
        return self._status

    async def _connect(self) -> None:
        await self._client.connect()
        self._status = GATEWAY_STATUS_CONNECTED
        self._last_connected_at = datetime.now(UTC)
        self._last_error = None
        self._consecutive_failures = 0

    async def test_connection(self, db: Session) -> dict[str, Any]:
        """测试连接：连接并探测一个映射节点；原本未连接则测后断开。"""
        was_connected = self._client.connected
        started = time.perf_counter()
        probe_node: str | None = None
        sample: float | bool | int | str | None = None
        try:
            if not was_connected:
                await self._client.connect()
            mappings = load_mappings(db)
            if mappings:
                probe_node = mappings[0].node_id
                read = await self._client.read_node(probe_node)
                sample = read.value
            self._status = GATEWAY_STATUS_CONNECTED
            self._last_connected_at = datetime.now(UTC)
            self._last_error = None
            self._persist_state(db)
            return {
                "ok": True,
                "endpoint": self._client.endpoint,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "probe_node": probe_node,
                "sample_value": sample,
                "error": None,
            }
        except Exception as exc:
            self._status = GATEWAY_STATUS_ERROR
            self._last_error = str(exc)
            self._persist_state(db)
            return {
                "ok": False,
                "endpoint": self._client.endpoint,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "probe_node": probe_node,
                "sample_value": None,
                "error": str(exc),
            }
        finally:
            if not was_connected and self._client.connected:
                await self._client.disconnect()

    # ------------------------------------------------------------------
    # 同步（读取 → 质量 → 聚合 → 入库）
    # ------------------------------------------------------------------

    async def sync_once(self, db: Session) -> GatewaySyncResult:
        """执行一次完整同步。连接失败时安全回退：不写任何业务数据。"""
        async with self._lock:
            started = time.perf_counter()
            result = GatewaySyncResult()
            try:
                if not self._client.connected:
                    await self._connect()
            except Exception as exc:
                return self._record_failure(db, result, exc, started)

            try:
                await self._collect(db, result)
            except Exception as exc:  # 防御：单次同步异常不中断轮询进程
                db.rollback()
                return self._record_failure(db, result, exc, started)

            result.ok = True
            self._status = GATEWAY_STATUS_CONNECTED
            self._last_sync_at = datetime.now(UTC)
            self._consecutive_failures = 0
            self._last_result = result
            self._accumulate_totals(result)
            self._persist_state(db)
            result.duration_ms = round((time.perf_counter() - started) * 1000, 1)
            return result

    def _record_failure(
        self,
        db: Session,
        result: GatewaySyncResult,
        exc: Exception,
        started: float,
    ) -> GatewaySyncResult:
        """失败回退：记录错误与连续失败次数，等待退避重试。

        回退保证：失败周期不写入任何业务数据，仅更新网关自身的连接状态。
        """
        result.error = str(exc)
        result.duration_ms = round((time.perf_counter() - started) * 1000, 1)
        self._status = GATEWAY_STATUS_ERROR
        self._last_error = str(exc)
        self._consecutive_failures += 1
        self._last_result = result
        logger.warning("网关同步失败（第 %d 次）：%s", self._consecutive_failures, exc)
        self._persist_state(db)
        return result

    async def _collect(self, db: Session, result: GatewaySyncResult) -> None:
        self.ensure_seed(db)
        mappings = load_mappings(db)
        if not mappings:
            result.snapshots_skipped += 1
            result.skipped_details.append("no_mappings: 未配置任何节点映射")
            return

        if self._before_sync is not None:
            self._before_sync()

        reads: list[NodeRead] = []
        for mapping in mappings:
            entry = self._entry_for(mapping)
            try:
                read = await self._client.read_node(mapping.node_id)
            except Exception as exc:
                entry.last_error = str(exc)
                result.reads_total += 1
                continue
            entry.last_error = None
            entry.last_value = read.value
            entry.last_quality = read.quality
            entry.last_timestamp = read.source_timestamp
            reads.append(read)
            result.reads_total += 1

        report = self._quality.process(reads)
        result.accepted = len(report.accepted)
        result.rejected = len(report.rejected)
        result.corrections = len(report.corrections)
        result.reject_reasons = report.reject_reasons()
        for rejected in report.rejected:
            cached = self._node_entries.get(rejected.node_id)
            if cached is not None:
                cached.last_error = f"{rejected.reason}: {rejected.detail}"

        accepted_by_node = {read.node_id: read for read in report.accepted}
        grouped: dict[int, list[tuple[NodeMapping, NodeRead]]] = {}
        for mapping in mappings:
            accepted_read = accepted_by_node.get(mapping.node_id)
            if accepted_read is not None:
                grouped.setdefault(mapping.equipment_id, []).append(
                    (mapping, accepted_read)
                )

        for equipment_id, pairs in grouped.items():
            equipment = db.get(Equipment, equipment_id)
            if equipment is None:
                result.snapshots_skipped += 1
                result.skipped_details.append(f"equipment_{equipment_id}: 设备不存在")
                continue
            snapshot, missing = self._build_snapshot(equipment, pairs)
            if snapshot is None:
                result.snapshots_skipped += 1
                result.skipped_details.append(
                    f"{equipment.code}: 快照不完整，缺少 {sorted(set(missing))}"
                )
                continue
            if not self._auto_ingest:
                result.snapshots_skipped += 1
                result.skipped_details.append(f"{equipment.code}: AUTO_INGEST 已关闭")
                continue
            ingestion = ingest_snapshot(db, equipment, snapshot)
            result.snapshots_ingested += 1
            result.anomalies += int(ingestion.anomaly is not None)
            result.work_orders_created += int(ingestion.work_order is not None)
            result.telemetry_ids.append(ingestion.telemetry.id)

    def _entry_for(self, mapping: NodeMapping) -> NodeSnapshotEntry:
        entry = self._node_entries.get(mapping.node_id)
        if entry is None:
            entry = NodeSnapshotEntry(
                node_id=mapping.node_id,
                equipment_code=mapping.equipment_code,
                metric_name=mapping.metric_name,
                unit=mapping.unit,
                enabled=mapping.enabled,
                informational=mapping.informational,
            )
            self._node_entries[mapping.node_id] = entry
        return entry

    def _build_snapshot(
        self, equipment: Equipment, pairs: list[tuple[NodeMapping, NodeRead]]
    ) -> tuple[TelemetrySnapshot | None, list[str]]:
        fields: dict[str, float] = {}
        quality_floor = 1.0
        latest_ts: datetime | None = None
        missing: list[str] = []

        for mapping, read in pairs:
            if read.source_timestamp is not None and (
                latest_ts is None or read.source_timestamp > latest_ts
            ):
                latest_ts = read.source_timestamp
            if read.quality == QUALITY_UNCERTAIN:
                quality_floor = min(quality_floor, 0.5)

            field_name = mapping.snapshot_field
            if field_name is None:
                continue  # informational 节点（running/alarm）仅展示
            try:
                value = convert_value(
                    mapping.metric_name,
                    mapping.unit,
                    float(read.value),  # type: ignore[arg-type]
                )
            except (UnitConversionError, TypeError, ValueError):
                missing.append(f"{mapping.metric_name}(unit={mapping.unit})")
                continue
            fields[field_name] = round(mapping.apply_scaling(value), 4)

        missing_required = [
            name for name in REQUIRED_SNAPSHOT_FIELDS if name not in fields
        ]
        if missing_required:
            missing.extend(missing_required)
            return None, missing

        return (
            TelemetrySnapshot(
                equipment_id=UUID(equipment.asset_uuid),
                collected_at=latest_ts or datetime.now(UTC),
                vibration_rms=fields.get("vibration_rms"),
                bearing_temperature=fields.get("bearing_temperature"),
                motor_current=fields.get("motor_current"),
                motor_voltage=fields.get("motor_voltage"),
                rotational_speed=fields.get("rotational_speed"),
                load_ratio=fields.get("load_ratio"),
                ambient_temperature=fields.get("ambient_temperature"),
                cumulative_runtime_hours=equipment.cumulative_runtime_hours,
                scenario=TELEMETRY_SOURCE_OPCUA,
                quality=quality_floor,
            ),
            [],
        )

    # ------------------------------------------------------------------
    # 后台轮询
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动后台轮询任务（需在事件循环内调用）。"""
        if self._running:
            return
        self._running = True
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._run_loop())

    def stop(self) -> None:
        self._running = False

    async def wait_stopped(self) -> None:
        task = self._task
        if task is not None:
            self._running = False
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            self._task = None

    async def _run_loop(self) -> None:
        while self._running:
            db = SessionLocal()
            try:
                await self.sync_once(db)
            except Exception:  # pragma: no cover - sync_once 内部已兜底
                db.rollback()
            finally:
                db.close()
            # 失败退避：连续失败时按 2^n 拉长重试间隔，最长 16 倍。
            backoff = min(2 ** min(self._consecutive_failures, 4), 16)
            await asyncio.sleep(self._poll_interval_seconds * backoff)

    # ------------------------------------------------------------------
    # 状态、持久化与配置装载
    # ------------------------------------------------------------------

    def ensure_seed(self, db: Session) -> None:
        """首次使用时装载 YAML 映射配置（表为空才执行，幂等）。"""
        from app.industrial_gateway.models import OpcUaNodeMapping

        if db.query(OpcUaNodeMapping).count() > 0:
            return
        from pathlib import Path

        path = Path(self._mapping_config_path)
        if not path.exists():
            self._seed_error = f"映射配置文件不存在: {path}"
            return
        result = seed_mappings_from_config(db, path)
        logger.info(
            "已从 %s 装载节点映射：新建 %d，更新 %d，跳过 %d",
            path,
            result.created,
            result.updated,
            len(result.skipped),
        )

    @property
    def seed_error(self) -> str | None:
        return self._seed_error

    def reload_mappings(self, db: Session) -> dict[str, Any]:
        from pathlib import Path

        result = seed_mappings_from_config(db, Path(self._mapping_config_path))
        return {
            "created": result.created,
            "updated": result.updated,
            "skipped": result.skipped,
        }

    def ensure_connection_row(self, db: Session) -> GatewayConnection:
        row = (
            db.query(GatewayConnection)
            .filter(GatewayConnection.name == self._connection_name)
            .first()
        )
        if row is None:
            row = GatewayConnection(
                name=self._connection_name,
                protocol="opcua",
                endpoint=self._client.endpoint,
                mode=self._mode,
                status=self._status,
                poll_interval_seconds=self._poll_interval_seconds,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    def _persist_state(self, db: Session) -> None:
        try:
            row = self.ensure_connection_row(db)
            row.endpoint = self._client.endpoint
            row.mode = self._mode
            row.status = self._status
            row.poll_interval_seconds = self._poll_interval_seconds
            row.last_connected_at = self._last_connected_at
            row.last_sync_at = self._last_sync_at
            row.last_error = self._last_error
            db.commit()
        except Exception:  # pragma: no cover - 状态持久化失败不影响采集
            db.rollback()
            logger.exception("保存网关连接状态失败")

    def node_entries(self, db: Session) -> list[NodeSnapshotEntry]:
        """当前全部映射节点及其最近读数状态（含禁用行）。"""
        entries: list[NodeSnapshotEntry] = []
        for mapping in load_all_mappings(db):
            entry = NodeSnapshotEntry(
                node_id=mapping.node_id,
                equipment_code=mapping.equipment_code,
                metric_name=mapping.metric_name,
                unit=mapping.unit,
                enabled=mapping.enabled,
                informational=mapping.informational,
            )
            cached = self._node_entries.get(mapping.node_id)
            if cached is not None:
                entry.last_value = cached.last_value
                entry.last_quality = cached.last_quality
                entry.last_timestamp = cached.last_timestamp
                entry.last_error = cached.last_error
            entries.append(entry)
        return entries

    def status(self) -> dict[str, Any]:
        return {
            "mode": self._mode,
            "endpoint": self._client.endpoint,
            "connected": self._client.connected,
            "connection_status": self._status,
            "running": self._running,
            "poll_interval_seconds": self._poll_interval_seconds,
            "auto_ingest": self._auto_ingest,
            "read_only": True,
            "last_connected_at": _iso(self._last_connected_at),
            "last_sync_at": _iso(self._last_sync_at),
            "last_error": self._last_error,
            "consecutive_failures": self._consecutive_failures,
            "totals": dict(self._totals),
            "last_sync": self._last_result.to_dict() if self._last_result else None,
        }

    def _accumulate_totals(self, result: GatewaySyncResult) -> None:
        self._totals["reads_total"] += result.reads_total
        self._totals["accepted"] += result.accepted
        self._totals["rejected"] += result.rejected
        self._totals["snapshots_ingested"] += result.snapshots_ingested
        self._totals["snapshots_skipped"] += result.snapshots_skipped
        self._totals["anomalies"] += result.anomalies
        self._totals["work_orders_created"] += result.work_orders_created


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


# ----------------------------------------------------------------------
# 运行时装配（模块级单例）
# ----------------------------------------------------------------------

_gateway_runtime: OpcUaGatewayService | None = None


def get_gateway_runtime() -> OpcUaGatewayService:
    """按 Settings 装配网关运行时（懒加载单例）。"""
    global _gateway_runtime
    if _gateway_runtime is not None:
        return _gateway_runtime

    from app.core.config import settings
    from app.industrial_gateway.gateway import build_client
    from app.industrial_gateway.opcua.client import MockOpcUaClient
    from app.industrial_gateway.simulator.generator import MotorSimulator

    config: GatewayConfig = GatewayConfig.from_settings(settings)
    client = build_client(config)
    before_sync = None
    if isinstance(client, MockOpcUaClient):
        # Mock 模式：接入确定性电机仿真，作为进程内“设备数据源”。
        simulator = MotorSimulator(seed=42, scenario="normal")
        client.set_value_provider(simulator.value_provider())
        before_sync = simulator.advance

    _gateway_runtime = OpcUaGatewayService(
        client,
        mode=config.mode,
        poll_interval_seconds=config.poll_interval_seconds,
        auto_ingest=config.auto_ingest,
        mapping_config_path=config.mapping_config_path,
        before_sync=before_sync,
    )
    return _gateway_runtime


def reset_gateway_runtime() -> None:
    """测试专用：清空运行时单例。"""
    global _gateway_runtime
    _gateway_runtime = None
