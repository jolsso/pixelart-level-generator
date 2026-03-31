from __future__ import annotations

import base64
import io
import json
import logging
import time
from pathlib import Path

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (
    "Classify this pixel art sprite: {filename}\n"
    "\n"
    "Reply with JSON only:\n"
    '{{\n'
    '  "description": "<specific object name>",\n'
    '  "type": "<floor|wall|object|terrain>",\n'
    '  "passable": <true|false>,\n'
    '  "tags": ["<tag>", ...],\n'
    '  "confidence": <0.0-1.0>\n'
    '}}'
)

_REQUIRED_KEYS = {"description", "semantic_type", "tags"}
_RETRIES = 2
_RETRY_DELAY = 10.0  # seconds — gives Ollama time to recover after a crash


def analyze_tile(
    image_path: Path,
    host: str = "http://localhost:11434",
    model: str = "qwen2.5vl:7b",
    rel_path: str = "",
) -> dict | None:
    """Call Ollama to describe a tile image. Returns parsed dict or None on failure.

    Retries up to _RETRIES times on transient errors (500s, connection drops)
    with a fixed delay, so Ollama has time to recover from memory pressure.
    """
    filename = Path(rel_path).name if rel_path else image_path.name
    prompt = _PROMPT_TEMPLATE.format(filename=filename)

    # Upscale small pixel art so the vision model has more detail to work with.
    # Uses nearest-neighbor to preserve crisp pixel edges.
    _MIN_SIDE = 256
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
    for attempt in range(1 + _RETRIES):
        try:
            response = httpx.post(f"{host}/api/chat", json=payload, timeout=60.0)
            response.raise_for_status()
            raw = response.json()["message"]["content"]
            result = json.loads(raw)
        except Exception as e:
            if attempt < _RETRIES:
                logger.warning(
                    "Ollama call failed for %s (attempt %d/%d): %s — retrying in %.0fs",
                    image_path, attempt + 1, 1 + _RETRIES, e, _RETRY_DELAY,
                )
                time.sleep(_RETRY_DELAY)
                continue
            logger.warning("Ollama call failed for %s: %s", image_path, e)
            return None

        # Normalize: prompt uses "type" but internal schema uses "semantic_type"
        if "type" in result:
            result["semantic_type"] = result.pop("type")

        if not _REQUIRED_KEYS.issubset(result.keys()):
            logger.warning("Ollama response missing keys for %s: %s", image_path, result)
            return None

        return result

    return None  # unreachable, satisfies type checker
