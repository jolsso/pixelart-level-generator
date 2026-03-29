# pixelart_map — Design Spec

**Date:** 2026-03-29
**Status:** Approved

## Summary

`pixelart_map` is a Python package that serves two purposes:

1. **Offline catalog builder** — analyzes pixel art tile assets using a local Ollama vision model (Qwen2-VL) and produces a `catalog.json` artifact describing every tile.
2. **Runtime library** — provides a query interface over the catalog and a Pillow-based renderer that composites tile placements into PNG images.

The package is consumed by a separate game engine project. The game engine owns all LLM-based map generation logic, user-facing HTTP endpoints, and game state. This package has no HTTP server.

---

## Scope

**In scope:**
- Analyzer CLI that scans `data/` and calls Ollama to describe each tile
- `catalog.json` schema and the query API over it
- `render_map()` — composites a grid of tile placements into a PNG

**Out of scope:**
- LLM map generation (lives in the game engine)
- HTTP API / web server
- Game state, player logic, authentication

---

## Repository Structure

```
pixelart-level-generator/
├── data/                          # unversioned pixel art assets (gitignored)
│   ├── moderninteriors-win/       # interior tiles, 48×48px
│   └── modernexteriors-win/       # exterior tiles, 16×16px
├── pixelart_map/
│   ├── __init__.py                # public API: get_catalog, render_map
│   ├── analyzer.py                # CLI: scans data/, calls Ollama, writes catalog.json
│   ├── catalog.py                 # loads catalog.json, TileInfo dataclass, query methods
│   └── renderer.py                # Pillow compositor
├── catalog.json                   # committed build artifact — updated when assets change
├── pyproject.toml
└── .gitignore                     # excludes data/
```

---

## 1. Analyzer

**Invocation:** `python -m pixelart_map.analyzer [--data-dir ./data]`

### Behavior

1. Walks `data/` recursively, collecting all `.png` files.
2. Loads existing `catalog.json` (empty dict if not present).
3. For each PNG whose SHA-256 path hash is not already in the catalog:
   - Derives `theme`, `map_type`, and `tile_size` from the folder path (no LLM needed — folder names are semantic).
   - Base64-encodes the image.
   - POSTs to Ollama chat API with the image and a structured prompt requesting JSON with `description`, `semantic_type`, and `tags`.
   - Appends the result to the catalog dict.
4. Writes updated `catalog.json`.
5. Displays progress with `tqdm`. Skips already-analyzed tiles so re-runs are incremental.

### Path-derived fields

| Field | Derivation |
|---|---|
| `map_type` | `"interior"` if path contains `moderninteriors`, else `"exterior"` |
| `tile_size` | `48` if path contains `48x48`, `16` if `16x16` |
| `theme` | Folder name of the deepest theme directory (e.g. `Classroom_and_Library`) |

### Ollama prompt (structured output)

```
You are analyzing a pixel art tile for a top-down 2D game.
Respond with valid JSON only, no markdown, matching this schema:
{
  "description": "<one sentence: what this tile depicts>",
  "semantic_type": "<one of: floor, wall, furniture, decoration, terrain, prop, building, vehicle>",
  "tags": ["<keyword>", ...]
}
```

---

## 2. Catalog

### catalog.json schema

```json
{
  "version": 1,
  "generated_at": "<ISO8601 timestamp>",
  "tiles": {
    "<tile_id>": {
      "id": "<SHA-256 of relative path, first 16 chars>",
      "path": "<relative path from data/ root>",
      "theme": "Classroom_and_Library",
      "map_type": "interior",
      "tile_size": 48,
      "description": "School desk with chair, wooden, top-down view",
      "semantic_type": "furniture",
      "tags": ["desk", "chair", "school", "wooden"]
    }
  }
}
```

### Python query API (`catalog.py`)

