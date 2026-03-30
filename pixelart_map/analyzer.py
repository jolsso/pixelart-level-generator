from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
from collections.abc import Callable
from pathlib import Path

from PIL import Image
from tqdm import tqdm

from pixelart_map._filename import parse_exterior_filename
from pixelart_map._ollama import analyze_tile
from pixelart_map._theme import strip_theme_name
from pixelart_map.catalog import insert_tile, open_catalog_db

logger = logging.getLogger(__name__)

_RESOLUTION_RE = re.compile(r"(\d+)x\d+")


def compute_tile_id(relative_path: str) -> str:
    return hashlib.sha256(relative_path.encode()).hexdigest()


def _grid_unit_from_path(path: Path) -> int | None:
    """Extract grid unit (e.g. 16, 32, 48) from the first NNxNN token in a path."""
    for part in path.parts:
        m = _RESOLUTION_RE.search(part)
        if m:
            return int(m.group(1))
    return None


def _collect_pngs(data_dir: Path, resolution: int | None = None) -> list[tuple[Path, str, int]]:
    """Return list of (abs_path, map_type, grid_unit) for all singles PNGs.

    Interior: all Theme_Sorter_Shadowless_Singles subtrees (16x16, 32x32, 48x48).
    Exterior: all ME_Theme_Sorter subtrees (16x16, 32x32, 48x48); root-level
              spritesheets directly inside ME_Theme_Sorter are skipped.

    Args:
        resolution: If set, only collect tiles whose grid_unit matches this value.
    """
    results: list[tuple[Path, str, int]] = []

    # ── Interiors: Shadowless Singles at every available resolution ──────────
    interiors_root = data_dir / "moderninteriors-win" / "1_Interiors"
    if not interiors_root.exists():
        logger.warning("Interior root not found: %s", interiors_root)
    else:
        for res_dir in sorted(interiors_root.iterdir()):
            if not res_dir.is_dir():
                continue
            grid_unit = _grid_unit_from_path(res_dir)
            if grid_unit is None:
                continue
            if resolution is not None and grid_unit != resolution:
                continue
            for variant_dir in sorted(res_dir.iterdir()):
                if not variant_dir.is_dir():
                    continue
                vname = variant_dir.name.lower()
                if "shadowless" in vname and "singles" in vname:
                    for png in sorted(variant_dir.rglob("*.png")):
                        results.append((png, "interior", grid_unit))
                    break  # only one shadowless-singles variant per resolution

    # ── Exteriors: ME_Theme_Sorter at every available resolution ─────────────
    exteriors_root = data_dir / "modernexteriors-win"
    if not exteriors_root.exists():
        logger.warning("Exterior root not found: %s", exteriors_root)
    else:
        for res_dir in sorted(exteriors_root.iterdir()):
            if not res_dir.is_dir() or not res_dir.name.startswith("Modern_Exteriors_"):
                continue
            grid_unit = _grid_unit_from_path(res_dir)
            if grid_unit is None:
                continue
            if resolution is not None and grid_unit != resolution:
                continue
            for sub in sorted(res_dir.iterdir()):
                if not sub.is_dir() or not sub.name.startswith("ME_Theme_Sorter_"):
                    continue
                for png in sorted(sub.rglob("*.png")):
                    # Skip root-level spritesheets (PNGs directly in ME_Theme_Sorter_NNxNN)
                    if png.parent == sub:
                        continue
                    results.append((png, "exterior", grid_unit))
                break  # only one ME_Theme_Sorter per resolution dir

    return results


