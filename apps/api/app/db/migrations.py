"""Small, idempotent schema upgrades for databases created before Alembic was configured."""

from __future__ import annotations

from sqlalchemy import Engine, inspect, text

_CHECKLIST_CATEGORIES = {
    "safety": [
        "设备已停机",
        "相关能源已切断",
        "已执行上锁挂牌（LOTO）",
        "残余能量已释放",
        "安全联锁状态已确认",
        "现场警示已设置",
        "个人防护用品已佩戴",
        "确认设备已停机",
        "执行断电操作",
        "执行上锁挂牌（LOTO）",
        "确认残余能量已释放",
    ],
    "diagnosis": ["读取并记录故障代码", "检查相关部件状态"],
    "testing": ["空载测试", "负载测试", "确认设备恢复正常"],
}


def upgrade_schema(engine: Engine) -> list[str]:
    """Apply backward-compatible upgrades and return the applied migration names."""
    inspector = inspect(engine)
    if "work_order_checklist_items" not in inspector.get_table_names():
        return []

    applied: list[str] = []
    columns = {
        column["name"] for column in inspector.get_columns("work_order_checklist_items")
    }

    with engine.begin() as connection:
        if "category" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE work_order_checklist_items "
                    "ADD COLUMN category VARCHAR(32) NOT NULL DEFAULT 'repair'"
                )
            )
            applied.append("work_order_checklist_items.category")

        backfilled = False
        for category, contents in _CHECKLIST_CATEGORIES.items():
            for content in contents:
                result = connection.execute(
                    text(
                        "UPDATE work_order_checklist_items "
                        "SET category = :category "
                        "WHERE content = :content AND category = 'repair'"
                    ),
                    {"category": category, "content": content},
                )
                backfilled = bool(result.rowcount) or backfilled
        if backfilled:
            applied.append("work_order_checklist_items.category_backfill")

    return applied
