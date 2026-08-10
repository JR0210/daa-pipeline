"""Measure volume, PCA length and watertightness for a batch of meshes.

Usage:
    python measure_vol.py --input <folder> [--require-watertight] [--jobs N]

Run once on raw wrapped meshes, and again on decimated output to confirm
decimation did not break watertightness (see README "Order of Operations").
"""

from __future__ import annotations

import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import trimesh

from daa.cli import build_parser, resolve_settings, setup_logging
from daa.naming import UnclassifiedMeshError, parse_specimen
from daa.report import EXIT_ERROR, EXIT_GATE, write_stage_report

logger = logging.getLogger("daa")

RESULT_FIELDS = ["species", "mesh_type", "filename", "volume", "skull_length", "watertight"]
ERROR_FIELDS = ["species", "mesh_type", "filename", "error"]


def measure_one(args: tuple[str, list[str], list[str]]) -> dict:
    """Worker: measure a single mesh. Runs in a subprocess, must be picklable."""
    mesh_path_str, crania_tokens, mandible_tokens = args
    mesh_path = Path(mesh_path_str)
    filename = mesh_path.name

    try:
        specimen = parse_specimen(filename, crania_tokens, mandible_tokens)
    except UnclassifiedMeshError as e:
        return {
            "ok": False,
            "species": "",
            "mesh_type": "",
            "filename": filename,
            "error": str(e),
        }

    try:
        mesh = trimesh.load(mesh_path, force="mesh")

        if mesh.is_empty:
            raise ValueError("Mesh is empty")

        watertight = mesh.is_watertight
        volume = mesh.volume if watertight else float("nan")

        vertices = mesh.vertices
        if len(vertices) < 3:
            raise ValueError("Mesh contains fewer than 3 vertices")

        v_centered = vertices - vertices.mean(axis=0)
        _, _, vt = np.linalg.svd(v_centered, full_matrices=False)
        main_axis = vt[0]
        projections = v_centered @ main_axis
        skull_length = projections.max() - projections.min()

        return {
            "ok": True,
            "species": specimen.genus_species,
            "mesh_type": specimen.part,
            "filename": filename,
            "volume": volume,
            "skull_length": skull_length,
            "watertight": watertight,
        }

    except Exception as e:  # noqa: BLE001 - reported per-mesh, not fatal to the batch
        return {
            "ok": False,
            "species": specimen.genus_species,
            "mesh_type": specimen.part,
            "filename": filename,
            "error": f"{type(e).__name__}: {e}",
        }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(
        "Measure mesh volume, length and watertightness for a batch of PLY meshes."
    )
    parser.add_argument(
        "--require-watertight",
        action="store_true",
        help="Exit with code 2 (gate) if any mesh is not watertight.",
    )
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    settings = resolve_settings(args)
    input_dir = Path(args.input) if args.input else settings.stage_dir("raw")

    print("=" * 60)
    print("MESH BATCH PROCESSING")
    print("=" * 60)
    print(f"\nMesh folder:\n{input_dir}")

    if not input_dir.is_dir():
        logger.error("Mesh folder does not exist: %s", input_dir)
        return EXIT_ERROR

    mesh_files = sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".ply")
    print(f"\nPLY files found: {len(mesh_files)}")

    if args.dry_run:
        for p in mesh_files:
            print(f"  would measure: {p.name}")
        return 0

    results: list[dict] = []
    errors: list[dict] = []

    worker_args = [
        (str(p), settings.crania_tokens, settings.mandible_tokens) for p in mesh_files
    ]

    with ProcessPoolExecutor(max_workers=max(1, settings.jobs)) as pool:
        futures = [pool.submit(measure_one, wa) for wa in worker_args]
        for future in as_completed(futures):
            outcome = future.result()
            ok = outcome.pop("ok")
            if ok:
                results.append(outcome)
                print(f"  OK: {outcome['filename']}")
            else:
                errors.append(outcome)
                print(f"  ERROR: {outcome['filename']}: {outcome.get('error')}")

    results.sort(key=lambda r: r["filename"])
    errors.sort(key=lambda r: r["filename"])

    exit_code = write_stage_report(
        settings.reports_dir(),
        "measure_vol",
        results,
        errors,
        RESULT_FIELDS,
        ERROR_FIELDS,
    )

    print("\n" + "=" * 60)
    print("BATCH PROCESSING COMPLETE")
    print("=" * 60)
    print(f"PLY files found:       {len(mesh_files)}")
    print(f"Successful meshes:     {len(results)}")
    print(f"Errored meshes:        {len(errors)}")

    non_watertight = [r for r in results if not r["watertight"]]
    if args.require_watertight and non_watertight:
        print(f"\nNon-watertight meshes ({len(non_watertight)}):")
        for r in non_watertight:
            print(f"  {r['filename']}")
        return EXIT_GATE

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
