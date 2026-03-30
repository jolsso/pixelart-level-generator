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
    "You are classifying a pixel art sprite for a searchable level-design catalog.\n"
    "\n"
    "## Context\n"
    "- Source path: {rel_path}\n"
    "- The folder name is the tileset theme — use it to resolve ambiguity "
    "(e.g. 'dungeon/chest.png' → dungeon chest, not a beach chest).\n"
    "- The sprite is shown upscaled. Pixel clusters and color patterns matter "
    "more than fine detail.\n"
    "\n"
    "## Your task\n"
    "First, reason briefly about what you see:\n"
    "- What shapes and colors are dominant?\n"
    "- What does the folder/filename suggest?\n"
    "- Is it a flat tile (base layer) or a raised object (object layer)?\n"
    "\n"
    "Then output a single JSON object. Rules:\n"
    "- `description`: 2–5 words naming the exact object. "
    "Never write 'tile', 'sprite', or 'pixel art'. "
    "Good: 'stone dungeon floor', 'wooden treasure chest'. "
    "Bad: 'floor tile', 'decorative object'.\n"
    "- `semantic_type`: pick exactly one — "
    "floor | wall | door | water | terrain | vegetation | "
    "furniture | container | light | hazard | prop | building | vehicle | ui\n"
    "- `layer`: 'base' if it tiles flat on the ground, "
    "'object' if it sits on top of a base tile, 'overlay' if it goes above objects\n"
    "- `passable`: true if a character can walk over it, false if it blocks movement\n"
    "- `tags`: 3–8 words a designer would search. Include material, style, "
    "color if distinctive, and theme. No plurals, lowercase only.\n"
    "- `confidence`: 0.9+ only if unmistakable, 0.6–0.89 if plausible, "
    "below 0.6 if the sprite is too small or ambiguous to be certain.\n"
    "\n"
    "Respond with valid JSON only — no markdown, no commentary:\n"
    '{{\n'
    '  "reasoning": "<one sentence: what you see and why you chose this classification>",\n'
    '  "description": "<2–5 word specific name>",\n'
    '  "semantic_type": "<type>",\n'
    '  "layer": "<base|object|overlay>",\n'
    '  "passable": <true|false>,\n'
    '  "tags": ["<tag>", ...],\n'
    '  "confidence": <0.0–1.0>\n'
    '}}'
)

_REQUIRED_KEYS = {"reasoning", "description", "semantic_type", "layer", "passable", "tags", "confidence"}


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
