import pytest
from pixelart_map.catalog import Catalog, TileInfo

TILE_ID_1 = "aaaa000000000000000000000000000000000000000000000000000000000001"
TILE_ID_2 = "bbbb000000000000000000000000000000000000000000000000000000000002"
TILE_ID_3 = "cccc000000000000000000000000000000000000000000000000000000000003"


def test_get_tile_returns_tile_info(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    tile = catalog.get_tile(TILE_ID_1)
    assert isinstance(tile, TileInfo)
    assert tile.id == TILE_ID_1
    assert tile.theme == "Classroom_and_Library"
    assert tile.map_type == "interior"
    assert tile.grid_unit == 48
    assert tile.pixel_width == 48
    assert tile.pixel_height == 48
    assert tile.semantic_type == "furniture"
    assert "desk" in tile.tags


def test_get_tile_unknown_raises(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    with pytest.raises(KeyError):
        catalog.get_tile("nonexistent")


def test_themes(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    themes = catalog.themes()
    assert set(themes) == {"Classroom_and_Library", "Office"}


def test_map_types(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    assert set(catalog.map_types()) == {"interior", "exterior"}


def test_tiles_by_theme(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    tiles = catalog.tiles_by_theme("Classroom_and_Library")
    assert len(tiles) == 2
    assert all(t.theme == "Classroom_and_Library" for t in tiles)


def test_tiles_by_theme_empty(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    assert catalog.tiles_by_theme("Nonexistent") == []


def test_tiles_by_map_type(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    interiors = catalog.tiles_by_map_type("interior")
    assert len(interiors) == 2
    assert all(t.map_type == "interior" for t in interiors)


def test_tiles_by_semantic_type(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    furniture = catalog.tiles_by_semantic_type("furniture")
    assert len(furniture) == 2


def test_search_by_tag(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    results = catalog.search("desk")
    assert len(results) == 1
    assert results[0].id == TILE_ID_1


def test_search_by_description(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    results = catalog.search("bookshelf")
    assert len(results) == 1
    assert results[0].id == TILE_ID_2


def test_search_case_insensitive(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    assert catalog.search("DESK") == catalog.search("desk")


def test_search_no_results(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    assert catalog.search("xyzzy") == []
