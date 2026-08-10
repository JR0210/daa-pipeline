import pytest

from daa.naming import UnclassifiedMeshError, canonical_name, parse_specimen

CRANIA_TOKENS = ["crania", "cranium", "skull"]
MANDIBLE_TOKENS = ["mandible", "mandibles", "jaw"]


@pytest.mark.parametrize(
    "filename,expected_species,expected_part",
    [
        ("Ailuropoda_melanoleuca crania_wrapped.ply", "Ailuropoda_melanoleuca", "crania"),
        ("Ailuropoda_melanoleuca mandible_wrapped.ply", "Ailuropoda_melanoleuca", "mandible"),
        ("Ailurus_fulgens crania_wrapped.ply", "Ailurus_fulgens", "crania"),
        ("Ailurus_fulgens mandible_wrapped.ply", "Ailurus_fulgens", "mandible"),
        ("Alopex lagopus crania_wrapped.ply", "Alopex_lagopus", "crania"),
        ("Alopex lagopus mandible_wrapped.ply", "Alopex_lagopus", "mandible"),
    ],
)
def test_parse_real_mesh_filenames(filename, expected_species, expected_part):
    specimen = parse_specimen(filename, CRANIA_TOKENS, MANDIBLE_TOKENS)
    assert specimen.genus_species == expected_species
    assert specimen.part == expected_part
    assert specimen.original_name == filename


def test_parse_specimen_normalises_separators_consistently():
    underscore = parse_specimen(
        "Ailuropoda_melanoleuca crania_wrapped.ply", CRANIA_TOKENS, MANDIBLE_TOKENS
    )
    space = parse_specimen(
        "Alopex lagopus crania_wrapped.ply", CRANIA_TOKENS, MANDIBLE_TOKENS
    )
    # Both separator styles collapse to the same underscore convention.
    assert "_" in underscore.genus_species
    assert " " not in underscore.genus_species
    assert "_" in space.genus_species
    assert " " not in space.genus_species


def test_unclassified_filename_raises():
    with pytest.raises(UnclassifiedMeshError):
        parse_specimen("some_random_scan.ply", CRANIA_TOKENS, MANDIBLE_TOKENS)


def test_canonical_name_format():
    specimen = parse_specimen(
        "Ailuropoda_melanoleuca crania_wrapped.ply", CRANIA_TOKENS, MANDIBLE_TOKENS
    )
    assert canonical_name(specimen, "dec", "ply") == "Ailuropoda_melanoleuca_crania_dec.ply"
    assert canonical_name(specimen, "", "vtk") == "Ailuropoda_melanoleuca_crania.vtk"
