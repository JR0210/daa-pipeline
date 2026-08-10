# Paper - Assessing the application of landmark-free morphometrics to macroevolutionary analyses

"""Batch-convert aligned PLY meshes to VTK PolyData format.

Usage:
    python ply_to_vtk.py --part both [--jobs N] [--overwrite]
"""

from __future__ import annotations

import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from daa.cli import build_parser, parts_to_process, resolve_settings, setup_logging
from daa.report import write_stage_report

logger = logging.getLogger("daa")

RESULT_FIELDS = ["filename", "output_filename"]
ERROR_FIELDS = ["filename", "error"]


def convert_one(job: tuple[str, str]) -> dict:
    """Worker: convert a single PLY to VTK. Runs in a subprocess."""
    import vtk

    input_path_str, output_path_str = job
    input_path = Path(input_path_str)
    output_path = Path(output_path_str)

    try:
        reader = vtk.vtkPLYReader()
        reader.SetFileName(str(input_path))
        reader.Update()
        polydata = reader.GetOutput()

        writer = vtk.vtkPolyDataWriter()
        writer.SetFileName(str(output_path))
        writer.SetInputData(polydata)
        writer.Write()

        return {"ok": True, "filename": input_path.name, "output_filename": output_path.name}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "filename": input_path.name, "error": f"{type(e).__name__}: {e}"}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser("Batch-convert PLY meshes to VTK PolyData format.")
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    settings = resolve_settings(args)
    parts = parts_to_process(args)

    jobs: list[tuple[str, str]] = []
    skipped: list[dict] = []

    for part in parts:
        input_dir = Path(args.input) if args.input else settings.stage_dir("aligned", part)
        output_dir = Path(args.output) if args.output else settings.stage_dir("vtk", part)

        if not input_dir.is_dir():
            logger.warning("Input folder does not exist, skipping part %s: %s", part, input_dir)
            continue

        output_dir.mkdir(parents=True, exist_ok=True)

        mesh_files = sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".ply")
        logger.info("[%s] PLY files found: %d", part, len(mesh_files))

        for mesh_path in mesh_files:
            output_path = output_dir / (mesh_path.stem + ".vtk")
            if output_path.exists() and not args.overwrite:
                skipped.append({"filename": mesh_path.name, "output_filename": output_path.name})
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
                    logger.info("Converted: %s -> %s", outcome["filename"], outcome["output_filename"])
                else:
                    errors.append(outcome)
                    logger.error("Failed: %s: %s", outcome["filename"], outcome["error"])

    results.sort(key=lambda r: r["filename"])
    errors.sort(key=lambda r: r["filename"])

    return write_stage_report(
        settings.reports_dir(),
        "ply_to_vtk",
        results,
        errors,
        RESULT_FIELDS,
        ERROR_FIELDS,
    )


if __name__ == "__main__":
    sys.exit(main())
