"""Canonical specimen naming/parsing shared by every stage of the pipeline.

Input filenames are inconsistent (underscore vs space separators, mixed
case, trailing "_wrapped" suffixes, etc). Every stage that needs to join
data across files (mesh <-> landmarks <-> manifests <-> kPCA output) must
go through this module so the join key is computed the same way everywhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CRANIA = "crania"
MANDIBLE = "mandible"

_WHITESPACE_RUN = re.compile(r"[\s_-]+")


class UnclassifiedMeshError(ValueError):
    """Raised when a filename does not contain a recognisable part token."""


@dataclass(frozen=True)
class Specimen:
    genus_species: str
    part: str
    original_name: str


def _normalise(raw: str) -> str:
    """Collapse whitespace/underscore/hyphen runs to a single underscore."""
    collapsed = _WHITESPACE_RUN.sub("_", raw.strip())
    return collapsed.strip("_")


def parse_specimen(
    filename: str,
    crania_tokens: list[str],
    mandible_tokens: list[str],
) -> Specimen:
    """Parse a specimen identity out of a raw input filename.

    Finds the earliest-occurring part token (case-insensitive) among the
    supplied crania/mandible synonym lists, takes everything before it as
    the species name, and normalises separators to a single underscore.
    Raises UnclassifiedMeshError if no known part token is found.
    """
    stem = filename
    for ext in (".ply", ".vtk", ".obj", ".stl"):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break

    lower = stem.lower()

    best_index: int | None = None
    best_token = ""
    best_part = ""
    for token in crania_tokens:
        idx = lower.find(token.lower())
        if idx != -1 and (best_index is None or idx < best_index):
            best_index = idx
            best_token = token
            best_part = CRANIA
    for token in mandible_tokens:
        idx = lower.find(token.lower())
        if idx != -1 and (best_index is None or idx < best_index):
            best_index = idx
            best_token = token
            best_part = MANDIBLE

    if best_index is None:
        raise UnclassifiedMeshError(
            f"Filename {filename!r} does not contain a recognised part token "
            f"(looked for {crania_tokens + mandible_tokens})"
        )

    species_raw = stem[:best_index]
    genus_species = _normalise(species_raw)

    if not genus_species:
        raise UnclassifiedMeshError(
            f"Filename {filename!r} has no species name before the part token "
            f"{best_token!r}"
        )

    return Specimen(genus_species=genus_species, part=best_part, original_name=filename)


def canonical_name(specimen: Specimen, suffix: str, ext: str) -> str:
    """Build the canonical output filename for a specimen.

    e.g. canonical_name(specimen, "dec", "ply") -> "Genus_species_crania_dec.ply"
    """
    ext = ext.lstrip(".")
    parts = [specimen.genus_species, specimen.part]
    if suffix:
        parts.append(suffix)
    return "_".join(parts) + f".{ext}"
