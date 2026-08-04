"""CLI for XJTU-SY run-to-failure RUL experiments."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from app.ml.training import TaskType, safe_summary, train_from_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["xjtu-sy"], required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    outcome = train_from_config(
        dataset_name=str(args.dataset),
        config_path=cast(Path, args.config),
        expected_task=cast(TaskType, "rul"),
    )
    print(safe_summary(outcome, str(args.dataset)))


if __name__ == "__main__":
    main()
