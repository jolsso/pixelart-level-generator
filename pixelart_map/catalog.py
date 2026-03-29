from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tiles (
    id           TEXT PRIMARY KEY,
    path         TEXT NOT NULL,
    theme        TEXT NOT NULL,
    map_type     TEXT NOT NULL,
    grid_unit    INTEGER NOT NULL,
    pixel_width  INTEGER NOT NULL,
    pixel_height INTEGER NOT NULL,
    description  TEXT NOT NULL,
    semantic_type TEXT NOT NULL,
    tags         TEXT NOT NULL
);
"""

_INSERT_TILE = """
INSERT OR REPLACE INTO tiles
    (id, path, theme, map_type, grid_unit, pixel_width, pixel_height,
     description, semantic_type, tags)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def open_catalog_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) a catalog SQLite database, ensuring the schema exists."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.row_factory = sqlite3.Row
    return conn


def insert_tile(conn: sqlite3.Connection, tile: dict) -> None:
    conn.execute(
        _INSERT_TILE,
        (
            tile["id"],
            tile["path"],
            tile["theme"],
            tile["map_type"],
            tile["grid_unit"],
            tile["pixel_width"],
            tile["pixel_height"],
            tile["description"],
            tile["semantic_type"],
            json.dumps(tile["tags"]),
        ),
    )


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

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TileInfo":
        return cls(
            id=row["id"],
            path=row["path"],
            theme=row["theme"],
            map_type=row["map_type"],
            grid_unit=row["grid_unit"],
            pixel_width=row["pixel_width"],
            pixel_height=row["pixel_height"],
            description=row["description"],
            semantic_type=row["semantic_type"],
            tags=tuple(json.loads(row["tags"])),
        )


class Catalog:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._tiles: dict[str, TileInfo] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"Catalog not found: {self._path}")
        conn = open_catalog_db(self._path)
        self._tiles = {
            row["id"]: TileInfo.from_row(row)
            for row in conn.execute("SELECT * FROM tiles")
        }
        conn.close()

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
        path = Path(__file__).parent / "catalog.db"
    return Catalog(path)
