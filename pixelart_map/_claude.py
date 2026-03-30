from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

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


def analyze_tile(
    image_path: Path,
    model: str = "claude-opus-4-6",
) -> dict | None:
    """Call the Claude API to describe a tile image. Returns parsed dict or None on failure.

    Requires ANTHROPIC_API_KEY in the environment. The anthropic package must be
    installed: pip install 'pixelart_map[claude]'
    """
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            "anthropic package required for Claude provider. "
            "Install with: pip install 'pixelart_map[claude]'"
        ) from exc

    image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }],
        )
        raw = next(b.text for b in response.content if b.type == "text")
        result = json.loads(raw)
    except Exception as e:
        logger.warning("Claude API call failed for %s: %s", image_path, e)
        return None

    if not _REQUIRED_KEYS.issubset(result.keys()):
        logger.warning("Claude response missing keys for %s: %s", image_path, result)
        return None

    return result
