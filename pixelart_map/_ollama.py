from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (
    "You are analyzing a small pixel art sprite for a top-down 2D game.\n"
    "These are tiny sprites (often 16x16, 32x32, or 48x48 pixels) so details "
    "are stylized and abstract — interpret shapes by what they represent in "
    "the game context, not literally.\n"
    "\n"
    "File path: {rel_path}\n"
    "The folder name tells you the theme (e.g. Kitchen, Halloween, Bathroom). "
    "Use this as strong context — a dark blob in a Halloween folder is likely "
    "a spider or bat, not a generic object.\n"
    "\n"
    "Respond with valid JSON only, no markdown, matching this schema:\n"
    '{{\n'
    '  "description": "<one sentence: what this sprite depicts>",\n'
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
    image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
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
