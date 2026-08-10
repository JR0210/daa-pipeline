"""Run the DAA pipeline end-to-end, stopping only at the three points that
need a human: watertightness rework, visual alignment QC approval, and the
external Deformetrica run.

Usage:
    python run_pipeline.py                    # resume from the last completed stage
    python run_pipeline.py --status           # show progress without running anything
    python run_pipeline.py --dry-run          # print every stage's command, run nothing
    python run_pipeline.py --approve visual_qc
    python run_pipeline.py --from ply_to_vtk  # re-enter at a specific stage
    python run_pipeline.py --only decimate    # run a single stage regardless of state

See pipeline.yaml for the stage declarations and README.md for the full
walkthrough.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from daa.cli import setup_logging
from daa.config import load_settings
from daa.pipeline import PipelineState, list_status, load_pipeline, run

REPO_ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the DAA pipeline end-to-end.")
    parser.add_argument("--data-root", default=None, help="Overrides DATA_ROOT env var.")
    parser.add_argument("--jobs", type=int, default=None, help="Overrides JOBS env var.")
    parser.add_argument(
        "--pipeline",
        default=str(REPO_ROOT / "pipeline.yaml"),
        help="Path to the pipeline YAML (default: pipeline.yaml next to this script).",
    )
    parser.add_argument("--from", dest="from_stage", default=None, help="Re-enter at a specific stage.")
    parser.add_argument("--only", default=None, help="Run a single stage regardless of recorded progress.")
    parser.add_argument("--approve", default=None, metavar="KEY", help="Record approval for a gate and exit.")
    parser.add_argument("--status", action="store_true", help="Print stage progress and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would run without running it.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print each stage's rendered command.")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    settings = load_settings(data_root_override=args.data_root)
    if args.jobs:
        settings.jobs = args.jobs

    pipeline_path = Path(args.pipeline)
    if not pipeline_path.is_file():
        print(f"Pipeline file not found: {pipeline_path}", file=sys.stderr)
        return 1
    stages = load_pipeline(pipeline_path)

    state_path = settings.reports_dir() / "pipeline_state.json"
    state = PipelineState.load(state_path)

    if args.status:
        print(list_status(stages, state))
        return 0

    if args.approve:
        known_keys = {s.approval_key for s in stages if s.approval_key}
        if args.approve not in known_keys:
            print(
                f"Unknown approval key: {args.approve!r}. Known keys: {', '.join(sorted(known_keys)) or '(none)'}",
                file=sys.stderr,
            )
            return 1
        state.approve(args.approve)
        state.save(state_path)
        print(f"Recorded approval for {args.approve!r}. Run the pipeline again to continue.")
        return 0

    return run(
        stages,
        settings,
        state,
        state_path,
        from_stage=args.from_stage,
        only=args.only,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
