from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_PROMPT = (
    "You are analyzing a pixel art tile for a top-down 2D game.\n"
    "Respond with valid JSON only, no markdown, matching this schema:\n"
    '{\n'
    '  "description": "<one sentence: what this tile depicts>",\n'
    '  "semantic_type": "<one of: floor, wall, furniture, decoration, terrain, prop, building, vehicle>",\n'
    '  "tags": ["<keyword>", ...]\n'
    '}'
)

_REQUIRED_KEYS = {"description", "semantic_type", "tags"}
_RETRIES = 2
_RETRY_DELAY = 10.0  # seconds — gives Ollama time to recover after a crash


def analyze_tile(
    image_path: Path,
    host: str = "http://localhost:11434",
    model: str = "qwen2.5vl:7b",
) -> dict | None:
    """Call Ollama to describe a tile image. Returns parsed dict or None on failure.

    Retries up to _RETRIES times on transient errors (500s, connection drops)
    with a fixed delay, so Ollama has time to recover from memory pressure.
    """
    image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [{
            "role": "user",
            "content": _PROMPT,
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

        if not _REQUIRED_KEYS.issubset(result.keys()):
            logger.warning("Ollama response missing keys for %s: %s", image_path, result)
            return None

        return result

    return None  # unreachable, satisfies type checker
