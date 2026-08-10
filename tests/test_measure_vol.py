import logging

import pytest

import measure_vol
from tests.fixtures import make_tetrahedron_ply


def test_raw_stage_falls_back_to_data_root_when_01_raw_is_absent(tmp_path, caplog):
    # The exact scenario reported: DATA_ROOT pointed straight at an existing
    # mesh folder, no 01_raw subfolder ever created.
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True)
    make_tetrahedron_ply(data_root / "Testus_syntheticus crania_wrapped.ply")

    with caplog.at_level(logging.INFO):
        exit_code = measure_vol.main(["--data-root", str(data_root), "--jobs", "1"])

    assert exit_code == 0, caplog.text
    assert "not found -- using" in caplog.text

    metrics = (data_root / "_reports" / "measure_vol_metrics.csv").read_text(encoding="utf-8")
    assert "Testus_syntheticus crania_wrapped.ply" in metrics


def test_raw_stage_prefers_01_raw_when_it_exists(tmp_path):
    data_root = tmp_path / "data"
    raw_dir = data_root / "01_raw"
    raw_dir.mkdir(parents=True)
    make_tetrahedron_ply(raw_dir / "Testus_syntheticus crania_wrapped.ply")

    # A loose .ply directly in data_root too -- must be ignored, since
    # 01_raw exists and takes priority.
    make_tetrahedron_ply(data_root / "Should_not_be_seen crania_wrapped.ply")

    exit_code = measure_vol.main(["--data-root", str(data_root), "--jobs", "1"])
    assert exit_code == 0

    metrics = (data_root / "_reports" / "measure_vol_metrics.csv").read_text(encoding="utf-8")
    assert "Testus_syntheticus crania_wrapped.ply" in metrics
    assert "Should_not_be_seen" not in metrics


def test_raw_stage_with_nothing_present_gives_actionable_error(tmp_path, caplog):
    data_root = tmp_path / "data"

    with caplog.at_level(logging.ERROR):
        exit_code = measure_vol.main(["--data-root", str(data_root), "--jobs", "1"])

    assert exit_code == measure_vol.EXIT_ERROR
    assert "Copy your wrapped .ply files directly into" in caplog.text
    assert "01_raw" in caplog.text


def test_decimated_stage_actually_scans_decimated_output_not_raw(tmp_path):
    # Regression test for the bug where --stage/--part were accepted but
    # never used: measure_vol_decimated was silently re-measuring 01_raw
    # instead of 02_decimated, so the watertightness gate never actually
    # checked decimated output.
    data_root = tmp_path / "data"
    raw_dir = data_root / "01_raw"
    raw_dir.mkdir(parents=True)
    make_tetrahedron_ply(raw_dir / "Raw_only_mesh crania_wrapped.ply")

    crania_dir = data_root / "02_decimated" / "crania"
    mandible_dir = data_root / "02_decimated" / "mandible"
    crania_dir.mkdir(parents=True)
    mandible_dir.mkdir(parents=True)
    make_tetrahedron_ply(crania_dir / "Testus_syntheticus_crania_dec.ply")
    make_tetrahedron_ply(mandible_dir / "Testus_syntheticus_mandible_dec.ply")

    exit_code = measure_vol.main(
        ["--data-root", str(data_root), "--stage", "decimated", "--part", "both", "--jobs", "1"]
    )
    assert exit_code == 0

    metrics = (data_root / "_reports" / "measure_vol_metrics.csv").read_text(encoding="utf-8")
    assert "Testus_syntheticus_crania_dec.ply" in metrics
    assert "Testus_syntheticus_mandible_dec.ply" in metrics
    assert "Raw_only_mesh" not in metrics


def test_decimated_stage_with_no_decimated_output_gives_actionable_error(tmp_path, caplog):
    data_root = tmp_path / "data"

    with caplog.at_level(logging.ERROR):
        exit_code = measure_vol.main(
            ["--data-root", str(data_root), "--stage", "decimated", "--part", "both", "--jobs", "1"]
        )

    assert exit_code == measure_vol.EXIT_ERROR
    assert "Run decimate.py first" in caplog.text
