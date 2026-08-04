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

import prepare_bearing_dataset as dataset_preparation  # noqa: E402
from audit_bearing_dataset import (  # noqa: E402
    audit_paderborn,
    audit_xjtu,
    record_paderborn_extraction,
)
from audit_ml_leakage import audit_processed_dataset  # noqa: E402
from create_dataset_snapshot import create_snapshot  # noqa: E402
from download_paderborn_dataset import (  # noqa: E402
    EXPECTED_BEARINGS,
    download_file,
    parse_official_listing,
    verify_official_listing,
)
from prepare_bearing_dataset import ProcessedRow, write_processed  # noqa: E402


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
        return httpx.Response(
            206,
            stream=httpx.ByteStream(b"second"),
            request=request,
        )

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


def test_paderborn_channel_falls_back_to_strict_mat5_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "fixture.mat"
    channels = np.empty((1, 1), dtype=[("Name", "O"), ("Data", "O"), ("Unit", "O")])
    channels["Name"][0, 0] = "vibration_1"
    channels["Data"][0, 0] = np.asarray([1.0, -2.0, 3.5])
    channels["Unit"][0, 0] = "m/s2"
    root = np.empty((1, 1), dtype=[("Y", "O")])
    root["Y"][0, 0] = channels
    savemat(path, {path.stem: root}, do_compression=False)

    def fail_general_decode(*args: object, **kwargs: object) -> None:
        raise TypeError("fixture general-reader failure")

    monkeypatch.setattr(dataset_preparation, "loadmat", fail_general_decode)

    signal = dataset_preparation._load_paderborn_channel(path, "vibration_1")

    np.testing.assert_array_equal(signal, np.asarray([1.0, -2.0, 3.5]))


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
    record_paderborn_extraction(manifest, result, extractor="7-Zip test")
    recorded = json.loads(manifest.read_text(encoding="utf-8"))
    assert recorded["archives"][0]["extracted_mat_files"] == 1
    assert recorded["extraction"]["mat_files"] == 1
    assert recorded["extraction"]["status"] == "verified"


def test_xjtu_audit_accepts_complete_traceable_fixture(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    archive = raw_dir / "_archives" / "XJTU-SY_Bearing_Datasets.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"official-archive-fixture")
    bearing_dir = raw_dir / "35Hz12kN" / "Bearing1_1"
    bearing_dir.mkdir(parents=True)
    for index in (1, 2):
        (bearing_dir / f"{index}.csv").write_text(
            f"Horizontal,Vertical\n{index}.0,2.0\n3.0,4.0\n5.0,6.0\n7.0,8.0\n",
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


def test_xjtu_audit_rejects_non_finite_measurements(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    archive = raw_dir / "_archives" / "part01.rar"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"official-archive-fixture")
    bearing_dir = raw_dir / "35Hz12kN" / "Bearing1_1"
    bearing_dir.mkdir(parents=True)
    (bearing_dir / "1.csv").write_text("1.0,nan\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "download_verified": True,
                "archive_format": "multipart_rar",
                "archive_size_bytes": archive.stat().st_size,
                "archive_parts": [
                    {
                        "path": "_archives/part01.rar",
                        "size_bytes": archive.stat().st_size,
                        "sha256": _sha256(archive),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = audit_xjtu(
        raw_dir,
        manifest,
        expected_bearings=("Bearing1_1",),
        expected_samples=1,
    )

    assert result["status"] == "FAIL"
    assert "non-finite numeric value" in result["malformed_csv"][0]


def test_snapshot_version_and_processed_lineage_are_deterministic(
    tmp_path: Path,
) -> None:
    template = tmp_path / "template.json"
    template.write_text(
        json.dumps(
            {
                "source_url": "https://example.test/official",
                "license": "research only",
                "citation": "fixture",
                "processed_version": "bearing-processed-v1",
            }
        ),
        encoding="utf-8",
    )
    download = tmp_path / "download.json"
    download.write_text(
        json.dumps(
            {
                "archives": [
                    {
                        "archive": f"K{index:03d}.rar",
                        "sha256": f"{index:064x}",
                        "size_bytes": index,
                    }
                    for index in range(1, 33)
                ]
            }
        ),
        encoding="utf-8",
    )
    split = tmp_path / "paderborn-split-v1.json"
    split.write_text(
        json.dumps(
            {
                "train": [f"bearing-{index}" for index in range(20)],
                "validation": [f"bearing-{index}" for index in range(20, 26)],
                "test": [f"bearing-{index}" for index in range(26, 32)],
            }
        ),
        encoding="utf-8",
    )
    config = tmp_path / "fault.yaml"
    config.write_text(
        """split:\n  strategy: locked_group_manifest\n  manifest: paderborn-split-v1.json\npreprocessing:\n  fit_split: train\nselection_split: validation\ntest_usage: final_selected_model_evaluation_once\n""",
        encoding="utf-8",
    )

    first = create_snapshot(
        dataset="paderborn",
        template_path=template,
        download_manifest_path=download,
        split_manifest_path=split,
        processing_config_path=config,
        git_sha="a" * 40,
    )
    second = create_snapshot(
        dataset="paderborn",
        template_path=template,
        download_manifest_path=download,
        split_manifest_path=split,
        processing_config_path=config,
        git_sha="b" * 40,
    )

    assert first["version"] == second["version"]
    assert first["git_sha"] != second["git_sha"]
    assert first["bearing_count"] == 32

    dataset_manifest = tmp_path / "dataset.json"
    dataset_manifest.write_text(json.dumps(first), encoding="utf-8")
    output = tmp_path / "processed.npz"
    rows = [
        ProcessedRow(
            values={"rms": float(index + 1)},
            target="healthy" if index == 0 else "outer_ring",
            sample_id=f"sample-{index}",
            bearing_id=f"bearing-{index}",
            source_file=f"bearing-{index}/source.mat",
            window_index=0,
            split="train" if index == 0 else ("validation" if index == 1 else "test"),
            operating_condition="N15_M07_F10",
            rul_measurements=-1,
            rul_hours=float("nan"),
        )
        for index in range(3)
    ]
    small_split = tmp_path / "small-split.json"
    small_split.write_text(
        json.dumps(
            {
                "train": ["bearing-0"],
                "validation": ["bearing-1"],
                "test": ["bearing-2"],
            }
        ),
        encoding="utf-8",
    )
    small_config = tmp_path / "small-config.yaml"
    small_config.write_text(
        """split:\n  strategy: locked_group_manifest\n  manifest: small-split.json\npreprocessing:\n  fit_split: train\nselection_split: validation\ntest_usage: final_selected_model_evaluation_once\n""",
        encoding="utf-8",
    )
    write_processed(
        rows,
        output,
        "paderborn",
        "fault_classification",
        dataset_version=str(first["version"]),
        dataset_manifest=dataset_manifest,
        split_manifest=small_split,
        chunk_rows=1,
        processing_config={"trend_policy": "backward_only"},
    )

    audit = audit_processed_dataset(
        output,
        small_split,
        small_config,
        require_future_consistency=False,
    )

    assert audit["status"] == "PASS"
    assert audit["identity_leakage_check_passed"] is True
    assert audit["source_leakage_check_passed"] is True
    with np.load(output, allow_pickle=False) as payload:
        assert payload["sample_ids"].tolist() == ["sample-0", "sample-1", "sample-2"]
