"""Per-stage reporting and the exit-code contract the pipeline runner relies on.

Exit codes:
    0 = success
    1 = hard error (missing input, crash before any work was attempted)
    2 = gate condition not met (e.g. non-watertight meshes found) -- needs
        human intervention before the pipeline can continue
    3 = partial success -- some specimens processed, some errored
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

logger = logging.getLogger("daa")

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_GATE = 2
EXIT_PARTIAL = 3


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_stage_report(
    reports_dir: Path,
    stage_name: str,
    results: list[dict],
    errors: list[dict],
    result_fields: list[str],
    error_fields: list[str],
) -> int:
    """Write metrics/errors CSVs for a stage and return the suggested exit code.

    Returns EXIT_SUCCESS if there were no errors, EXIT_PARTIAL if there were
    both successes and errors, EXIT_ERROR if everything errored and nothing
    succeeded.
    """
    metrics_path = reports_dir / f"{stage_name}_metrics.csv"
    errors_path = reports_dir / f"{stage_name}_errors.csv"

    write_csv(metrics_path, results, result_fields)
    write_csv(errors_path, errors, error_fields)

    logger.info("Results saved to: %s", metrics_path)
    logger.info("Errors saved to: %s", errors_path)

    if errors:
        for error in errors:
            logger.warning("  %s", error)

    if not errors:
        return EXIT_SUCCESS
    if results:
        return EXIT_PARTIAL
    return EXIT_ERROR
