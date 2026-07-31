from sqlalchemy import create_engine, inspect, text

from app.db.migrations import upgrade_schema


def test_upgrade_adds_checklist_category_without_losing_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE work_order_checklist_items ("
                "id INTEGER PRIMARY KEY, content VARCHAR(255) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO work_order_checklist_items (id, content) "
                "VALUES (1, 'legacy checklist item'), (2, '负载测试')"
            )
        )

    assert upgrade_schema(engine) == [
        "work_order_checklist_items.category",
        "work_order_checklist_items.category_backfill",
    ]

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("work_order_checklist_items")
    }
    assert "category" in columns
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT content, category FROM work_order_checklist_items "
                "ORDER BY id"
            )
        ).all()
    assert rows == [
        ("legacy checklist item", "repair"),
        ("负载测试", "testing"),
    ]


def test_upgrade_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'current.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE work_order_checklist_items ("
                "id INTEGER PRIMARY KEY, content VARCHAR(255) NOT NULL, "
                "category VARCHAR(32) NOT NULL DEFAULT 'repair')"
            )
        )

    assert upgrade_schema(engine) == []
    assert upgrade_schema(engine) == []
