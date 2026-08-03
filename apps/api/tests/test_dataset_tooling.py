"""Tests for official bearing dataset download and audit tooling."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import httpx
import numpy as np
import pytest
from scipy.io import savemat

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from audit_bearing_dataset import audit_paderborn, audit_xjtu  # noqa: E402
from download_paderborn_dataset import (  # noqa: E402
    EXPECTED_BEARINGS,
    download_file,
    parse_official_listing,
    verify_official_listing,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_paderborn_listing_requires_the_exact_official_archive_set() -> None:
    listing = "\n".join(
        f'<a href="{bearing_id}.rar">{bearing_id}</a>'
        for bearing_id in reversed(EXPECTED_BEARINGS)
    )

    parsed = parse_official_listing(listing)

    verify_official_listing(parsed)
    assert set(parsed) == set(EXPECTED_BEARINGS)


def test_paderborn_download_resumes_to_an_atomic_destination(tmp_path: Path) -> None:
    destination = tmp_path / "K001.rar"
    partial = tmp_path / "K001.rar.partial"
    partial.write_bytes(b"first-")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Range"] == "bytes=6-"
        return httpx.Response(206, content=b"second", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        record = download_file(
            client,
            "https://example.test/K001.rar",
            destination,
            retries=1,
        )

    assert destination.read_bytes() == b"first-second"
    assert not partial.exists()
    assert record["download_complete"] is True
    assert record["resumed"] is True
    assert record["sha256"] == _sha256(destination)


def test_paderborn_download_rejects_an_existing_checksum_mismatch(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "K001.rar"
    destination.write_bytes(b"changed")

    with (
        httpx.Client(transport=httpx.MockTransport(lambda request: None)) as client,
        pytest.raises(RuntimeError, match="differs from its checksum manifest"),
    ):
        download_file(
            client,
            "https://example.test/K001.rar",
            destination,
            retries=1,
            existing_record={"size_bytes": 3, "sha256": "not-the-current-hash"},
        )


def test_paderborn_audit_accepts_complete_traceable_fixture(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    archive = raw_dir / "_archives" / "K001.rar"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"official-archive-fixture")
    mat_path = raw_dir / "K001" / "N15_M07_F10_K001_1.mat"
    mat_path.parent.mkdir(parents=True)
    savemat(mat_path, {"vibration": np.arange(16, dtype=np.float64)})

    labels = tmp_path / "labels.csv"
    fields = [
        "bearing_id",
        "fault_class",
        "condition_group",
        "damage_origin",
        "fault_location",
        "fault_type",
        "damage_level",
        "damage_method",
        "source_document",
        "source_table",
        "notes",
    ]
    with labels.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "bearing_id": "K001",
                "fault_class": "healthy",
                "condition_group": "healthy",
                "damage_origin": "healthy",
                "fault_location": "none",
                "fault_type": "none",
                "damage_level": "none",
                "damage_method": "none",
                "source_document": "official paper",
                "source_table": "Table 7",
                "notes": "traceable fixture",
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "download_verified": True,
                "archives": [
                    {
                        "bearing_id": "K001",
                        "size_bytes": archive.stat().st_size,
                        "sha256": _sha256(archive),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = audit_paderborn(
        raw_dir,
        labels,
        manifest,
        expected_bearings=("K001",),
        expected_files_per_bearing=1,
        expected_conditions=("N15_M07_F10",),
    )

    assert result["status"] == "PASS"
    assert result["bearing_count"] == 1
    assert result["archive_validation"]["checksum_status"] == "PASS"


def test_xjtu_audit_accepts_complete_traceable_fixture(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    archive = raw_dir / "_archives" / "XJTU-SY_Bearing_Datasets.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"official-archive-fixture")
    bearing_dir = raw_dir / "35Hz12kN" / "Bearing1_1"
    bearing_dir.mkdir(parents=True)
    for index in (1, 2):
        (bearing_dir / f"{index}.csv").write_text(
            "Horizontal,Vertical\n1.0,2.0\n3.0,4.0\n5.0,6.0\n7.0,8.0\n",
            encoding="utf-8",
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "download_verified": True,
                "archive_name": archive.name,
                "archive_size_bytes": archive.stat().st_size,
                "sha256": _sha256(archive),
            }
        ),
        encoding="utf-8",
    )

    result = audit_xjtu(
        raw_dir,
        manifest,
        expected_bearings=("Bearing1_1",),
        expected_samples=4,
    )

    assert result["status"] == "PASS"
    assert result["measurement_files"] == 2
    assert result["run_lengths"]["Bearing1_1"]["failure_endpoint"] == "2.csv"
    assert result["archive_validation"]["checksum_status"] == "PASS"
