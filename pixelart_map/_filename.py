"""
Filename-based metadata extraction for exterior tiles.

Three filename patterns exist in the asset pack:

  Pattern 1 (themes 1-20, ~5 400 files):
      ME_Singles_{Theme}_{NNxNN}_{ObjectWords}[_{N}].png

  Pattern 2 (themes 21-23, ~670 files):
      {N}_{Theme}_{NNxNN}_{ObjectWords}.png

  Pattern 3 (theme 24, ~220 files):
      {N}_{Theme}_{ObjectWords}_{NNxNN}.png   (resolution suffix, no object after it)

All three let us derive description, semantic_type, and tags from the filename
alone, skipping the Ollama vision call for all ~6 000 exterior tiles.
Interior tiles use a bare {Theme}_{N}.png pattern with no object info and
always fall through to Ollama.
"""
from __future__ import annotations

import re

_EXTERIOR_PREFIX = re.compile(r"^ME_Singles_", re.IGNORECASE)
_NUMERIC_PREFIX = re.compile(r"^\d+_")
_RESOLUTION_MID = re.compile(r"_\d+x\d+_")   # resolution with object words after
_RESOLUTION_END = re.compile(r"_\d+x\d+$")    # resolution at end of stem
_TRAILING_NUMBER = re.compile(r"_\d+$")

# Words to drop when building tags (non-informative noise)
_STOP_WORDS = {"variation", "and", "the", "of", "a", "an"}

# Keyword → semantic_type mapping (first match wins)
_SEMANTIC_KEYWORDS: list[tuple[str, list[str]]] = [
    ("vehicle",    ["car", "truck", "bus", "ambulance", "boat", "van", "motorcycle",
                    "bicycle", "train", "vehicle", "tram"]),
    ("building",   ["building", "condo", "house", "shop", "store", "station", "office",
                    "church", "tower", "roof", "facade", "villa", "hotel", "hospital",
                    "school", "garage", "factory"]),
    ("wall",       ["wall", "fence", "gate", "barrier", "railing", "border", "hedge",
                    "door", "window"]),
    ("terrain",    ["grass", "dirt", "sand", "water", "deep", "shallow", "cliff", "rock",
                    "mud", "snow", "ice", "terrain", "tree", "bush", "forest", "shore",
                    "ground", "soil"]),
    ("floor",      ["floor", "asphalt", "pavement", "road", "path", "carpet", "sidewalk",
                    "tile", "court", "track"]),
    ("furniture",  ["bench", "chair", "desk", "table", "bed", "sofa", "shelf", "counter",
                    "cabinet", "locker"]),
    ("decoration", ["flower", "plant", "pot", "fountain", "statue", "sign", "banner",
                    "flag", "light", "lamp", "lantern"]),
    ("prop",       ["barrel", "atm", "antenna", "post", "trash", "bin", "box", "crate",
                    "cone", "hydrant", "mailbox", "dumpster", "cart", "ball", "net"]),
]


def parse_exterior_filename(stem: str, theme: str) -> dict | None:
    """Parse an exterior tile filename stem into catalog metadata.

    Returns a dict with description/semantic_type/tags, or None if the
    filename does not match any known exterior pattern (falls back to Ollama).

    Examples:
        'ME_Singles_School_16x16_Basketball_Ball_1', 'School'
        → description: 'Basketball ball, top-down view'
        → semantic_type: 'prop'
        → tags: ['basketball', 'ball', 'school']

        '21_Beach_16x16_Beach_Sign', 'Beach'
        → description: 'Beach sign, top-down view'
        → semantic_type: 'prop'
        → tags: ['beach', 'sign']

        '24_Additional_Houses_Country_House_16x16', 'Additional_Houses'
        → description: 'Country house, top-down view'
        → semantic_type: 'building'
        → tags: ['country', 'house', 'additional', 'houses']
    """
    object_part = _extract_object_part(stem, theme)
    if object_part is None:
        return None

    # Build description from the object words
    object_words = object_part.replace("_", " ").strip()
    description = f"{object_words}, top-down view"

    # Object tags — used for semantic type inference (theme words excluded)
    object_tags: list[str] = []
    seen: set[str] = set()
    for word in object_part.lower().split("_"):
        if word and not word.isdigit() and word not in _STOP_WORDS and len(word) > 1:
            if word not in seen:
                object_tags.append(word)
                seen.add(word)

    # Full tags: object words + theme words (for search/filter)
    tags = list(object_tags)
    for word in theme.lower().split("_"):
        if word and not word.isdigit() and word not in _STOP_WORDS and len(word) > 1:
            if word not in seen:
                tags.append(word)
                seen.add(word)

    semantic_type = _infer_semantic_type(object_tags)

    return {
        "description": description,
        "semantic_type": semantic_type,
        "tags": tags,
        "confidence": 1.0,
        "reasoning": "parsed from filename",
        "layer": "object",
        "passable": semantic_type in ("floor", "terrain"),
    }


def _extract_object_part(stem: str, theme: str) -> str | None:
    """Return the object_part string for a stem, or None if not a known exterior pattern."""

    # Pattern 1: ME_Singles_{Theme}_{NNxNN}_{ObjectWords}[_{N}]
    if _EXTERIOR_PREFIX.match(stem):
        m = _RESOLUTION_MID.search(stem)
        if not m:
            return None
        part = stem[m.end():]
        if not part:
            return None
        return _TRAILING_NUMBER.sub("", part) or None

    # Patterns 2 & 3: {N}_{Theme}_...
    if not _NUMERIC_PREFIX.match(stem):
        return None

    # Pattern 2: {N}_{Theme}_{NNxNN}_{ObjectWords}
    m = _RESOLUTION_MID.search(stem)
    if m:
        part = stem[m.end():]
        if not part:
            return None
        return _TRAILING_NUMBER.sub("", part) or None

    # Pattern 3: {N}_{Theme}_{ObjectWords}_{NNxNN}  (resolution suffix)
    if _RESOLUTION_END.search(stem):
        # Strip leading number
        body = _NUMERIC_PREFIX.sub("", stem)
        # Strip resolution suffix
        body = _RESOLUTION_END.sub("", body)
        # Strip theme prefix (case-insensitive) to isolate object words
        theme_prefix = re.escape(theme) + "_"
        body = re.sub(f"^{theme_prefix}", "", body, flags=re.IGNORECASE)
        return body or None

    return None


def _infer_semantic_type(tags: list[str]) -> str:
    tag_set = set(tags)
    for semantic_type, keywords in _SEMANTIC_KEYWORDS:
        if tag_set & set(keywords):
            return semantic_type
    return "prop"
