from __future__ import annotations

import io
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image

from pixelart_map.catalog import Catalog, TileInfo


@dataclass
class RenderResult:
    png_bytes: bytes
    tilemap: list[dict]


@lru_cache(maxsize=256)
def _load_image(abs_path: str) -> Image.Image:
    """Load a tile PNG from disk. Cached by absolute path."""
    return Image.open(abs_path).convert("RGBA")


def render_map(
    grid_width: int,
    grid_height: int,
    placements: list[dict],
    catalog: Catalog | None = None,
    data_dir: str | None = None,
) -> RenderResult:
    # Resolve data_dir
    resolved_data_dir = data_dir or os.environ.get("PIXELART_DATA_DIR")
    if not resolved_data_dir:
        raise ValueError(
            "data_dir must be provided or PIXELART_DATA_DIR env var must be set"
        )
    data_path = Path(resolved_data_dir)

    # Resolve catalog
    if catalog is None:
        from pixelart_map import get_catalog
        catalog = get_catalog()

    # Resolve and validate tiles
    resolved: list[tuple[dict, TileInfo]] = []
    for p in placements:
        tile_id = p["tile_id"]
        try:
            tile = catalog.get_tile(tile_id)
        except KeyError:
            raise ValueError(f"Unknown tile_id: {tile_id!r}")
        resolved.append((p, tile))

    if not resolved:
        canvas = Image.new("RGBA", (grid_width, grid_height), (0, 0, 0, 0))
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        return RenderResult(png_bytes=buf.getvalue(), tilemap=[])

    # Validate consistent map_type
    first_map_type = resolved[0][1].map_type
    for _, tile in resolved:
        if tile.map_type != first_map_type:
            raise ValueError(
                f"map_type mismatch: cannot mix '{first_map_type}' and '{tile.map_type}' tiles"
            )

    grid_unit = resolved[0][1].grid_unit
    canvas = Image.new("RGBA", (grid_width * grid_unit, grid_height * grid_unit), (0, 0, 0, 0))

    tilemap: list[dict] = []
    for placement, tile in resolved:
        abs_path = str((data_path / tile.path).resolve())
        tile_img = _load_image(abs_path)
        canvas.paste(tile_img, (placement["x"] * grid_unit, placement["y"] * grid_unit))
        tilemap.append({
            **placement,
            "theme": tile.theme,
            "map_type": tile.map_type,
            "semantic_type": tile.semantic_type,
            "pixel_width": tile.pixel_width,
            "pixel_height": tile.pixel_height,
        })

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return RenderResult(png_bytes=buf.getvalue(), tilemap=tilemap)