def build_catalog(
    data_dir: Path,
    host: str,
    model: str,
    existing_ids: set[str] | None = None,
    on_tile: Callable[[dict], None] | None = None,
    resolution: int | None = None,
) -> dict:
    """Analyze tiles and return a catalog dict.

    Args:
        existing_ids: Set of tile IDs already in the catalog — those tiles are skipped.
        on_tile: Optional callback invoked with each new tile dict as it is analyzed.
                 Use this for incremental persistence (e.g. write to SQLite per tile).
        resolution: If set, only analyze tiles with this grid_unit (e.g. 48).
    """
    if existing_ids is None:
        existing_ids = set()

    pngs = _collect_pngs(data_dir, resolution=resolution)
    new_pngs = [
        (p, mt, gu) for p, mt, gu in pngs
        if compute_tile_id(str(p.relative_to(data_dir))) not in existing_ids
    ]

    tiles: dict[str, dict] = {}

    for abs_path, map_type, grid_unit in tqdm(new_pngs, desc="Analyzing tiles"):
        rel_path = str(abs_path.relative_to(data_dir))
        tile_id = compute_tile_id(rel_path)
        theme = strip_theme_name(abs_path.parent.name)

        with Image.open(abs_path) as img:
            pixel_width, pixel_height = img.size

        result = parse_exterior_filename(abs_path.stem, theme)
        if result is None:
            result = analyze_tile(abs_path, host=host, model=model)
        if result is None:
            logger.warning("Skipping tile (analysis failed): %s", rel_path)
            continue

        tile = {
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
        tiles[tile_id] = tile
        if on_tile is not None:
            on_tile(tile)

    return {"tiles": tiles}


def _list_ollama_models(host: str) -> list[str]:
    """Return installed Ollama model names, or [] if Ollama is unreachable."""
    import httpx
    try:
        response = httpx.get(f"{host}/api/tags", timeout=5.0)
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]
    except Exception as e:
        logger.debug("Could not reach Ollama at %s: %s", host, e)
        return []


def _pick_model(host: str, default: str) -> str:
    """Interactively pick an installed Ollama model, or fall back to default."""
    models = _list_ollama_models(host)

    if not models:
        print(f"Could not reach Ollama — using model: {default}")
        return default

    if len(models) == 1:
        print(f"Using installed model: {models[0]}")
        return models[0]

    print("\nInstalled Ollama models:")
    for i, name in enumerate(models, 1):
        print(f"  {i}) {name}")
    print(f"  (default: {default})")

    while True:
        raw = input(f"Pick a model [1-{len(models)}, or Enter for default]: ").strip()
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(models):
            return models[int(raw) - 1]
        print(f"  Enter a number between 1 and {len(models)}, or press Enter.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze pixel art tiles and build catalog.db")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("PIXELART_DATA_DIR", "./data"),
        help="Root path of the pixel art asset folder (default: ./data or PIXELART_DATA_DIR)",
    )
    parser.add_argument(
        "--output",
        default="catalog.db",
        help="Output path for catalog.db (default: catalog.db)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        help="Ollama server URL",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Ollama model name (default: auto-picked from installed models)",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        default=48,
        metavar="N",
        help="Only analyze tiles at this grid unit size in pixels (default: 48). "
             "Pass 0 to scan all resolutions.",
    )
    args = parser.parse_args()

    host = args.host
    fallback = os.environ.get("OLLAMA_MODEL", "qwen2.5vl:7b")
    model = args.model if args.model is not None else _pick_model(host, fallback)

    data_dir = Path(args.data_dir)
    db_path = Path(args.output)

    conn = open_catalog_db(db_path)
    existing_ids = {row[0] for row in conn.execute("SELECT id FROM tiles")}
    if existing_ids:
        print(f"Resuming from existing catalog: {len(existing_ids):,} tiles already analyzed")

    def _write_tile(tile: dict) -> None:
        insert_tile(conn, tile)
        conn.commit()

    resolution = args.resolution if args.resolution != 0 else None

    build_catalog(
        data_dir=data_dir,
        host=host,
        model=model,
        existing_ids=existing_ids,
        on_tile=_write_tile,
        resolution=resolution,
    )

    total = conn.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]
    conn.close()
    print(f"catalog.db contains {total:,} tiles → {db_path}")


if __name__ == "__main__":
    main()
