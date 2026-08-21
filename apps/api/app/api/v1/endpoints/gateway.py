"""工业协议网关 API：连接状态、节点列表、连接测试与手动同步。

所有端点均为只读或触发一次只读采集；不提供任何写 PLC 的接口。
``/sync`` 与 ``/mappings/reload`` 会写平台业务数据 / 映射表，
因此限制为 supervisor/admin。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, supervisor_or_admin
from app.db.session import get_db
from app.industrial_gateway.models import GatewaySubscription
from app.industrial_gateway.opcua.service import get_gateway_runtime
from app.industrial_gateway.schemas import (
    GatewayConnectionOut,
    GatewayNodesOut,
    GatewayStatusOut,
    GatewaySubscriptionRowOut,
    GatewaySyncOut,
    MappingReloadOut,
    SubscriptionActionOut,
    SubscriptionStatusOut,
    TestConnectOut,
)
from app.models.user import User

router = APIRouter(prefix="/gateway", tags=["industrial-gateway"])


@router.get("/status", response_model=GatewayStatusOut)
def gateway_status(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> GatewayStatusOut:
    """网关连接状态：connection status / OPC UA server / last sync time。"""
    from app.core.config import settings

    runtime = get_gateway_runtime()
    runtime.ensure_seed(db)
    connection = runtime.ensure_connection_row(db)
    return GatewayStatusOut(
        connection=GatewayConnectionOut.model_validate(connection),
        runtime=runtime.status(),
        enabled=settings.GATEWAY_ENABLED,
        read_only=True,
        seed_error=runtime.seed_error,
    )


@router.get("/nodes", response_model=GatewayNodesOut)
def gateway_nodes(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> GatewayNodesOut:
    """当前映射的全部设备节点及最近读数与质量状态。"""
    runtime = get_gateway_runtime()
    runtime.ensure_seed(db)
    return GatewayNodesOut(
        nodes=runtime.node_entries(db),
        read_only=True,
    )


@router.post("/test-connect", response_model=TestConnectOut)
async def test_connect(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TestConnectOut:
    """测试与 OPC UA Server 的连接（只读探测，不入库）。"""
    runtime = get_gateway_runtime()
    result = await runtime.test_connection(db)
    return TestConnectOut(**result)


@router.post("/sync", response_model=GatewaySyncOut)
async def gateway_sync(
    db: Session = Depends(get_db),
    _user: User = Depends(supervisor_or_admin),
) -> GatewaySyncOut:
    """手动执行一次「读取 → 质量校验 → 遥测入库」同步。"""
    runtime = get_gateway_runtime()
    runtime.ensure_seed(db)
    result = await runtime.sync_once(db)
    return GatewaySyncOut(**result.to_dict())


@router.post("/mappings/reload", response_model=MappingReloadOut)
def reload_mappings(
    db: Session = Depends(get_db),
    _user: User = Depends(supervisor_or_admin),
) -> MappingReloadOut:
    """从 YAML 配置重新装载节点映射（按 node_id 幂等 upsert）。"""
    runtime = get_gateway_runtime()
    return MappingReloadOut(**runtime.reload_mappings(db))


@router.get("/subscriptions", response_model=SubscriptionStatusOut)
def subscription_status(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SubscriptionStatusOut:
    """查看 DataChange 订阅状态：active nodes / sampling interval / 事件计数。"""
    runtime = get_gateway_runtime()
    runtime.ensure_seed(db)
    status = runtime.subscription_status()
    connection = runtime.ensure_connection_row(db)
    rows = (
        db.query(GatewaySubscription)
        .filter(GatewaySubscription.gateway_id == connection.id)
        .order_by(GatewaySubscription.node_id)
        .all()
    )
    return SubscriptionStatusOut(
        ok=True,
        status=status["subscription_status"],
        rows=[GatewaySubscriptionRowOut.model_validate(row) for row in rows],
        **status,
    )


@router.post("/subscriptions/start", response_model=SubscriptionActionOut)
async def start_subscriptions(
    db: Session = Depends(get_db),
    _user: User = Depends(supervisor_or_admin),
) -> SubscriptionActionOut:
    """启动 DataChange 订阅（事件驱动接入，只读）。"""
    runtime = get_gateway_runtime()
    result = await runtime.start_subscription(db)
    detail = {
        k: v
        for k, v in result.items()
        if k not in {"ok", "status", "already_active", "error"}
    }
    return SubscriptionActionOut(
        ok=result["ok"],
        status=result["status"],
        already_active=result.get("already_active", False),
        error=result.get("error"),
        detail=detail,
    )


@router.post("/subscriptions/stop", response_model=SubscriptionActionOut)
async def stop_subscriptions(
    db: Session = Depends(get_db),
    _user: User = Depends(supervisor_or_admin),
) -> SubscriptionActionOut:
    """停止 DataChange 订阅（轮询能力保持可用）。"""
    runtime = get_gateway_runtime()
    result = await runtime.stop_subscription(db)
    return SubscriptionActionOut(ok=result["ok"], status=result["status"])
