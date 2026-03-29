import pytest
from pixelart_map._filename import parse_exterior_filename


@pytest.mark.parametrize("stem,theme,expected_object,expected_semantic", [
    # Pattern 1: ME_Singles — standard single-word object
    ("ME_Singles_City_Props_16x16_ATM_1",               "City_Props",           "ATM",                      "prop"),
    ("ME_Singles_City_Props_16x16_Antenna",             "City_Props",           "Antenna",                  "prop"),
    ("ME_Singles_City_Props_16x16_Bench_3",             "City_Props",           "Bench",                    "furniture"),
    ("ME_Singles_City_Props_16x16_Barrel_12",           "City_Props",           "Barrel",                   "prop"),
    # Pattern 1: ME_Singles — multi-word object
    ("ME_Singles_School_16x16_Basketball_Ball_1",       "School",               "Basketball ball",          "prop"),
    ("ME_Singles_School_16x16_Basketball_Court_4",      "School",               "Basketball court",         "floor"),
    ("ME_Singles_School_16x16_Clock_Tower_1",           "School",               "Clock tower",              "building"),
    # Pattern 1: ME_Singles — vehicles with direction suffix
    ("ME_Singles_Vehicles_16x16_Ambulance_Down_1",      "Vehicles",             "Ambulance down",           "vehicle"),
    ("ME_Singles_Vehicles_16x16_Boat_1_Down_2",         "Vehicles",             "Boat 1 down",              "vehicle"),
    # Pattern 1: ME_Singles — terrain / floor / wall
    ("ME_Singles_Terrains_and_Fences_16x16_Deep_Water_1_5", "Terrains_and_Fences", "Deep water 1",         "terrain"),
    ("ME_Singles_City_Terrains_16x16_Asphalt_1_Variation_27", "City_Terrains", "Asphalt 1 variation",      "floor"),
    ("ME_Singles_Generic_Building_16x16_Condo_1_3",     "Generic_Building",     "Condo 1",                  "building"),
    ("ME_Singles_Terrains_and_Fences_16x16_Fence_1",    "Terrains_and_Fences",  "Fence",                    "wall"),
    # Pattern 2: {N}_{Theme}_16x16_{Object} — Beach / Post Office / Military
    ("21_Beach_16x16_Ball",                             "Beach",                "Ball",                     "prop"),
    ("21_Beach_16x16_Beach_Sign",                       "Beach",                "Beach sign",               "decoration"),
    ("21_Beach_16x16_Bamboo_Bar_Counter_1",             "Beach",                "Bamboo bar counter",       "furniture"),
    ("22_Post_Office_16x16_Big_Blue_Mailbox",           "Post_Office",          "Big blue mailbox",         "prop"),
    ("23_MIlitary_Base_16x16_Barbed_Wire_1",            "Military_Base",        "Barbed wire",              "prop"),
    # Pattern 3: {N}_{Theme}_{Object}_16x16 — Additional Houses (resolution suffix)
    ("24_Additional_Houses_Country_House_16x16",        "Additional_Houses",    "Country house",            "building"),
    ("24_Additional_Houses_Fence_1_Bottom_Left_16x16",  "Additional_Houses",    "Fence",                    "wall"),
])
def test_parse_exterior_filename(stem, theme, expected_object, expected_semantic):
    result = parse_exterior_filename(stem, theme)
    assert result is not None
    assert result["description"].lower().startswith(expected_object.lower())
    assert result["semantic_type"] == expected_semantic
    assert isinstance(result["tags"], list)
    assert len(result["tags"]) > 0


def test_parse_exterior_returns_none_for_interior(sample_catalog_path):
    """Interior filenames don't start with ME_Singles_ — should return None."""
    result = parse_exterior_filename(
        "Birthday_Party_Singles_Shadowless_48x48_1",
        "Birthday_Party",
    )
    assert result is None


def test_parse_exterior_returns_none_for_unknown_pattern():
    assert parse_exterior_filename("some_random_file", "Theme") is None


def test_tags_exclude_noise_words():
    result = parse_exterior_filename(
        "ME_Singles_City_Terrains_16x16_Asphalt_1_Variation_5",
        "City_Terrains",
    )
    assert result is not None
    # Pure numbers and stop words should not appear as tags
    assert "1" not in result["tags"]
    assert "5" not in result["tags"]
    assert "variation" not in result["tags"]


def test_tags_include_theme_words():
    result = parse_exterior_filename(
        "ME_Singles_School_16x16_Bench_2",
        "School",
    )
    assert result is not None
    assert "school" in result["tags"]
    assert "bench" in result["tags"]


def test_no_duplicate_tags():
    result = parse_exterior_filename(
        "ME_Singles_School_16x16_School_Bench_1",
        "School",
    )
    assert result is not None
    assert result["tags"].count("school") == 1


def test_description_format():
    result = parse_exterior_filename(
        "ME_Singles_City_Props_16x16_ATM_1",
        "City_Props",
    )
    assert result is not None
    assert result["description"].endswith(", top-down view")


def test_analyzer_skips_ollama_for_exterior(tmp_path):
    """Analyzer should not call Ollama for exterior tiles with parseable filenames."""
    from PIL import Image
    from unittest.mock import patch
    from pixelart_map.analyzer import build_catalog

    exterior_dir = (
        tmp_path
        / "modernexteriors-win/Modern_Exteriors_16x16/ME_Theme_Sorter_16x16"
        / "13_School_Singles_16x16"
    )
    exterior_dir.mkdir(parents=True)
    Image.new("RGBA", (16, 16), (0, 255, 0, 255)).save(
        exterior_dir / "ME_Singles_School_16x16_Bench_1.png"
    )

    with patch("pixelart_map.analyzer.analyze_tile") as mock_ollama:
        catalog = build_catalog(
            data_dir=tmp_path,
            host="http://localhost:11434",
            model="qwen2.5vl:7b",
        )

    mock_ollama.assert_not_called()
    assert len(catalog["tiles"]) == 1
    tile = next(iter(catalog["tiles"].values()))
    assert tile["semantic_type"] == "furniture"
    assert "bench" in tile["tags"]
    assert "school" in tile["tags"]
