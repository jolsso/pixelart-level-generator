from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path

from tqdm import tqdm

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
_BATCH_SIZE = 1_000
_POLL_INTERVAL = 30  # seconds between batch status checks


def _get_client():
    try:
        import anthropic
        return anthropic.Anthropic()
    except ImportError as exc:
        raise ImportError(
            "anthropic package required for Claude provider. "
            "Install with: pip install 'pixelart_map[claude]'"
        ) from exc


def analyze_tile(
    image_path: Path,
    model: str = "claude-haiku-4-5-20251001",
) -> dict | None:
    """Call the Claude API to describe a tile image. Returns parsed dict or None on failure."""
    client = _get_client()
    image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")

    try:
        response = client.messages.create(
            model=model,
            max_tokens=256,
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


def submit_batch(requests: list[tuple[str, Path]], model: str = "claude-haiku-4-5-20251001") -> str:
    """Submit (custom_id, image_path) pairs as a Batch API job. Returns the batch_id."""
    client = _get_client()
    batch_requests = []
    for custom_id, image_path in requests:
        image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        batch_requests.append({
            "custom_id": custom_id,
            "params": {
                "model": model,
                "max_tokens": 256,
                "messages": [{
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
            },
        })

    batch = client.messages.batches.create(requests=batch_requests)
    return batch.id


def retrieve_batch_results(batch_id: str) -> dict[str, dict | None]:
    """Poll until the batch ends, then return {custom_id: parsed_result | None}."""
    client = _get_client()

    with tqdm(desc=f"Batch {batch_id[:12]}", unit="req") as pbar:
        while True:
            batch = client.messages.batches.retrieve(batch_id)
            counts = batch.request_counts
            total = (
                counts.processing + counts.succeeded
                + counts.errored + counts.canceled + counts.expired
            )
            done = counts.succeeded + counts.errored + counts.canceled + counts.expired
            pbar.total = total
            pbar.n = done
            pbar.refresh()

            if batch.processing_status == "ended":
                break
            time.sleep(_POLL_INTERVAL)

    results: dict[str, dict | None] = {}
    for result in client.messages.batches.results(batch_id):
        cid = result.custom_id
        if result.result.type != "succeeded":
            logger.warning(
                "Batch result for %s: type=%s (not succeeded)",
                cid, result.result.type,
            )
            results[cid] = None
            continue
        msg = result.result.message
        text_blocks = [b for b in msg.content if b.type == "text"]
        if not text_blocks:
            logger.warning(
                "Batch result for %s: no text blocks in response (stop_reason=%s)",
                cid, msg.stop_reason,
            )
            results[cid] = None
            continue
        raw = text_blocks[0].text.strip()
        if not raw:
            logger.warning(
                "Batch result for %s: empty text block (stop_reason=%s)",
                cid, msg.stop_reason,
            )
            results[cid] = None
            continue
        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            parsed = json.loads(raw)
        except Exception as e:
            logger.warning(
                "Batch result for %s: JSON parse failed (%s) — raw: %.200r",
                cid, e, raw,
            )
            results[cid] = None
            continue
        if not _REQUIRED_KEYS.issubset(parsed.keys()):
            logger.warning(
                "Batch result for %s: missing keys %s",
                cid, _REQUIRED_KEYS - parsed.keys(),
            )
            results[cid] = None
            continue
        results[cid] = parsed

    return results
