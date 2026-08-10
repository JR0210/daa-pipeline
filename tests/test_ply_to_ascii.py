from plyfile import PlyData

from ply_to_ascii import convert_to_ascii
from tests.fixtures import make_mixed_face_ply, make_tetrahedron_ply


def test_round_trip_preserves_vertex_and_face_counts(tmp_path):
    input_path = tmp_path / "tetrahedron.ply"
    n_vertices, n_faces = make_tetrahedron_ply(input_path)

    output_path = tmp_path / "out.ply"
    converted_n_vertices, converted_n_faces = convert_to_ascii(input_path, output_path)

    assert converted_n_vertices == n_vertices
    assert converted_n_faces == n_faces

    converted = PlyData.read(str(output_path))
    assert len(converted["vertex"].data) == n_vertices
    assert len(converted["face"].data) == n_faces
    assert converted.text is True


def test_non_triangular_faces_are_written_correctly(tmp_path):
    input_path = tmp_path / "quad_and_tri.ply"
    n_vertices, n_faces = make_mixed_face_ply(input_path)

    output_path = tmp_path / "out.ply"
    converted_n_vertices, converted_n_faces = convert_to_ascii(input_path, output_path)

    assert converted_n_vertices == n_vertices
    assert converted_n_faces == n_faces

    converted = PlyData.read(str(output_path))
    converted_faces = converted["face"].data["vertex_indices"]
    assert list(converted_faces[0]) == [0, 1, 2, 3]
    assert list(converted_faces[1]) == [0, 1, 4]
