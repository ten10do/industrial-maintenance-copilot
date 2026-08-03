"""Create immutable dataset-version manifests from verified downloads and config."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["paderborn", "xjtu-sy"], required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--download-manifest", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--processing-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = create_snapshot(
        dataset=args.dataset,
        template_path=args.template,
        download_manifest_path=args.download_manifest,
        split_manifest_path=args.split_manifest,
        processing_config_path=args.processing_config,
        git_sha=_git_sha(),
    )
    temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
    temporary.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(
        json.dumps({"version": snapshot["version"], "output": args.output.as_posix()})
    )


def create_snapshot(
    *,
    dataset: str,
    template_path: Path,
    download_manifest_path: Path,
    split_manifest_path: Path,
    processing_config_path: Path,
    git_sha: str,
) -> dict[str, Any]:
    template = _read_json(template_path)
    download = _read_json(download_manifest_path)
    split = _read_json(split_manifest_path)
    processing_bytes = processing_config_path.read_bytes()
    version_input = {
        "download_manifest": download,
        "processing_config_sha256": hashlib.sha256(processing_bytes).hexdigest(),
    }
    digest = hashlib.sha256(
        json.dumps(version_input, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    archives = _archive_records(download)
    aggregate_hash = hashlib.sha256(
        "\n".join(
            f"{item['name']}:{item['sha256']}:{item['size_bytes']}" for item in archives
        ).encode()
    ).hexdigest()
    raw_files = 2560 if dataset == "paderborn" else 9216
    bearing_count = 32 if dataset == "paderborn" else 15
    expected_groups = {
        str(group)
        for name in ("train", "validation", "test")
        for group in split.get(name, [])
    }
    if len(expected_groups) != bearing_count:
        raise ValueError("split manifest bearing count does not match dataset snapshot")
    return {
        **template,
        "dataset_name": dataset,
        "version": f"{dataset}-snapshot-{digest[:16]}",
        "version_derivation": "sha256(verified download manifest + processing config)",
        "version_digest": digest,
        "downloaded_at": download.get("updated_at"),
        "sha256": aggregate_hash,
        "archive_hashes": archives,
        "raw_files": raw_files,
        "bearing_count": bearing_count,
        "feature_schema_version": "bearing-features-v1",
        "processing_config": processing_config_path.as_posix(),
        "processing_config_sha256": hashlib.sha256(processing_bytes).hexdigest(),
        "split_manifest": split_manifest_path.as_posix(),
        "split_manifest_sha256": _sha256(split_manifest_path),
        "download_manifest": download_manifest_path.as_posix(),
        "download_manifest_sha256": _sha256(download_manifest_path),
        "git_sha": git_sha,
        "snapshot_created_at": datetime.now(UTC).isoformat(),
    }


def _archive_records(download: dict[str, Any]) -> list[dict[str, Any]]:
    values = download.get("archives", download.get("archive_parts", []))
    if not isinstance(values, list) or not values:
        raise ValueError("verified download manifest has no archive records")
    records: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            raise TypeError("archive record must be an object")
        name = str(item.get("archive", item.get("name", "")))
        sha = str(item.get("sha256", ""))
        size = item.get("size_bytes")
        if not name or len(sha) != 64 or not isinstance(size, int):
            raise ValueError("archive record is missing name, size, or SHA256")
        records.append({"name": name, "size_bytes": size, "sha256": sha})
    return sorted(records, key=lambda item: str(item["name"]))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


if __name__ == "__main__":
    main()
