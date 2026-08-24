"""对本次升级涉及的 Python 代码执行 Ruff format/lint。"""

from __future__ import annotations

import argparse
import subprocess
import sys

QUALITY_PATHS = ["app", "alembic", "tests", "scripts", "../../scripts"]


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
