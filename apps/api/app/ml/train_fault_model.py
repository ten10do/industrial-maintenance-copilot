"""CLI for Paderborn failure-risk or fault-classification experiments."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from app.ml.training import TaskType, safe_summary, train_from_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["paderborn", "xjtu-sy"], required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--task",
        choices=["failure_risk", "fault_classification"],
        default="fault_classification",
    )
    args = parser.parse_args()
    outcome = train_from_config(
        dataset_name=str(args.dataset),
        config_path=cast(Path, args.config),
        expected_task=cast(TaskType, args.task),
    )
    print(safe_summary(outcome, str(args.dataset)))


if __name__ == "__main__":
    main()
