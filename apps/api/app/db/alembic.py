"""应用内 Alembic 升级入口与版本就绪检查。"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text

from alembic import command

_API_ROOT = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    config = Config(str(_API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_API_ROOT / "alembic"))
    return config


def upgrade_database(engine: Engine) -> None:
    config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def current_revision(engine: Engine) -> str | None:
    if "alembic_version" not in inspect(engine).get_table_names():
        return None
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()


def database_is_at_head(engine: Engine) -> bool:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    return current_revision(engine) == head


def ensure_database_at_head(engine: Engine, *, auto_migrate: bool) -> None:
    if auto_migrate:
        upgrade_database(engine)
        return
    if database_is_at_head(engine):
        return
    current = current_revision(engine) or "unversioned"
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    raise RuntimeError(
        f"数据库迁移版本不是 head（current={current}, head={head}）；"
        "请在部署阶段先执行 alembic upgrade head"
    )
