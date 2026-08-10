# Paper - Comparing landmark-free and manual landmarking methods for macroevolutionary studies using the mammalian crania

"""Generate kernel PCA scores and eigenvalues from Deformetrica atlas output.

Reads DeterministicAtlas__EstimatedParameters__{ControlPoints,Momenta}.txt
from the Deformetrica output directory (08_daa/<part>/ by default) plus the
data.csv manifest (06_manifests/<part>/data.csv), and writes kpca.csv and
eigenvalues.csv to 09_kpca/<part>/.

Usage:
    python kpca_generator.py --part both [--n-components N] [--gamma G]

This is the final pipeline stage and is external-input-dependent: it cannot
run until Deformetrica has produced the atlas for a given part.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import KernelPCA

from daa.cli import build_parser, parts_to_process, resolve_settings, setup_logging

logger = logging.getLogger("daa")

CONTROL_POINTS_FILENAME = "DeterministicAtlas__EstimatedParameters__ControlPoints.txt"
MOMENTA_FILENAME = "DeterministicAtlas__EstimatedParameters__Momenta.txt"


def load_momenta(daa_dir: Path) -> tuple[np.ndarray, int, int, int]:
    momenta_path = daa_dir / MOMENTA_FILENAME
    with open(momenta_path) as f:
        first_line = f.readline().split(" ")
    number_of_subjects = int(first_line[0])
    number_of_controlpoints = int(first_line[1])
    dimension = int(first_line[2])

    momenta = np.loadtxt(momenta_path, skiprows=2)
    momenta_linearised = momenta.reshape([number_of_subjects, dimension * number_of_controlpoints])

    return momenta_linearised, number_of_subjects, number_of_controlpoints, dimension


def run_kpca(
    momenta_linearised: np.ndarray,
    df: pd.DataFrame,
    n_components: int,
    gamma: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    kpca = KernelPCA(kernel="rbf", fit_inverse_transform=True, n_components=n_components, gamma=gamma)
    x_kpca = kpca.fit_transform(momenta_linearised)

    df = df.copy()
    for i in range(x_kpca.shape[1]):
        df[f"PC{i + 1}"] = x_kpca[:, i]

    # sklearn >=0.24 renamed KernelPCA.lambdas_/alphas_ to eigenvalues_/eigenvectors_.
    eigenvalues = kpca.eigenvalues_
    eigenvectors = kpca.eigenvectors_ / np.linalg.norm(kpca.eigenvectors_, axis=0)

    eig = pd.DataFrame()
    eig["PCA dimension"] = [f"PC{i + 1}" for i in range(len(eigenvalues))]
    eig["cum. variability (in %)"] = 100 * np.cumsum(eigenvalues) / np.sum(eigenvalues)
    eig["lambda"] = eigenvalues
    eig["alpha"] = list(np.transpose(eigenvectors))

    return df, eig


def main(argv: list[str] | None = None) -> int:
    parser = build_parser("Generate kernel PCA scores and eigenvalues from a Deformetrica atlas.")
    parser.add_argument("--daa-dir", default=None, help="Deformetrica output directory (overrides stage default).")
    parser.add_argument("--manifest-dir", default=None, help="Directory containing data.csv (overrides stage default).")
    parser.add_argument("--n-components", type=int, default=None, help="Number of kPCA components (default: number of subjects).")
    parser.add_argument("--gamma", type=float, default=None, help="RBF kernel gamma (overrides KPCA_GAMMA env var).")
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    settings = resolve_settings(args)
    parts = parts_to_process(args)
    gamma = args.gamma if args.gamma is not None else settings.kpca_gamma

    exit_code = 0
    for part in parts:
        daa_dir = Path(args.daa_dir) if args.daa_dir else settings.stage_dir("daa", part)
        manifest_dir = Path(args.manifest_dir) if args.manifest_dir else settings.stage_dir("manifests", part)
        output_dir = Path(args.output) if args.output else settings.stage_dir("kpca", part)

        momenta_path = daa_dir / MOMENTA_FILENAME
        control_points_path = daa_dir / CONTROL_POINTS_FILENAME
        manifest_path = manifest_dir / "data.csv"

        missing = [p for p in (momenta_path, control_points_path, manifest_path) if not p.exists()]
        if missing:
            logger.warning(
                "[%s] Skipping: missing required input(s): %s",
                part,
                ", ".join(str(p) for p in missing),
            )
            exit_code = 1
            continue

        momenta_linearised, number_of_subjects, number_of_controlpoints, dimension = load_momenta(daa_dir)
        logger.info(
            "[%s] Control points: %d, Subjects: %d, Dimension: %d",
            part,
            number_of_controlpoints,
            number_of_subjects,
            dimension,
        )

        df = pd.read_csv(manifest_path)
        if len(df) != number_of_subjects:
            logger.warning(
                "[%s] data.csv has %d rows but Momenta.txt reports %d subjects; "
                "kPCA scores will be misaligned with specimen metadata.",
                part,
                len(df),
                number_of_subjects,
            )

        n_components = args.n_components or settings.kpca_n_components or number_of_subjects
        n_components = min(n_components, number_of_subjects)

        if args.dry_run:
            print(f"  would run kPCA for {part}: n_components={n_components}, gamma={gamma}")
            continue

        df_out, eig = run_kpca(momenta_linearised, df, n_components, gamma)

        output_dir.mkdir(parents=True, exist_ok=True)
        eig.to_csv(output_dir / "eigenvalues.csv")
        df_out.to_csv(output_dir / "kpca.csv")

        logger.info("[%s] Wrote %s and %s", part, output_dir / "eigenvalues.csv", output_dir / "kpca.csv")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
