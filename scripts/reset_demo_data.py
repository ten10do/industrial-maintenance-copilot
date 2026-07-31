"""Rebuild the public demo dataset without dropping database objects."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: E402, F401
from app.core.config import settings  # noqa: E402
from app.db.session import Base, engine  # noqa: E402
from app.seed import _seed  # noqa: E402


def reset_demo_data() -> None:
    tables = list(Base.metadata.sorted_tables)
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            formatter = connection.dialect.identifier_preparer
            names = ", ".join(formatter.format_table(table) for table in tables)
            connection.exec_driver_sql(
                f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"
            )
        else:
            for table in reversed(tables):
                connection.execute(table.delete())
            if (
                connection.dialect.name == "sqlite"
                and "sqlite_sequence" in inspect(connection).get_table_names()
            ):
                connection.execute(text("DELETE FROM sqlite_sequence"))

        session = Session(bind=connection)
        try:
            _seed(session)
            session.flush()
        finally:
            session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-public-demo-reset",
        action="store_true",
        help="Required acknowledgement that the configured demo database will be reset.",
    )
    args = parser.parse_args()

    if settings.APP_ENV != "demo":
        parser.error("APP_ENV must be 'demo'")
    if not args.confirm_public_demo_reset:
        parser.error("--confirm-public-demo-reset is required")
    if os.getenv("DEMO_RESET_ALLOWED", "").lower() != "true":
        parser.error("DEMO_RESET_ALLOWED=true is required")

    reset_demo_data()
    print("Public demo data reset completed.")


if __name__ == "__main__":
    main()
