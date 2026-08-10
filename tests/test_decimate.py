from pathlib import Path

import decimate
from tests.fixtures import make_tetrahedron_ply


def test_below_threshold_mesh_is_copied_through_with_canonical_name(tmp_path):
    data_root = tmp_path / "data"
    raw_dir = data_root / "01_raw"
    raw_dir.mkdir(parents=True)

    # A 4-face tetrahedron is far below any realistic TARGET_FACES (default
    # 50000), so it should be copied through rather than decimated -- and,
    # before the fix, would have been skipped entirely, leaving the output
    # folder incomplete.
    make_tetrahedron_ply(raw_dir / "Testus_syntheticus mandible_wrapped.ply")

    exit_code = decimate.main(
        ["--data-root", str(data_root), "--part", "mandible", "--jobs", "1"]
    )
    assert exit_code == 0

    output_dir = data_root / "02_decimated" / "mandible"
    output_files = list(output_dir.iterdir())
    assert len(output_files) == 1
    assert output_files[0].name == "Testus_syntheticus_mandible_dec.ply"