```python
from pixelart_map import get_catalog

catalog = get_catalog()  # loads catalog.json from package root or PIXELART_CATALOG_PATH

catalog.themes() -> List[str]
catalog.map_types() -> List[str]  # ["interior", "exterior"]
catalog.tiles_by_theme(theme: str) -> List[TileInfo]
catalog.tiles_by_map_type(map_type: str) -> List[TileInfo]
catalog.tiles_by_semantic_type(semantic_type: str) -> List[TileInfo]
catalog.search(query: str) -> List[TileInfo]  # searches description + tags (case-insensitive substring)
catalog.get_tile(tile_id: str) -> TileInfo
```

`TileInfo` is a dataclass mirroring the JSON schema above.

---

## 3. Renderer

### API

```python
from pixelart_map import render_map

result = render_map(
    grid_width=10,
    grid_height=10,
    placements=[
        {"x": 0, "y": 0, "tile_id": "abc123"},
        {"x": 1, "y": 0, "tile_id": "def456"},
        ...
    ],
    data_dir="./data"  # or omit to use PIXELART_DATA_DIR env var
)

result.png_bytes: bytes        # PNG-encoded composited image
result.tilemap: List[dict]     # echo of placements with resolved TileInfo metadata
```

### Behavior

1. Resolves each `tile_id` via the catalog. Raises `ValueError` for unknown IDs.
2. Validates all tiles share the same `map_type`. Raises `ValueError` on mismatch (no interior/exterior mixing).
3. Determines `tile_size` from the first resolved tile.
4. Creates a blank RGBA canvas: `grid_width × tile_size` by `grid_height × tile_size` pixels.
5. Iterates `placements` in order (caller controls draw order — floors should come before furniture).
6. For each placement, opens the PNG from disk and pastes onto canvas at `(x * tile_size, y * tile_size)`.
7. Encodes canvas to PNG bytes and returns.

Tiles that extend beyond the grid bounds are silently clipped (Pillow default).

---

## 4. Configuration

| Env var | Default | Purpose |
|---|---|---|
| `PIXELART_DATA_DIR` | `./data` | Root path of asset folder |
| `PIXELART_CATALOG_PATH` | `./catalog.json` | Path to catalog file |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2-vl` | Vision model used for tile analysis |

---

## 5. Dependencies

```toml
[project]
requires-python = ">=3.11"

dependencies = [
  "pillow",     # image compositing
  "httpx",      # Ollama API calls
  "tqdm",       # analyzer progress bar
]
```

No runtime dependency on Ollama — it is only required when running the analyzer CLI.

---

## 6. Game Engine Integration

The game engine installs this package and uses it as follows:

```python
# 1. Discover available tiles
from pixelart_map import get_catalog
catalog = get_catalog()
tiles = catalog.tiles_by_theme("Classroom_and_Library")
# → pass tile metadata to LLM to decide placement

# 2. Render the LLM-decided layout
from pixelart_map import render_map
result = render_map(grid_width=15, grid_height=15, placements=[...])
# → serve result.png_bytes as image response
# → use result.tilemap for collision/game state
```

The game engine never accesses `data/` directly — all asset I/O goes through `render_map()`.

---

## 7. Asset Themes Reference

### Interiors (48×48)
Living Room, Bathroom, Bedroom, Classroom & Library, Music & Sport, Art, Gym, Fishing, Birthday Party, Halloween, Kitchen, Conference Hall, Basement, Christmas, Grocery Store, Jail, Hospital, Japanese Interiors, Clothing Store, Museum, Television & Film Studio, Ice Cream Shop, Shooting Range, Condominium

### Exteriors (16×16)
Terrains & Fences, City Terrains, City Props, Generic Buildings, Floor Modular Buildings, Garage Sales, Villas, Worksite, Shopping Center & Markets, Vehicles, Camping, Hotel & Hospital, School, Swimming Pool, Police Station, Office, Garden, Fire Station, Graveyard, Subway & Train Station, Beach, Post Office, Military Base, Additional Houses
