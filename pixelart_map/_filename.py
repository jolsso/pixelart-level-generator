"""
Filename-based metadata extraction for exterior tiles.

Exterior tiles follow the pattern:
    ME_Singles_{Theme}_16x16_{ObjectWords}_{N}.png

This lets us derive description, semantic_type, and tags from the filename
alone, skipping the Ollama vision call for the ~6000 exterior tiles.
Interior tiles use a bare {Theme}_{N}.png pattern with no object info,
so they always fall through to Ollama.
"""
from __future__ import annotations

import re

_EXTERIOR_PREFIX = re.compile(r"^ME_Singles_", re.IGNORECASE)
_RESOLUTION = re.compile(r"_\d+x\d+_")
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
    filename does not match the exterior ME_Singles pattern (falls back
    to Ollama).

    Examples:
        'ME_Singles_School_16x16_Basketball_Ball_1', 'School'
        → description: 'Basketball ball, top-down view'
        → semantic_type: 'prop'
        → tags: ['basketball', 'ball', 'school']

        'ME_Singles_City_Props_16x16_Antenna', 'City_Props'
        → description: 'Antenna, top-down view'
        → semantic_type: 'prop'
        → tags: ['antenna', 'city', 'props']
    """
    if not _EXTERIOR_PREFIX.match(stem):
        return None

    # Locate the _NNxNN_ separator
    m = _RESOLUTION.search(stem)
    if not m:
        return None

    object_part = stem[m.end():]
    if not object_part:
        return None

    # Strip trailing variant number (_1, _27, etc.)
    object_part = _TRAILING_NUMBER.sub("", object_part)

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
    }


def _infer_semantic_type(tags: list[str]) -> str:
    tag_set = set(tags)
    for semantic_type, keywords in _SEMANTIC_KEYWORDS:
        if tag_set & set(keywords):
            return semantic_type
    return "prop"
