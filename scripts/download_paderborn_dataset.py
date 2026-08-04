"""Download the Paderborn bearing archives from the official university host."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

OFFICIAL_INDEX_URL = "https://groups.uni-paderborn.de/kat/BearingDataCenter/"
OFFICIAL_DATASET_PAGE = (
    "https://mb.uni-paderborn.de/en/kat/research/"
    "bearing-datacenter/data-sets-and-download"
)
OFFICIAL_PAPER_URL = (
    "https://mb.uni-paderborn.de/fileadmin-mb/kat/PDF/"
    "Veroeffentlichungen/20160703_PHME16_CM_bearing.pdf"
)
EXPECTED_BEARINGS = (
    "K001",
    "K002",
    "K003",
    "K004",
    "K005",
    "K006",
    "KA01",
    "KA03",
    "KA04",
    "KA05",
    "KA06",
    "KA07",
    "KA08",
    "KA09",
    "KA15",
    "KA16",
    "KA22",
    "KA30",
    "KB23",
    "KB24",
    "KB27",
    "KI01",
    "KI03",
    "KI04",
    "KI05",
    "KI07",
    "KI08",
    "KI14",
    "KI16",
    "KI17",
    "KI18",
    "KI21",
)
METADATA_FILES = {
    "readme_versions.txt": urljoin(OFFICIAL_INDEX_URL, "readme_versions.txt"),
    "bearing-dataset-paper.pdf": OFFICIAL_PAPER_URL,
    "dataset-page.html": OFFICIAL_DATASET_PAGE,
    "bearing-damage.html": (
        "https://mb.uni-paderborn.de/en/kat/research/bearing-datacenter/bearing-damage"
    ),
    "operating-conditions.html": (
        "https://mb.uni-paderborn.de/en/kat/research/"
        "bearing-datacenter/operating-conditions"
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_official_listing(html: str) -> tuple[str, ...]:
    names = {
        match.group(1).upper()
        for match in re.finditer(
            r'href=["\']([A-Za-z0-9]+)\.rar["\']', html, flags=re.IGNORECASE
        )
    }
    return tuple(sorted(names))


def verify_official_listing(found: tuple[str, ...]) -> None:
    expected = set(EXPECTED_BEARINGS)
    actual = set(found)
    if actual != expected:
        raise RuntimeError(
            "official Paderborn archive list changed; "
            f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
        )


def download_file(
    client: httpx.Client,
    url: str,
    destination: Path,
    *,
    retries: int,
    existing_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        record = _file_record(destination, url, resumed=False, reused=True)
        if existing_record is not None and (
            record["sha256"] != existing_record.get("sha256")
            or record["size_bytes"] != existing_record.get("size_bytes")
        ):
            raise RuntimeError(
                f"existing file differs from its checksum manifest: {destination}"
            )
        return record
    partial = destination.with_name(f"{destination.name}.partial")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resumed = _download_once(client, url, partial)
            partial.replace(destination)
            return _file_record(destination, url, resumed=resumed, reused=False)
        except (httpx.HTTPError, OSError, RuntimeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(2**attempt, 8))
    raise RuntimeError(
        f"download failed after {retries} attempts: {url}"
    ) from last_error


def _download_once(client: httpx.Client, url: str, partial: Path) -> bool:
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with client.stream("GET", url, headers=headers) as response:
        if response.status_code not in {200, 206}:
            raise RuntimeError(
                f"unexpected HTTP {response.status_code} while downloading {url}"
            )
        resumed = offset > 0 and response.status_code == 206
        mode = "ab" if resumed else "wb"
        with partial.open(mode) as stream:
            for chunk in response.iter_raw(64 * 1024):
                stream.write(chunk)
    if not partial.exists() or partial.stat().st_size == 0:
        raise RuntimeError(f"empty response while downloading {url}")
    return resumed


def _file_record(
    path: Path, url: str, *, resumed: bool, reused: bool
) -> dict[str, Any]:
    return {
        "name": path.name,
        "source_url": url,
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "download_complete": True,
        "resumed": resumed,
        "reused_existing": reused,
    }


def write_manifest(
    path: Path,
    archives: list[dict[str, Any]],
    metadata: list[dict[str, Any]],
) -> None:
    archive_ids = {str(item["bearing_id"]) for item in archives}
    payload = {
        "dataset": "paderborn",
        "source": OFFICIAL_INDEX_URL,
        "dataset_page": OFFICIAL_DATASET_PAGE,
        "license": "CC BY-NC 4.0",
        "download_method": "official_static_http",
        "download_verified": archive_ids == set(EXPECTED_BEARINGS),
        "expected_archive_count": len(EXPECTED_BEARINGS),
        "archives": sorted(archives, key=lambda item: str(item["bearing_id"])),
        "metadata": sorted(metadata, key=lambda item: str(item["name"])),
        "extraction": {
            "status": "not_audited",
            "extractor": None,
            "mat_files": 0,
        },
        "updated_at": datetime.now(UTC).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _existing_records(path: Path, key: str) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get(key, [])
    if not isinstance(values, list):
        return {}
    record_key = "bearing_id" if key == "archives" else "name"
    return {
        str(item[record_key]): item
        for item in values
        if isinstance(item, dict) and record_key in item
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("data/raw/paderborn/_archives")
    )
    parser.add_argument(
        "--metadata-output", type=Path, default=Path("data/raw/paderborn/_metadata")
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/manifests/paderborn-real-download.json"),
    )
    parser.add_argument("--bearing", action="append", choices=EXPECTED_BEARINGS)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()
    if args.retries < 1:
        parser.error("--retries must be at least 1")
    timeout = httpx.Timeout(args.timeout, connect=min(args.timeout, 15.0))
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": "industrial-maintenance-research-downloader/1.0"},
    ) as client:
        listing_response = client.get(OFFICIAL_INDEX_URL)
        listing_response.raise_for_status()
        found = parse_official_listing(listing_response.text)
        verify_official_listing(found)
        print(
            json.dumps(
                {
                    "source": OFFICIAL_INDEX_URL,
                    "archive_count": len(found),
                    "bearing_ids": list(found),
                    "official_list_matches_expected": True,
                },
                indent=2,
            )
        )
        if args.list_only:
            return
        archive_records = _existing_records(args.manifest, "archives")
        metadata_records = _existing_records(args.manifest, "metadata")
        for name, url in METADATA_FILES.items():
            metadata_records[name] = download_file(
                client,
                url,
                args.metadata_output / name,
                retries=args.retries,
                existing_record=metadata_records.get(name),
            )
        if not args.metadata_only:
            selected = tuple(args.bearing or EXPECTED_BEARINGS)
            for bearing_id in selected:
                name = f"{bearing_id}.rar"
                record = download_file(
                    client,
                    urljoin(OFFICIAL_INDEX_URL, name),
                    args.output / name,
                    retries=args.retries,
                    existing_record=archive_records.get(bearing_id),
                )
                record["bearing_id"] = bearing_id
                record["archive"] = name
                record["extracted_mat_files"] = 0
                archive_records[bearing_id] = record
                write_manifest(
                    args.manifest,
                    list(archive_records.values()),
                    list(metadata_records.values()),
                )
        write_manifest(
            args.manifest,
            list(archive_records.values()),
            list(metadata_records.values()),
        )


if __name__ == "__main__":
    main()
