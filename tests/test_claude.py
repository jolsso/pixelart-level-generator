import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from PIL import Image

anthropic = pytest.importorskip("anthropic", reason="anthropic package not installed")

from pixelart_map._claude import analyze_tile


@pytest.fixture
def tiny_png(tmp_path) -> Path:
    img = Image.new("RGBA", (48, 48), (100, 150, 200, 255))
    p = tmp_path / "tile.png"
    img.save(p)
    return p


def _mock_response(content: dict) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = json.dumps(content)
    response = MagicMock()
    response.content = [block]
    return response


def test_analyze_tile_returns_dict(tiny_png):
    expected = {
        "description": "A blue tile",
        "semantic_type": "floor",
        "tags": ["blue", "floor"],
    }
    client_mock = MagicMock()
    client_mock.messages.create.return_value = _mock_response(expected)

    with patch("anthropic.Anthropic", return_value=client_mock):
        result = analyze_tile(tiny_png, model="claude-opus-4-6")

    assert result == expected
    client_mock.messages.create.assert_called_once()


def test_analyze_tile_request_format(tiny_png):
    expected = {"description": "x", "semantic_type": "floor", "tags": []}
    client_mock = MagicMock()
    client_mock.messages.create.return_value = _mock_response(expected)

    with patch("anthropic.Anthropic", return_value=client_mock):
        analyze_tile(tiny_png, model="claude-opus-4-6")

    call_kwargs = client_mock.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-6"
    msg = call_kwargs["messages"][0]
    assert msg["role"] == "user"
    image_block = next(b for b in msg["content"] if b["type"] == "image")
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == "image/png"
    assert not image_block["source"]["data"].startswith("data:")


def test_analyze_tile_returns_none_on_bad_json(tiny_png):
    block = MagicMock()
    block.type = "text"
    block.text = "not valid json {"
    response = MagicMock()
    response.content = [block]

    client_mock = MagicMock()
    client_mock.messages.create.return_value = response

    with patch("anthropic.Anthropic", return_value=client_mock):
        result = analyze_tile(tiny_png)

    assert result is None


def test_analyze_tile_returns_none_on_missing_keys(tiny_png):
    client_mock = MagicMock()
    client_mock.messages.create.return_value = _mock_response({"description": "x"})

    with patch("anthropic.Anthropic", return_value=client_mock):
        result = analyze_tile(tiny_png)

    assert result is None


def test_analyze_tile_returns_none_on_api_error(tiny_png):
    client_mock = MagicMock()
    client_mock.messages.create.side_effect = anthropic.APIConnectionError(request=MagicMock())

    with patch("anthropic.Anthropic", return_value=client_mock):
        result = analyze_tile(tiny_png)

    assert result is None


def test_analyze_tile_raises_on_missing_package(tiny_png):
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        with pytest.raises(ImportError, match="pip install"):
            analyze_tile(tiny_png)
