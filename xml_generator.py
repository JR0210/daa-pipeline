# Paper - Assessing the application of landmark-free morphometrics to macroevolutionary analyses

"""Generate the data_set.xml file used by Deformetrica.

Usage:
    python xml_generator.py --part both
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

from daa.cli import build_parser, parts_to_process, resolve_settings, setup_logging

logger = logging.getLogger("daa")


def build_data_set_xml(vtk_filenames: list[str], object_id: str) -> str:
    root = Element("data-set")
    for filename in vtk_filenames:
        subject = SubElement(root, "subject", id=filename)
        visit = SubElement(subject, "visit", id=object_id)
        file_el = SubElement(visit, "filename", object_id=object_id)
        file_el.text = filename

    rough_xml = tostring(root, encoding="unicode")
    pretty = minidom.parseString(rough_xml).toprettyxml(indent="    ")
    # Drop the blank lines minidom inserts between elements.
    lines = [line for line in pretty.splitlines() if line.strip()]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser("Generate the Deformetrica data_set.xml manifest.")
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

        if not vtk_files:
            logger.warning("[%s] No VTK files found, skipping XML generation", part)
            exit_code = 1
            continue

        xml_data = build_data_set_xml(vtk_files, object_id=part)

        if args.dry_run:
            print(f"  would write: {output_dir / 'data_set.xml'}")
            continue

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "data_set.xml"
        output_path.write_text(xml_data, encoding="utf-8")
        logger.info("[%s] Wrote %s", part, output_path)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
