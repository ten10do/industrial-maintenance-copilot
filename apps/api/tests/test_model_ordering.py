"""Deterministic ordering regression tests.

上一阶段发现 ``checklist_items`` 缺失显式排序时，PostgreSQL 在 UPDATE 后
返回顺序不稳定（SQLite 因 rowid 序掩盖了问题）。本文件锁定所有
"顺序有业务含义" 的 relationship 的跨后端确定性排序行为。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.base import PriorityEnum, WorkOrderStatusEnum
from app.models.knowledge import KnowledgeArticle, KnowledgeChunk
from app.models.maintenance import MaintenanceLog
from app.models.user import RoleEnum, User
from app.models.workorder import (
    WorkOrder,
    WorkOrderChecklistItem,
    WorkOrderStatusHistory,
    WorkOrderTypeEnum,
)


def _user(db, email: str) -> User:
    from app.core.security import hash_password

    user = User(
        email=email,
        full_name=email,
        hashed_password=hash_password("test123"),
        role=RoleEnum.supervisor,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _work_order(db, user: User) -> WorkOrder:
    wo = WorkOrder(
        code="WO-ORDERING-001",
        title="排序回归测试工单",
        equipment_id=None,
        order_type=WorkOrderTypeEnum.fault_repair,
        priority=PriorityEnum.P2,
        status=WorkOrderStatusEnum.pending_dispatch,
        created_by_id=user.id,
        created_by=str(user.id),
    )
    db.add(wo)
    db.commit()
    db.refresh(wo)
    return wo


def test_maintenance_logs_ordered_by_created_then_id(db) -> None:
    """维修日志按 created_at 升序稳定返回，而非插入/堆序。"""
    user = _user(db, "log-user@test.com")
    wo = _work_order(db, user)
    base = datetime.now(UTC).replace(tzinfo=None)

    later = MaintenanceLog(
        work_order_id=wo.id,
        log_type="repair",
        content="后写入但时间更早标记",
        logged_at=base + timedelta(hours=2),
        created_at=base + timedelta(minutes=1),
    )
    earlier = MaintenanceLog(
        work_order_id=wo.id,
        log_type="note",
        content="先写入但时间更早",
        logged_at=base,
        created_at=base,
    )
    # 故意以"晚时间先插入"的顺序写入，锁定排序不依赖堆序。
    db.add_all([later, earlier])
    db.commit()

    db.refresh(wo)
    contents = [log.content for log in wo.logs]
    assert contents == ["先写入但时间更早", "后写入但时间更早标记"]


def test_status_history_append_only_order(db) -> None:
    """状态历史为追加式：按 id 升序 = 事件发生序，跨后端确定。"""
    user = _user(db, "history-user@test.com")
    wo = _work_order(db, user)
    for to_status in (
        WorkOrderStatusEnum.assigned,
        WorkOrderStatusEnum.accepted,
        WorkOrderStatusEnum.in_progress,
    ):
        wo.status_history.append(
            WorkOrderStatusHistory(
                from_status=None,
                to_status=to_status.value,
                changed_by=user.id,
                changed_at=datetime.now(UTC),
            )
        )
    db.commit()
    db.refresh(wo)
    assert [h.to_status for h in wo.status_history] == [
        WorkOrderStatusEnum.assigned.value,
        WorkOrderStatusEnum.accepted.value,
        WorkOrderStatusEnum.in_progress.value,
    ]


def test_checklist_items_ordered_by_business_order(db) -> None:
    """检查清单按业务字段 order 排序（既有加固行为的回归锁）。"""
    user = _user(db, "checklist-user@test.com")
    wo = _work_order(db, user)
    for idx, content in ((2, "第三步"), (0, "第一步"), (1, "第二步")):
        db.add(
            WorkOrderChecklistItem(
                work_order_id=wo.id,
                category="repair",
                content=content,
                order=idx,
                is_required=True,
            )
        )
    db.commit()
    db.refresh(wo)
    assert [item.content for item in wo.checklist_items] == [
        "第一步",
        "第二步",
        "第三步",
    ]


def test_knowledge_chunks_ordered_by_chunk_index(db) -> None:
    """RAG 分片按 chunk_index 稳定返回（检索证据顺序可复现）。"""
    article = KnowledgeArticle(
        title="排序测试知识",
        content="正文",
        source="manual",
        status="published",
        view_count=0,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    for idx in (2, 0, 1):
        db.add(
            KnowledgeChunk(
                article_id=article.id,
                content=f"chunk-{idx}",
                chunk_index=idx,
            )
        )
    db.commit()
    db.refresh(article)
    assert [chunk.chunk_index for chunk in article.chunks] == [0, 1, 2]
