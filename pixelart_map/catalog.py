from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TileInfo:
    id: str
    path: str
    theme: str
    map_type: str
    grid_unit: int
    pixel_width: int
    pixel_height: int
    description: str
    semantic_type: str
    tags: tuple[str, ...]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TileInfo":
        return cls(
            id=d["id"],
            path=d["path"],
            theme=d["theme"],
            map_type=d["map_type"],
            grid_unit=d["grid_unit"],
            pixel_width=d["pixel_width"],
            pixel_height=d["pixel_height"],
            description=d["description"],
            semantic_type=d["semantic_type"],
            tags=tuple(d["tags"]),
        )


class Catalog:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._tiles: dict[str, TileInfo] = {}
        self._load()

    def _load(self) -> None:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        self._tiles = {
            tile_id: TileInfo.from_dict(tile_data)
            for tile_id, tile_data in data.get("tiles", {}).items()
        }

    def get_tile(self, tile_id: str) -> TileInfo:
        return self._tiles[tile_id]

    def themes(self) -> list[str]:
        return sorted({t.theme for t in self._tiles.values()})

    def map_types(self) -> list[str]:
        return sorted({t.map_type for t in self._tiles.values()})

    def tiles_by_theme(self, theme: str) -> list[TileInfo]:
        return [t for t in self._tiles.values() if t.theme == theme]

    def tiles_by_map_type(self, map_type: str) -> list[TileInfo]:
        return [t for t in self._tiles.values() if t.map_type == map_type]

    def tiles_by_semantic_type(self, semantic_type: str) -> list[TileInfo]:
        return [t for t in self._tiles.values() if t.semantic_type == semantic_type]

    def search(self, query: str) -> list[TileInfo]:
        q = query.lower()
        return [
            t for t in self._tiles.values()
            if q in t.description.lower() or any(q in tag.lower() for tag in t.tags)
        ]


def get_catalog() -> Catalog:
    path = os.environ.get("PIXELART_CATALOG_PATH")
    if path is None:
        path = Path(__file__).parent / "catalog.json"
    return Catalog(path)
