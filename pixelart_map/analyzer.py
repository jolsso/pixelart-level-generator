from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from tqdm import tqdm

from pixelart_map._filename import parse_exterior_filename
from pixelart_map._ollama import analyze_tile
from pixelart_map._theme import strip_theme_name

logger = logging.getLogger(__name__)

# Subtrees to scan, relative to data_dir
_SCAN_SUBTREES = [
    (
        Path("moderninteriors-win/1_Interiors/48x48/Theme_Sorter_Shadowless_Singles_48x48"),
        "interior",
        48,
    ),
    (
        Path("modernexteriors-win/Modern_Exteriors_16x16/ME_Theme_Sorter_16x16"),
        "exterior",
        16,
    ),
]


def compute_tile_id(relative_path: str) -> str:
    return hashlib.sha256(relative_path.encode()).hexdigest()


def _collect_pngs(data_dir: Path) -> list[tuple[Path, str, int]]:
    """Return list of (abs_path, map_type, grid_unit) for all PNGs in scan subtrees."""
    results = []
    for subtree, map_type, grid_unit in _SCAN_SUBTREES:
        root = data_dir / subtree
        if not root.exists():
            logger.warning("Subtree not found, skipping: %s", root)
            continue
        for png in sorted(root.rglob("*.png")):
            results.append((png, map_type, grid_unit))
    return results


def build_catalog(
    data_dir: Path,
    host: str,
    model: str,
    existing: dict | None = None,
) -> dict:
    """Analyze tiles and return a catalog dict. Pass existing to enable incremental updates."""
    if existing is None:
        existing = {"version": 1, "generated_at": "", "tiles": {}}

    tiles = existing["tiles"].copy()
    pngs = _collect_pngs(data_dir)

    new_tiles = [
        (p, mt, gu) for p, mt, gu in pngs
        if compute_tile_id(str(p.relative_to(data_dir))) not in tiles
    ]

    for abs_path, map_type, grid_unit in tqdm(new_tiles, desc="Analyzing tiles"):
        rel_path = str(abs_path.relative_to(data_dir))
        tile_id = compute_tile_id(rel_path)
        theme = strip_theme_name(abs_path.parent.name)

        with Image.open(abs_path) as img:
            pixel_width, pixel_height = img.size

        # Try filename-based extraction first (exterior tiles only)
        result = parse_exterior_filename(abs_path.stem, theme)
        if result is None:
            result = analyze_tile(abs_path, host=host, model=model)
        if result is None:
            logger.warning("Skipping tile (analysis failed): %s", rel_path)
            continue

        tiles[tile_id] = {
            "id": tile_id,
            "path": rel_path,
            "theme": theme,
            "map_type": map_type,
            "grid_unit": grid_unit,
            "pixel_width": pixel_width,
            "pixel_height": pixel_height,
            "description": result["description"],
            "semantic_type": result["semantic_type"],
            "tags": result["tags"],
        }

    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tiles": tiles,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze pixel art tiles and build catalog.json")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("PIXELART_DATA_DIR", "./data"),
        help="Root path of the pixel art asset folder (default: ./data or PIXELART_DATA_DIR)",
    )
    parser.add_argument(
        "--output",
        default="catalog.json",
        help="Output path for catalog.json (default: catalog.json)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        help="Ollama server URL",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", "qwen2.5vl:7b"),
        help="Ollama model name",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_path = Path(args.output)

    existing = None
    if output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        print(f"Loaded existing catalog: {len(existing['tiles'])} tiles")

    catalog = build_catalog(data_dir=data_dir, host=args.host, model=args.model, existing=existing)

    output_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(catalog['tiles'])} tiles to {output_path}")


if __name__ == "__main__":
    main()
