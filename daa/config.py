"""Central configuration for the DAA pipeline scripts.

Loads settings from a `.env` file (see `.env.example`) with environment
variables and hardcoded defaults as fallbacks. Every script in this repo
should derive its paths from `Settings` rather than hardcoding them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is a required dependency
    load_dotenv = None


_ENV_LOADED = False


def _ensure_env_loaded() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    if load_dotenv is not None:
        # Search upward from the current working directory for a .env file,
        # falling back to the repo root (this file's parent's parent).
        repo_root = Path(__file__).resolve().parent.parent
        env_path = repo_root / ".env"
        load_dotenv(dotenv_path=env_path if env_path.exists() else None)
    _ENV_LOADED = True


def _env_str(name: str, default: str) -> str:
    _ensure_env_loaded()
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    _ensure_env_loaded()
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    _ensure_env_loaded()
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def _env_list(name: str, default: list[str]) -> list[str]:
    _ensure_env_loaded()
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return [token.strip() for token in raw.split(",") if token.strip()]


PARTS = ("crania", "mandible")

STAGE_DIRS = {
    "raw": "01_raw",
    "decimated": "02_decimated",
    "ascii": "03_ascii",
    "aligned": "04_aligned",
    "vtk": "05_vtk",
    "manifests": "06_manifests",
    "qc_images": "07_qc_images",
    "daa": "08_daa",
    "kpca": "09_kpca",
}


@dataclass
class Settings:
    data_root: Path
    target_faces: int
    rscript_path: str
    landmarks_csv: Path | None
    kpca_gamma: float
    kpca_n_components: int | None
    jobs: int
    crania_tokens: list[str] = field(default_factory=list)
    mandible_tokens: list[str] = field(default_factory=list)

    def stage_dir(self, stage: str, part: str | None = None) -> Path:
        """Return the directory for a pipeline stage, optionally scoped to a part."""
        if stage not in STAGE_DIRS:
            raise KeyError(
                f"Unknown stage {stage!r}; expected one of {sorted(STAGE_DIRS)}"
            )
        base = self.data_root / STAGE_DIRS[stage]
        if part is None:
            return base
        if part not in PARTS:
            raise ValueError(f"Unknown part {part!r}; expected one of {PARTS}")
        return base / part

    def reports_dir(self) -> Path:
        return self.data_root / "_reports"

    def part_tokens(self, part: str) -> list[str]:
        if part == "crania":
            return self.crania_tokens
        if part == "mandible":
            return self.mandible_tokens
        raise ValueError(f"Unknown part {part!r}; expected one of {PARTS}")

    def resolve_raw_input(self) -> tuple[Path, str | None]:
        """Resolve the raw-mesh input directory.

        Prefers DATA_ROOT/01_raw; if that doesn't exist but DATA_ROOT
        itself contains .ply files directly, falls back to DATA_ROOT
        itself -- so pointing DATA_ROOT straight at an existing mesh
        folder works with no manual folder creation. Every later stage
        still gets its own auto-created DATA_ROOT/NN_name folder; 01_raw
        is the one exception because it's the pipeline's sole external
        input, not something any script here produces.

        Only triggers when 01_raw doesn't exist at all -- if a user has
        already created it (even empty), that's treated as their explicit
        choice, not something to second-guess. If 01_raw exists but isn't a
        directory (e.g. a stray file with that name), that's a real
        misconfiguration and is returned as-is rather than silently
        falling back, so the caller's usual "does not exist" handling
        surfaces it instead of a misleading fallback note.

        Returns (resolved_dir, note); note explains the fallback when one
        is used, else None.
        """
        raw_dir = self.stage_dir("raw")
        if raw_dir.exists():
            return raw_dir, None
        if self.data_root.is_dir() and any(
            p.suffix.lower() == ".ply" for p in self.data_root.iterdir() if p.is_file()
        ):
            note = (
                f"{raw_dir} not found -- using {self.data_root} directly, since it "
                f"contains .ply files. (Optionally move them into {raw_dir} to keep "
                f"the pipeline's folder layout tidy -- both work.)"
            )
            return self.data_root, note
        return raw_dir, None


def load_settings(data_root_override: str | os.PathLike | None = None) -> Settings:
    """Build a Settings object from environment/.env, with an optional override."""
    _ensure_env_loaded()

    data_root = Path(
        data_root_override
        if data_root_override is not None
        else _env_str("DATA_ROOT", "./meshes")
    ).resolve()

    landmarks_csv_raw = _env_str("LANDMARKS_CSV", "")
    landmarks_csv = Path(landmarks_csv_raw).resolve() if landmarks_csv_raw else None

    kpca_n_components_raw = os.environ.get("KPCA_N_COMPONENTS", "")
    kpca_n_components = (
        int(kpca_n_components_raw) if kpca_n_components_raw.strip() else None
    )

    return Settings(
        data_root=data_root,
        target_faces=_env_int("TARGET_FACES", 50000),
        rscript_path=_env_str("RSCRIPT_PATH", "Rscript"),
        landmarks_csv=landmarks_csv,
        kpca_gamma=_env_float("KPCA_GAMMA", 0.0000025),
        kpca_n_components=kpca_n_components,
        jobs=_env_int("JOBS", os.cpu_count() or 1),
        crania_tokens=_env_list("CRANIA_TOKENS", ["crania", "cranium", "skull"]),
        mandible_tokens=_env_list(
            "MANDIBLE_TOKENS", ["mandible", "mandibles", "jaw"]
        ),
    )
