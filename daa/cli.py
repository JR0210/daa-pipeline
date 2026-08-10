"""Shared CLI scaffolding so every pipeline script has a consistent interface.

This is what lets the Stage 2 pipeline runner describe every stage uniformly
(same flags, same logging, same exit-code contract) regardless of whether
the stage does mesh processing, image rendering, or manifest generation.
"""

from __future__ import annotations

import argparse
import logging

from daa.config import PARTS, Settings, load_settings

logger = logging.getLogger("daa")


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got: {parsed}")
    return parsed


def build_parser(description: str) -> argparse.ArgumentParser:
    """Create an ArgumentParser pre-populated with the common pipeline flags.

    Scripts should call this, add any script-specific arguments, then parse.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--data-root",
        default=None,
        help="Root directory for pipeline stage folders (overrides DATA_ROOT env var).",
    )
    parser.add_argument(
        "--part",
        choices=(*PARTS, "both"),
        default="both",
        help="Which anatomical part to process (default: both).",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Input directory (overrides the stage default derived from --data-root).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (overrides the stage default derived from --data-root).",
    )
    parser.add_argument(
        "--jobs",
        type=positive_int,
        default=None,
        help="Number of parallel worker processes (overrides JOBS env var).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reprocess and overwrite outputs that already exist (default: skip them).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without writing any files.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )
    return parser


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def resolve_settings(args: argparse.Namespace) -> Settings:
    """Load Settings, applying any CLI overrides (CLI flag > env var > default)."""
    settings = load_settings(data_root_override=args.data_root)
    if getattr(args, "jobs", None) is not None:
        settings.jobs = args.jobs
    return settings


def parts_to_process(args: argparse.Namespace) -> list[str]:
    """Expand --part into the concrete list of parts to iterate over."""
    if args.part == "both":
        return list(PARTS)
    return [args.part]
