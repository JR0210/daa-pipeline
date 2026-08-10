"""Synthetic PLY mesh builders for tests.

Every mesh here is generated at test time from a handful of hardcoded
vertices/faces -- no real specimen data, no binary fixture files committed
to the repo. This keeps the test suite fully independent of `./meshes`,
which is gitignored personal data and must not be a dependency for tests
to actually run (as opposed to silently skipping).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from plyfile import PlyData, PlyElement


def make_tetrahedron_ply(path: Path) -> tuple[int, int]:
    """Write a minimal 4-vertex, 4-triangular-face mesh.

    Returns (n_vertices, n_faces).
    """
    vertex_data = np.array(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)],
        dtype=[("x", "f4"), ("y", "f4"), ("z", "f4")],
    )
    vertex_element = PlyElement.describe(vertex_data, "vertex")

    faces = [
        np.array([0, 1, 2], dtype="i4"),
        np.array([0, 1, 3], dtype="i4"),
        np.array([0, 2, 3], dtype="i4"),
        np.array([1, 2, 3], dtype="i4"),
    ]
    face_data = np.empty(len(faces), dtype=[("vertex_indices", "O")])
    for i, f in enumerate(faces):
        face_data["vertex_indices"][i] = f
    face_element = PlyElement.describe(
        face_data, "face", len_types={"vertex_indices": "u1"}, val_types={"vertex_indices": "i4"}
    )

    PlyData([vertex_element, face_element], text=True).write(str(path))
    return len(vertex_data), len(faces)


def make_mixed_face_ply(path: Path) -> tuple[int, int]:
    """Write a 5-vertex mesh with one quad face and one triangular face.

    Locks in the fix for the original hand-rolled ASCII writer, which
    hardcoded a 4-field face format ("{} {} {} {}") and raised on any
    non-triangular face.

    Returns (n_vertices, n_faces).
    """
    vertex_data = np.array(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0), (0.5, 0.5, 1.0)],
        dtype=[("x", "f4"), ("y", "f4"), ("z", "f4")],
    )
    vertex_element = PlyElement.describe(vertex_data, "vertex")

    faces = [np.array([0, 1, 2, 3], dtype="i4"), np.array([0, 1, 4], dtype="i4")]
    face_data = np.empty(len(faces), dtype=[("vertex_indices", "O")])
    for i, f in enumerate(faces):
        face_data["vertex_indices"][i] = f
    face_element = PlyElement.describe(
        face_data, "face", len_types={"vertex_indices": "u1"}, val_types={"vertex_indices": "i4"}
    )

    PlyData([vertex_element, face_element], text=True).write(str(path))
    return len(vertex_data), len(faces)
