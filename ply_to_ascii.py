# Paper - Comparing landmark-free and manual landmarking methods for macroevolutionary studies using the mammalian crania
# Original author: James M. Mulqueeney

"""Batch-convert binary PLY meshes to ASCII PLY (x/y/z vertices + face lists).

Usage:
    python ply_to_ascii.py --part both [--jobs N] [--overwrite]

Uses plyfile's own ASCII serialisation rather than hand-rolled string
formatting, so faces of any arity (not just triangles) are written with
the correct list-length prefix.
"""

from __future__ import annotations

import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from plyfile import PlyData, PlyElement

from daa.cli import build_parser, parts_to_process, resolve_settings, setup_logging
from daa.report import write_stage_report

logger = logging.getLogger("daa")

RESULT_FIELDS = ["filename", "vertices", "faces"]
ERROR_FIELDS = ["filename", "error"]


def convert_to_ascii(input_path: Path, output_path: Path) -> tuple[int, int]:
    """Convert a single PLY file (binary or ASCII) to ASCII, x/y/z + faces only."""
    plydata = PlyData.read(str(input_path))

    vertex_src = plydata["vertex"].data
    vertex_data = np.empty(len(vertex_src), dtype=[("x", "f4"), ("y", "f4"), ("z", "f4")])
    vertex_data["x"] = vertex_src["x"]
    vertex_data["y"] = vertex_src["y"]
    vertex_data["z"] = vertex_src["z"]
    vertex_element = PlyElement.describe(vertex_data, "vertex")

    face_src = plydata["face"].data
    face_prop_name = face_src.dtype.names[0]
    face_data = np.empty(len(face_src), dtype=[("vertex_indices", "O")])
    for i, row in enumerate(face_src[face_prop_name]):
        face_data["vertex_indices"][i] = np.asarray(row, dtype="i4")
    face_element = PlyElement.describe(
        face_data,
        "face",
        len_types={"vertex_indices": "u1"},
        val_types={"vertex_indices": "i4"},
    )

    PlyData([vertex_element, face_element], text=True).write(str(output_path))

    return len(vertex_src), len(face_src)


def convert_one(job: tuple[str, str]) -> dict:
    """Worker: convert a single mesh. Runs in a subprocess."""
    input_path_str, output_path_str = job
    input_path = Path(input_path_str)
    output_path = Path(output_path_str)
    try:
        n_vertices, n_faces = convert_to_ascii(input_path, output_path)
        return {"ok": True, "filename": input_path.name, "vertices": n_vertices, "faces": n_faces}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "filename": input_path.name, "error": f"{type(e).__name__}: {e}"}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser("Batch-convert binary PLY meshes to ASCII PLY.")
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    settings = resolve_settings(args)
    parts = parts_to_process(args)

    jobs: list[tuple[str, str]] = []
    skipped: list[dict] = []

    for part in parts:
        input_dir = Path(args.input) if args.input else settings.stage_dir("decimated", part)
        output_dir = Path(args.output) if args.output else settings.stage_dir("ascii", part)

        if not input_dir.is_dir():
            logger.warning("Input folder does not exist, skipping part %s: %s", part, input_dir)
            continue

        output_dir.mkdir(parents=True, exist_ok=True)

        mesh_files = sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".ply")
        logger.info("[%s] PLY files found: %d", part, len(mesh_files))

        for mesh_path in mesh_files:
            output_path = output_dir / mesh_path.name
            if output_path.exists() and not args.overwrite:
                skipped.append({"filename": mesh_path.name, "vertices": "", "faces": ""})
                continue
            if args.dry_run:
                print(f"  would convert: {mesh_path} -> {output_path}")
                continue
            jobs.append((str(mesh_path), str(output_path)))

    if args.dry_run:
        return 0

    results: list[dict] = list(skipped)
    errors: list[dict] = []

    if jobs:
        with ProcessPoolExecutor(max_workers=max(1, settings.jobs)) as pool:
            futures = [pool.submit(convert_one, job) for job in jobs]
            for future in as_completed(futures):
                outcome = future.result()
                ok = outcome.pop("ok")
                if ok:
                    results.append(outcome)
                    logger.info("Converted: %s", outcome["filename"])
                else:
                    errors.append(outcome)
                    logger.error("Failed: %s: %s", outcome["filename"], outcome["error"])

    results.sort(key=lambda r: r["filename"])
    errors.sort(key=lambda r: r["filename"])

    return write_stage_report(
        settings.reports_dir(),
        "ply_to_ascii",
        results,
        errors,
        RESULT_FIELDS,
        ERROR_FIELDS,
    )


if __name__ == "__main__":
    sys.exit(main())
