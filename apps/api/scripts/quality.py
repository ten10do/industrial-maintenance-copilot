"""对本次升级涉及的 Python 代码执行 Ruff format/lint。"""

from __future__ import annotations

import argparse
import subprocess
import sys

QUALITY_PATHS = [
    "app/ai/client.py",
    "app/api/v1/endpoints/equipment.py",
    "app/api/v1/endpoints/intelligence.py",
    "app/api/v1/router.py",
    "app/core/config.py",
    "app/db/migrations.py",
    "app/db/session.py",
    "app/gateways",
    "app/main.py",
    "app/models/__init__.py",
    "app/models/base.py",
    "app/models/equipment.py",
    "app/models/intelligence.py",
    "app/runtime.py",
    "app/schemas/equipment.py",
    "app/schemas/intelligence.py",
    "app/seed.py",
    "app/services/intelligence_service.py",
    "app/services/simulator.py",
    "scripts/quality.py",
    "scripts/verify_migrations.py",
    "tests/test_database_migrations.py",
    "tests/test_intelligent_maintenance.py",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format-only", action="store_true")
    parser.add_argument("--lint-only", action="store_true")
    args = parser.parse_args()
    if args.format_only and args.lint_only:
        parser.error("choose at most one quality phase")
    if not args.lint_only:
        subprocess.run(
            [sys.executable, "-m", "ruff", "format", "--check", *QUALITY_PATHS],
            check=True,
        )
    if not args.format_only:
        subprocess.run(
            [sys.executable, "-m", "ruff", "check", *QUALITY_PATHS],
            check=True,
        )


if __name__ == "__main__":
    main()
