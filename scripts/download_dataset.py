"""Register a user-authorized manual dataset download without redistributing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["paderborn", "xjtu-sy"], required=True)
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    source = args.source_file.resolve()
    if not source.is_file():
        parser.error(f"source file does not exist: {source}")
    dataset_dir = args.raw_root.resolve() / args.dataset
    dataset_dir.mkdir(parents=True, exist_ok=True)
    destination = dataset_dir / source.name
    if destination.exists():
        parser.error(f"destination already exists: {destination}")
    shutil.copy2(source, destination)
    receipt = {
        "dataset_name": args.dataset,
        "source_manifest": f"data/manifests/{args.dataset.replace('-', '_')}_bearing_v1.json",
        "registered_at": datetime.now(UTC).isoformat(),
        "local_filename": source.name,
        "size_bytes": destination.stat().st_size,
        "sha256": sha256(destination),
    }
    (dataset_dir / "local-download-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
