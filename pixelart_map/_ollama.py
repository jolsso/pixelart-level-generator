from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (
    "This is a pixel art sprite from a top-down 2D game, shown upscaled.\n"
    "File path: {rel_path}\n"
    "The folder name indicates the theme.\n"
    "\n"
    "This will be stored in a searchable catalog for a game designer "
    "building levels. Be specific — name the exact object, not a generic "
    "category. Tags should be words a designer would search for.\n"
    "\n"
    "Respond with valid JSON only, no markdown:\n"
    '{{\n'
    '  "description": "<name the specific object>",\n'
    '  "semantic_type": "<one of: floor, wall, furniture, decoration, terrain, prop, building, vehicle>",\n'
    '  "tags": ["<keyword>", ...],\n'
    '  "confidence": <float 0.0-1.0: how confident you are in this classification>\n'
    '}}'
)

_REQUIRED_KEYS = {"description", "semantic_type", "tags", "confidence"}


def analyze_tile(
    image_path: Path,
    host: str = "http://localhost:11434",
    model: str = "qwen2.5vl:7b",
    rel_path: str = "",
) -> dict | None:
    """Call Ollama to describe a tile image. Returns parsed dict or None on failure."""
    prompt = _PROMPT_TEMPLATE.format(rel_path=rel_path or image_path.name)

    # Upscale small pixel art so the vision model has more detail to work with.
    # Uses nearest-neighbor to preserve crisp pixel edges.
    _MIN_SIDE = 512
    with Image.open(image_path) as img:
        w, h = img.size
        scale = max(1, _MIN_SIDE // min(w, h))
        if scale > 1:
            img = img.resize((w * scale, h * scale), Image.NEAREST)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [{
            "role": "user",
            "content": prompt,
            "images": [image_b64],
        }],
    }
    try:
        response = httpx.post(f"{host}/api/chat", json=payload, timeout=60.0)
        response.raise_for_status()
        raw = response.json()["message"]["content"]
        result = json.loads(raw)
    except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Ollama call failed for %s: %s", image_path, e)
        return None

    if not _REQUIRED_KEYS.issubset(result.keys()):
        logger.warning("Ollama response missing keys for %s: %s", image_path, result)
        return None

    return result
