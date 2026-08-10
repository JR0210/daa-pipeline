"""Decimate meshes to a target face count, splitting crania/mandible into
separate output folders with normalised filenames.

Meshes already at or below the target face count are copied through
unchanged (rather than skipped) so the output folder always contains every
input mesh.

Usage:
    python decimate.py --part both [--jobs N] [--overwrite]
"""

from __future__ import annotations

import logging
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from daa.cli import build_parser, parts_to_process, resolve_settings, setup_logging
from daa.naming import UnclassifiedMeshError, canonical_name, parse_specimen
from daa.report import write_stage_report

logger = logging.getLogger("daa")

RESULT_FIELDS = ["species", "mesh_type", "filename", "output_filename", "original_faces", "final_faces", "action"]
ERROR_FIELDS = ["filename", "error"]


def decimate_one(job: tuple[str, str, int]) -> dict:
    """Worker: decimate (or copy through) a single mesh. Runs in a subprocess."""
    import pymeshlab

    input_path_str, output_path_str, target_faces = job
    input_path = Path(input_path_str)
    output_path = Path(output_path_str)

    ms = pymeshlab.MeshSet()
    ms.load_new_mesh(str(input_path))
    mesh = ms.current_mesh()
    face_count = mesh.face_number()

    if face_count <= target_faces:
        shutil.copyfile(input_path, output_path)
        return {
            "ok": True,
            "filename": input_path.name,
            "output_filename": output_path.name,
            "original_faces": face_count,
            "final_faces": face_count,
            "action": "copied",
        }

    ms.meshing_decimation_quadric_edge_collapse(
        targetfacenum=target_faces,
        preservenormal=True,
        preservetopology=False,
        preserveboundary=True,
        optimalplacement=True,
    )
    ms.save_current_mesh(str(output_path))
    final_faces = ms.current_mesh().face_number()

    return {
        "ok": True,
        "filename": input_path.name,
        "output_filename": output_path.name,
        "original_faces": face_count,
        "final_faces": final_faces,
        "action": "decimated",
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(
        "Decimate meshes to a target face count, split by anatomical part."
    )
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    settings = resolve_settings(args)

    if args.input:
        input_dir = Path(args.input)
    else:
        input_dir, note = settings.resolve_raw_input()
        if note:
            logger.info(note)

    if not input_dir.is_dir():
        if args.input:
            logger.error("Input folder does not exist: %s", input_dir)
        else:
            logger.error(
                "No raw meshes found. Either:\n"
                "  1. Copy your wrapped .ply files directly into %s, or\n"
                "  2. Create %s and copy them in there instead\n"
                "  Then re-run. (Or pass --input <folder> to point elsewhere.)",
                settings.data_root, input_dir,
            )
        return 1

    mesh_files = sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".ply")
    logger.info("PLY files found: %d", len(mesh_files))

    parts = set(parts_to_process(args))

    jobs: list[tuple[str, str, int]] = []
    skipped_unclassified: list[dict] = []
    already_done: list[dict] = []

    for mesh_path in mesh_files:
        try:
            specimen = parse_specimen(
                mesh_path.name, settings.crania_tokens, settings.mandible_tokens
            )
        except UnclassifiedMeshError as e:
            skipped_unclassified.append({"filename": mesh_path.name, "error": str(e)})
            continue

        if specimen.part not in parts:
            continue

        if args.output:
            output_dir = Path(args.output)
        else:
            output_dir = settings.stage_dir("decimated", specimen.part)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_name = canonical_name(specimen, "dec", "ply")
        output_path = output_dir / output_name

        if output_path.exists() and not args.overwrite:
            already_done.append(
                {
                    "species": specimen.genus_species,
                    "mesh_type": specimen.part,
                    "filename": mesh_path.name,
                    "output_filename": output_name,
                    "original_faces": "",
                    "final_faces": "",
                    "action": "skipped_existing",
                }
            )
            continue

        if args.dry_run:
            print(f"  would process: {mesh_path.name} -> {output_path}")
            continue

        jobs.append((str(mesh_path), str(output_path), settings.target_faces))

    if args.dry_run:
        return 0

    results: list[dict] = list(already_done)
    errors: list[dict] = list(skipped_unclassified)

    if jobs:
        with ProcessPoolExecutor(max_workers=max(1, settings.jobs)) as pool:
            futures = {pool.submit(decimate_one, job): job for job in jobs}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    outcome = future.result()
                except Exception as e:  # noqa: BLE001
                    errors.append({"filename": Path(job[0]).name, "error": f"{type(e).__name__}: {e}"})
                    continue

                outcome.pop("ok")
                specimen = parse_specimen(
                    outcome["filename"], settings.crania_tokens, settings.mandible_tokens
                )
                outcome = {
                    "species": specimen.genus_species,
                    "mesh_type": specimen.part,
                    **outcome,
                }
                results.append(outcome)
                logger.info(
                    "%s: %s (%s -> %s faces)",
                    outcome["action"],
                    outcome["filename"],
                    outcome["original_faces"],
                    outcome["final_faces"],
                )

    results.sort(key=lambda r: r["filename"])
    errors.sort(key=lambda r: r["filename"])

    return write_stage_report(
        settings.reports_dir(),
        "decimate",
        results,
        errors,
        RESULT_FIELDS,
        ERROR_FIELDS,
    )


if __name__ == "__main__":
    sys.exit(main())
