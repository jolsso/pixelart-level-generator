"""
Integration tests — full pipeline exercised end-to-end without mocking I/O.
Ollama is still mocked (no GPU), but all file I/O and module interactions are real.
"""
import io
import pytest
from pathlib import Path
from PIL import Image
from unittest.mock import patch

from pixelart_map.analyzer import build_catalog
from pixelart_map.catalog import Catalog, open_catalog_db, insert_tile
from pixelart_map.renderer import render_map, _load_image
from pixelart_map import get_catalog


def _make_asset_tree(base: Path) -> None:
    interior_dir = (
        base
        / "moderninteriors-win/1_Interiors/48x48"
        / "Theme_Sorter_Shadowless_Singles_48x48"
        / "5_Classroom_and_Library_Singles_Shadowless_48x48"
    )
    exterior_dir = (
        base
        / "modernexteriors-win/Modern_Exteriors_16x16/ME_Theme_Sorter_16x16"
        / "16_Office_Singles_16x16"
    )
    interior_dir.mkdir(parents=True)
    exterior_dir.mkdir(parents=True)
    Image.new("RGBA", (48, 48), (255, 0, 0, 255)).save(interior_dir / "floor.png")
    Image.new("RGBA", (48, 96), (0, 0, 255, 255)).save(interior_dir / "bookshelf.png")
    Image.new("RGBA", (16, 16), (0, 255, 0, 255)).save(exterior_dir / "building.png")


def _fake_analyze(path, host, model):
    name = Path(path).stem
    return {"description": f"A {name} tile", "semantic_type": "floor", "tags": [name]}


def _write_catalog_db(catalog_data: dict, db_path: Path) -> None:
    conn = open_catalog_db(db_path)
    for tile in catalog_data["tiles"].values():
        insert_tile(conn, tile)
    conn.commit()
    conn.close()


def test_full_pipeline_analyzer_to_render(tmp_path):
    """
    Full end-to-end: build_catalog → write catalog.db → Catalog → render_map.
    No real Ollama or GPU needed.
    """
    _make_asset_tree(tmp_path)
    db_path = tmp_path / "catalog.db"

    # Step 1: run analyzer (Ollama mocked)
    with patch("pixelart_map.analyzer.analyze_tile", side_effect=_fake_analyze):
        catalog_data = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")

    assert len(catalog_data["tiles"]) == 3

    # Step 2: write catalog to SQLite
    _write_catalog_db(catalog_data, db_path)

    # Step 3: load via Catalog class
    catalog = Catalog(db_path)
    assert set(catalog.themes()) == {"Classroom_and_Library", "Office"}
    assert set(catalog.map_types()) == {"interior", "exterior"}

    # Step 4: pick an interior tile and render it
    interior_tiles = catalog.tiles_by_map_type("interior")
    assert len(interior_tiles) == 2
    floor_tile = next(t for t in interior_tiles if t.pixel_height == 48)

    _load_image.cache_clear()
    result = render_map(
        grid_width=3,
        grid_height=3,
        placements=[{"x": 0, "y": 0, "tile_id": floor_tile.id}],
        data_dir=str(tmp_path),
        catalog=catalog,
    )

    img = Image.open(io.BytesIO(result.png_bytes))
    assert img.size == (3 * 48, 3 * 48)
    assert img.mode == "RGBA"
    assert len(result.tilemap) == 1
    assert result.tilemap[0]["theme"] == "Classroom_and_Library"
    assert result.tilemap[0]["tile_id"] == floor_tile.id


def test_incremental_analyzer_does_not_reanalyze(tmp_path):
    """
    Second build_catalog() call with existing IDs should call analyze_tile
    only for new tiles, not for ones already in the catalog.
    """
    _make_asset_tree(tmp_path)

    with patch("pixelart_map.analyzer.analyze_tile", side_effect=_fake_analyze) as mock:
        first = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")
        assert mock.call_count == 3

        # Add one new tile
        new_dir = (
            tmp_path
            / "moderninteriors-win/1_Interiors/48x48"
            / "Theme_Sorter_Shadowless_Singles_48x48"
            / "5_Classroom_and_Library_Singles_Shadowless_48x48"
        )
        Image.new("RGBA", (48, 48), (128, 128, 0, 255)).save(new_dir / "new_tile.png")

        second = build_catalog(
            data_dir=tmp_path,
            host="http://localhost:11434",
            model="qwen2-vl",
            existing_ids=set(first["tiles"].keys()),
        )
        assert mock.call_count == 4
        assert len(second["tiles"]) == 1  # only the new tile returned


def test_get_catalog_env_var_points_to_analyzer_output(tmp_path, monkeypatch):
    """get_catalog() loads correctly from a catalog produced by the analyzer."""
    _make_asset_tree(tmp_path)
    db_path = tmp_path / "catalog.db"

    with patch("pixelart_map.analyzer.analyze_tile", side_effect=_fake_analyze):
        catalog_data = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")
    _write_catalog_db(catalog_data, db_path)

    monkeypatch.setenv("PIXELART_CATALOG_PATH", str(db_path))
    catalog = get_catalog()

    assert len(catalog.themes()) > 0
    results = catalog.search("floor")
    assert len(results) > 0


def test_render_draw_order_respected(tmp_path):
    """
    Tiles rendered later in placements list should overwrite earlier ones
    at the same coordinates.
    """
    _make_asset_tree(tmp_path)
    db_path = tmp_path / "catalog.db"

    with patch("pixelart_map.analyzer.analyze_tile", side_effect=_fake_analyze):
        catalog_data = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")
    _write_catalog_db(catalog_data, db_path)

    catalog = Catalog(db_path)
    interior_tiles = catalog.tiles_by_map_type("interior")
    tile_a, tile_b = interior_tiles[0], interior_tiles[1]
    tile_b = next(t for t in interior_tiles if t.pixel_height == 48 and t.id != tile_a.id) \
        if len(interior_tiles) > 1 else tile_a

    _load_image.cache_clear()
    result = render_map(
        grid_width=2,
        grid_height=2,
        placements=[
            {"x": 0, "y": 0, "tile_id": tile_a.id},
            {"x": 0, "y": 0, "tile_id": tile_b.id},
        ],
        data_dir=str(tmp_path),
        catalog=catalog,
    )

    assert len(result.tilemap) == 2
    assert result.tilemap[0]["tile_id"] == tile_a.id
    assert result.tilemap[1]["tile_id"] == tile_b.id
