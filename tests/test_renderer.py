import io
import pytest
from PIL import Image
from pixelart_map.catalog import Catalog
from pixelart_map.renderer import render_map, RenderResult
from pixelart_map import renderer as renderer_module

TILE_1 = "aaaa000000000000000000000000000000000000000000000000000000000001"
TILE_2 = "bbbb000000000000000000000000000000000000000000000000000000000002"
TILE_3 = "cccc000000000000000000000000000000000000000000000000000000000003"


def test_render_returns_result(catalog_with_png_paths, data_dir):
    catalog = Catalog(catalog_with_png_paths)
    result = render_map(
        grid_width=2, grid_height=2,
        placements=[{"x": 0, "y": 0, "tile_id": TILE_1}],
        data_dir=str(data_dir),
        catalog=catalog,
    )
    assert isinstance(result, RenderResult)
    assert isinstance(result.png_bytes, bytes)
    assert len(result.png_bytes) > 0


def test_render_png_dimensions(catalog_with_png_paths, data_dir):
    catalog = Catalog(catalog_with_png_paths)
    result = render_map(
        grid_width=3, grid_height=2,
        placements=[{"x": 0, "y": 0, "tile_id": TILE_1}],
        data_dir=str(data_dir),
        catalog=catalog,
    )
    img = Image.open(io.BytesIO(result.png_bytes))
    assert img.size == (3 * 48, 2 * 48)  # 144x96


def test_render_tilemap_contains_metadata(catalog_with_png_paths, data_dir):
    catalog = Catalog(catalog_with_png_paths)
    result = render_map(
        grid_width=2, grid_height=2,
        placements=[{"x": 0, "y": 0, "tile_id": TILE_1}],
        data_dir=str(data_dir),
        catalog=catalog,
    )
    assert len(result.tilemap) == 1
    entry = result.tilemap[0]
    assert entry["x"] == 0
    assert entry["y"] == 0
    assert entry["tile_id"] == TILE_1
    assert entry["theme"] == "Classroom_and_Library"
    assert entry["semantic_type"] == "furniture"


def test_render_raises_on_unknown_tile(catalog_with_png_paths, data_dir):
    catalog = Catalog(catalog_with_png_paths)
    with pytest.raises(ValueError, match="Unknown tile_id"):
        render_map(
            grid_width=2, grid_height=2,
            placements=[{"x": 0, "y": 0, "tile_id": "unknown_id"}],
            data_dir=str(data_dir),
            catalog=catalog,
        )


def test_render_raises_on_map_type_mismatch(catalog_with_png_paths, data_dir):
    catalog = Catalog(catalog_with_png_paths)
    with pytest.raises(ValueError, match="map_type"):
        render_map(
            grid_width=2, grid_height=2,
            placements=[
                {"x": 0, "y": 0, "tile_id": TILE_1},  # interior
                {"x": 1, "y": 0, "tile_id": TILE_3},  # exterior
            ],
            data_dir=str(data_dir),
            catalog=catalog,
        )


def test_render_raises_when_no_data_dir(catalog_with_png_paths, monkeypatch):
    monkeypatch.delenv("PIXELART_DATA_DIR", raising=False)
    catalog = Catalog(catalog_with_png_paths)
    with pytest.raises(ValueError, match="data_dir"):
        render_map(
            grid_width=2, grid_height=2,
            placements=[{"x": 0, "y": 0, "tile_id": TILE_1}],
            catalog=catalog,
        )


def test_lru_cache_loads_image_once(catalog_with_png_paths, data_dir):
    renderer_module._load_image.cache_clear()
    catalog = Catalog(catalog_with_png_paths)
    placements = [
        {"x": 0, "y": 0, "tile_id": TILE_1},
        {"x": 1, "y": 0, "tile_id": TILE_1},
        {"x": 0, "y": 1, "tile_id": TILE_1},
    ]
    render_map(
        grid_width=3, grid_height=3,
        placements=placements,
        data_dir=str(data_dir),
        catalog=catalog,
    )
    info = renderer_module._load_image.cache_info()
    assert info.hits == 2   # second and third placement hit cache
    assert info.misses == 1  # first placement loads from disk
