import json
import pytest
from pathlib import Path
from unittest.mock import patch
from pixelart_map.analyzer import build_catalog, compute_tile_id


def make_asset_tree(base: Path) -> dict[str, Path]:
    """Create a minimal fake asset tree with 2 interior + 1 exterior PNG."""
    interior_dir = (
        base
        / "moderninteriors-win"
        / "1_Interiors"
        / "48x48"
        / "Theme_Sorter_Shadowless_Singles_48x48"
        / "5_Classroom_and_Library_Singles_Shadowless_48x48"
    )
    exterior_dir = (
        base
        / "modernexteriors-win"
        / "Modern_Exteriors_16x16"
        / "ME_Theme_Sorter_16x16"
        / "16_Office_Singles_16x16"
    )
    interior_dir.mkdir(parents=True)
    exterior_dir.mkdir(parents=True)

    from PIL import Image
    tiles = {}
    for name, size, d in [
        ("tile_a.png", (48, 48), interior_dir),
        ("tile_b.png", (48, 96), interior_dir),
        ("tile_c.png", (16, 16), exterior_dir),
    ]:
        p = d / name
        Image.new("RGBA", size, (100, 100, 100, 255)).save(p)
        tiles[name] = p
    return tiles


def _fake_analyze(path, host, model):
    return {
        "description": f"A tile at {Path(path).name}",
        "semantic_type": "floor",
        "tags": ["test"],
    }


def test_build_catalog_produces_entries(tmp_path):
    make_asset_tree(tmp_path)
    with patch("pixelart_map.analyzer.analyze_tile", side_effect=_fake_analyze):
        catalog = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")

    assert len(catalog["tiles"]) == 3
    assert catalog["version"] == 1
    assert "generated_at" in catalog


def test_build_catalog_tile_fields(tmp_path):
    make_asset_tree(tmp_path)
    with patch("pixelart_map.analyzer.analyze_tile", side_effect=_fake_analyze):
        catalog = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")

    tiles = list(catalog["tiles"].values())
    interior = next(t for t in tiles if t["map_type"] == "interior" and t["pixel_height"] == 48)
    assert interior["theme"] == "Classroom_and_Library"
    assert interior["grid_unit"] == 48
    assert interior["pixel_width"] == 48

    tall = next(t for t in tiles if t["pixel_height"] == 96)
    assert tall["map_type"] == "interior"
    assert tall["pixel_height"] == 96

    exterior = next(t for t in tiles if t["map_type"] == "exterior")
    assert exterior["theme"] == "Office"
    assert exterior["grid_unit"] == 16


def test_build_catalog_skips_already_analyzed(tmp_path):
    make_asset_tree(tmp_path)
    with patch("pixelart_map.analyzer.analyze_tile", side_effect=_fake_analyze) as mock_analyze:
        catalog1 = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")
        assert mock_analyze.call_count == 3

        catalog2 = build_catalog(
            data_dir=tmp_path,
            host="http://localhost:11434",
            model="qwen2-vl",
            existing=catalog1,
        )
        assert mock_analyze.call_count == 3  # unchanged


def test_build_catalog_skips_failed_tiles(tmp_path):
    make_asset_tree(tmp_path)
    with patch("pixelart_map.analyzer.analyze_tile", return_value=None):
        catalog = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")
    assert len(catalog["tiles"]) == 0


def test_compute_tile_id_is_sha256(tmp_path):
    import hashlib
    rel_path = "some/path/tile.png"
    expected = hashlib.sha256(rel_path.encode()).hexdigest()
    assert compute_tile_id(rel_path) == expected
    assert len(compute_tile_id(rel_path)) == 64
