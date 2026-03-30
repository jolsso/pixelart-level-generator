import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import httpx
from pixelart_map.analyzer import build_catalog, compute_tile_id, _list_ollama_models, _pick_model


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

        existing_ids = set(catalog1["tiles"].keys())
        catalog2 = build_catalog(
            data_dir=tmp_path,
            host="http://localhost:11434",
            model="qwen2-vl",
            existing_ids=existing_ids,
        )
        assert mock_analyze.call_count == 3  # unchanged


def test_build_catalog_resolution_filter(tmp_path):
    make_asset_tree(tmp_path)
    with patch("pixelart_map.analyzer.analyze_tile", side_effect=_fake_analyze):
        catalog = build_catalog(
            data_dir=tmp_path,
            host="http://localhost:11434",
            model="qwen2-vl",
            resolution=48,
        )

    tiles = list(catalog["tiles"].values())
    assert all(t["grid_unit"] == 48 for t in tiles)
    assert len(tiles) == 2  # interior 48x48 and 48x96; exterior 16x16 excluded


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


# ---------------------------------------------------------------------------
# Model picker
# ---------------------------------------------------------------------------

def _mock_tags(models: list[str]) -> MagicMock:
    mock = MagicMock(spec=httpx.Response)
    mock.raise_for_status.return_value = None
    mock.json.return_value = {"models": [{"name": m} for m in models]}
    return mock


def test_list_ollama_models_returns_names():
    with patch("httpx.get", return_value=_mock_tags(["qwen2.5vl:7b", "llava:13b"])):
        models = _list_ollama_models("http://localhost:11434")
    assert models == ["qwen2.5vl:7b", "llava:13b"]


def test_list_ollama_models_returns_empty_on_error():
    with patch("httpx.get", side_effect=httpx.RequestError("refused")):
        models = _list_ollama_models("http://localhost:11434")
    assert models == []


def test_pick_model_unreachable_returns_default():
    with patch("pixelart_map.analyzer._list_ollama_models", return_value=[]):
        result = _pick_model("http://localhost:11434", "qwen2.5vl:7b")
    assert result == "qwen2.5vl:7b"


def test_pick_model_single_installed_auto_selects():
    with patch("pixelart_map.analyzer._list_ollama_models", return_value=["llava:7b"]):
        result = _pick_model("http://localhost:11434", "qwen2.5vl:7b")
    assert result == "llava:7b"


def test_pick_model_multiple_user_picks_by_number():
    models = ["qwen2.5vl:7b", "llava:13b", "mistral:7b"]
    with patch("pixelart_map.analyzer._list_ollama_models", return_value=models):
        with patch("builtins.input", return_value="2"):
            result = _pick_model("http://localhost:11434", "qwen2.5vl:7b")
    assert result == "llava:13b"


def test_pick_model_multiple_enter_returns_default():
    models = ["qwen2.5vl:7b", "llava:13b"]
    with patch("pixelart_map.analyzer._list_ollama_models", return_value=models):
        with patch("builtins.input", return_value=""):
            result = _pick_model("http://localhost:11434", "qwen2.5vl:7b")
    assert result == "qwen2.5vl:7b"


def test_pick_model_invalid_then_valid_input():
    models = ["qwen2.5vl:7b", "llava:13b"]
    with patch("pixelart_map.analyzer._list_ollama_models", return_value=models):
        with patch("builtins.input", side_effect=["99", "abc", "1"]):
            result = _pick_model("http://localhost:11434", "qwen2.5vl:7b")
    assert result == "qwen2.5vl:7b"
