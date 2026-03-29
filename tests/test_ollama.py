import json
import pytest
import httpx
from unittest.mock import patch, MagicMock
from pathlib import Path
from PIL import Image

from pixelart_map._ollama import analyze_tile


@pytest.fixture
def tiny_png(tmp_path) -> Path:
    img = Image.new("RGBA", (48, 48), (200, 100, 50, 255))
    p = tmp_path / "tile.png"
    img.save(p)
    return p


def _mock_response(content: dict) -> MagicMock:
    mock = MagicMock(spec=httpx.Response)
    mock.raise_for_status.return_value = None
    mock.json.return_value = {"message": {"content": json.dumps(content)}}
    return mock


def test_analyze_tile_returns_dict(tiny_png):
    expected = {
        "description": "A red square tile",
        "semantic_type": "floor",
        "tags": ["red", "floor"],
    }
    with patch("httpx.post", return_value=_mock_response(expected)) as mock_post:
        result = analyze_tile(tiny_png, host="http://localhost:11434", model="qwen2-vl")

    assert result == expected
    mock_post.assert_called_once()


def test_analyze_tile_request_format(tiny_png):
    expected = {"description": "x", "semantic_type": "floor", "tags": []}
    with patch("httpx.post", return_value=_mock_response(expected)) as mock_post:
        analyze_tile(tiny_png, host="http://localhost:11434", model="qwen2-vl")

    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
    assert payload["stream"] is False
    assert payload["format"] == "json"
    assert payload["model"] == "qwen2-vl"
    msg = payload["messages"][0]
    assert msg["role"] == "user"
    assert len(msg["images"]) == 1
    # Must be raw base64, not a data-URI
    assert not msg["images"][0].startswith("data:")


def test_analyze_tile_returns_none_on_bad_json(tiny_png):
    mock = MagicMock(spec=httpx.Response)
    mock.raise_for_status.return_value = None
    mock.json.return_value = {"message": {"content": "not valid json {"}}
    with patch("httpx.post", return_value=mock):
        result = analyze_tile(tiny_png, host="http://localhost:11434", model="qwen2-vl")
    assert result is None


def test_analyze_tile_returns_none_on_missing_keys(tiny_png):
    with patch("httpx.post", return_value=_mock_response({"description": "x"})):
        result = analyze_tile(tiny_png, host="http://localhost:11434", model="qwen2-vl")
    assert result is None


def test_analyze_tile_returns_none_on_http_error(tiny_png):
    with patch("httpx.post", side_effect=httpx.RequestError("connection refused")):
        result = analyze_tile(tiny_png, host="http://localhost:11434", model="qwen2-vl")
    assert result is None
