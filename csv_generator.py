# Paper - Assessing the application of landmark-free morphometrics to macroevolutionary analyses

"""Generate the data.csv manifest used to match specimens for kPCA.

Usage:
    python csv_generator.py --part both
"""

from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

from daa.cli import build_parser, parts_to_process, resolve_settings, setup_logging
from daa.naming import UnclassifiedMeshError, parse_specimen

logger = logging.getLogger("daa")

FIELDNAMES = ["filename", "specimen_id", "genus", "species", "part"]


def build_rows(vtk_filenames: list[str], part: str, crania_tokens: list[str], mandible_tokens: list[str]) -> list[dict]:
    rows = []
    for filename in vtk_filenames:
        try:
            specimen = parse_specimen(filename, crania_tokens, mandible_tokens)
            genus_species_parts = specimen.genus_species.split("_", 1)
            genus = genus_species_parts[0]
            species = genus_species_parts[1] if len(genus_species_parts) > 1 else ""
            specimen_id = specimen.genus_species
        except UnclassifiedMeshError:
            # Manifest filenames may already be part-agnostic (e.g. canonical
            # VTK names include the part token, but fall back gracefully if not).
            specimen_id = Path(filename).stem
            genus, species = specimen_id, ""

        rows.append(
            {
                "filename": filename,
                "specimen_id": specimen_id,
                "genus": genus,
                "species": species,
                "part": part,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = build_parser("Generate the data.csv manifest for kPCA specimen matching.")
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    settings = resolve_settings(args)
    parts = parts_to_process(args)

    exit_code = 0
    for part in parts:
        input_dir = Path(args.input) if args.input else settings.stage_dir("vtk", part)
        output_dir = Path(args.output) if args.output else settings.stage_dir("manifests", part)

        if not input_dir.is_dir():
            logger.warning("Input folder does not exist, skipping part %s: %s", part, input_dir)
            exit_code = 1
            continue

        vtk_files = sorted(p.name for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".vtk")
        logger.info("[%s] VTK files found: %d", part, len(vtk_files))

        rows = build_rows(vtk_files, part, settings.crania_tokens, settings.mandible_tokens)

        if args.dry_run:
            print(f"  would write: {output_dir / 'data.csv'} ({len(rows)} rows)")
            continue

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "data.csv"
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

        logger.info("[%s] Wrote %s (%d rows)", part, output_path, len(rows))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
