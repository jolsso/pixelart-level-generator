"""
Validation tests — boundary conditions and error handling at module boundaries.
Covers cases not exercised by the unit tests.
"""
import io
import json
import pytest
from pathlib import Path
from PIL import Image
from unittest.mock import patch

from pixelart_map.catalog import Catalog, TileInfo
from pixelart_map.renderer import render_map
from pixelart_map import get_catalog

TILE_1 = "aaaa000000000000000000000000000000000000000000000000000000000001"


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------

def test_catalog_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        Catalog(tmp_path / "nonexistent.json")


def test_catalog_malformed_json_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    with pytest.raises(json.JSONDecodeError):
        Catalog(bad)


def test_catalog_missing_tiles_key_loads_empty(tmp_path):
    """A catalog.json with no 'tiles' key should load as an empty catalog."""
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps({"version": 1, "generated_at": "2026-01-01"}))
    catalog = Catalog(p)
    assert catalog.themes() == []
    assert catalog.map_types() == []


def test_tileinfo_from_dict_missing_required_field():
    """TileInfo.from_dict raises KeyError when a required field is absent."""
    incomplete = {
        "id": "abc",
        "path": "some/path.png",
        "theme": "Office",
        # map_type missing
        "grid_unit": 16,
        "pixel_width": 16,
        "pixel_height": 16,
        "description": "A tile",
        "semantic_type": "floor",
        "tags": [],
    }
    with pytest.raises(KeyError):
        TileInfo.from_dict(incomplete)


def test_get_catalog_missing_file_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("PIXELART_CATALOG_PATH", str(tmp_path / "missing.json"))
    with pytest.raises(FileNotFoundError):
        get_catalog()


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def test_render_empty_placements_returns_blank_png(catalog_with_png_paths, data_dir):
    """Empty placements list should return a valid blank RGBA PNG."""
    from pixelart_map.catalog import Catalog
    catalog = Catalog(catalog_with_png_paths)
    result = render_map(
        grid_width=3,
        grid_height=2,
        placements=[],
        data_dir=str(data_dir),
        catalog=catalog,
    )
    assert isinstance(result.png_bytes, bytes)
    assert result.tilemap == []
    # The PNG should be valid and decodable
    img = Image.open(io.BytesIO(result.png_bytes))
    # Empty placements uses raw pixel dimensions (grid_width x grid_height), not grid_unit scaled
    assert img.size == (3, 2)


def test_render_uses_pixelart_data_dir_env_var(catalog_with_png_paths, data_dir, monkeypatch):
    """render_map() should accept PIXELART_DATA_DIR in place of data_dir argument."""
    from pixelart_map.catalog import Catalog
    monkeypatch.setenv("PIXELART_DATA_DIR", str(data_dir))
    catalog = Catalog(catalog_with_png_paths)
    result = render_map(
        grid_width=2,
        grid_height=2,
        placements=[{"x": 0, "y": 0, "tile_id": TILE_1}],
        catalog=catalog,
        # data_dir not passed — should fall back to env var
    )
    assert len(result.png_bytes) > 0


def test_render_multi_tile_correct_dimensions(catalog_with_png_paths, data_dir):
    """Canvas dimensions scale correctly with multiple placements."""
    from pixelart_map.catalog import Catalog
    TILE_2 = "bbbb000000000000000000000000000000000000000000000000000000000002"
    catalog = Catalog(catalog_with_png_paths)
    result = render_map(
        grid_width=4,
        grid_height=3,
        placements=[
            {"x": 0, "y": 0, "tile_id": TILE_1},
            {"x": 1, "y": 0, "tile_id": TILE_2},
        ],
        data_dir=str(data_dir),
        catalog=catalog,
    )
    img = Image.open(io.BytesIO(result.png_bytes))
    assert img.size == (4 * 48, 3 * 48)
    assert len(result.tilemap) == 2


def test_render_tilemap_entry_has_all_fields(catalog_with_png_paths, data_dir):
    """Each tilemap entry should carry theme, map_type, semantic_type, pixel dimensions."""
    from pixelart_map.catalog import Catalog
    catalog = Catalog(catalog_with_png_paths)
    result = render_map(
        grid_width=2, grid_height=2,
        placements=[{"x": 0, "y": 0, "tile_id": TILE_1}],
        data_dir=str(data_dir),
        catalog=catalog,
    )
    entry = result.tilemap[0]
    for field in ("x", "y", "tile_id", "theme", "map_type", "semantic_type", "pixel_width", "pixel_height"):
        assert field in entry, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

def test_analyzer_missing_subtree_skips_gracefully(tmp_path):
    """build_catalog() should not crash if a scan subtree doesn't exist."""
    from pixelart_map.analyzer import build_catalog
    # tmp_path has no data subdirectories at all
    with patch("pixelart_map.analyzer.analyze_tile") as mock:
        catalog = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")
    mock.assert_not_called()
    assert catalog["tiles"] == {}


def test_analyzer_tile_id_matches_catalog_key(tmp_path):
    """The tile_id stored inside each tile entry must match its dict key."""
    from pixelart_map.analyzer import build_catalog

    interior_dir = (
        tmp_path
        / "moderninteriors-win/1_Interiors/48x48"
        / "Theme_Sorter_Shadowless_Singles_48x48"
        / "5_Classroom_and_Library_Singles_Shadowless_48x48"
    )
    interior_dir.mkdir(parents=True)
    Image.new("RGBA", (48, 48), (0, 0, 0, 255)).save(interior_dir / "tile.png")

    def fake_analyze(path, host, model):
        return {"description": "x", "semantic_type": "floor", "tags": []}

    with patch("pixelart_map.analyzer.analyze_tile", side_effect=fake_analyze):
        catalog = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")

    for key, tile in catalog["tiles"].items():
        assert tile["id"] == key, "Tile id must match its catalog dict key"
        assert len(key) == 64, "Tile id must be a full SHA-256 hex string"
