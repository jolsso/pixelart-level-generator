# pixelart_map — Design Spec

**Date:** 2026-03-29
**Status:** Approved

## Summary

`pixelart_map` is a Python package that serves two purposes:

1. **Offline catalog builder** — analyzes pixel art tile assets using a local Ollama vision model (Qwen2-VL) and produces a `catalog.json` artifact describing every tile.
2. **Runtime library** — provides a query interface over the catalog and a Pillow-based renderer that composites tile placements into PNG images.

The package is consumed by a separate game engine project. The game engine owns all LLM-based map generation logic, user-facing HTTP endpoints, and game state. This package has no HTTP server.

---

## Prerequisites

- Python ≥ 3.11
- NVIDIA GPU with ≥ 24 GB VRAM for running Qwen2-VL locally (e.g. RTX 3090). The analyzer is an offline tool and does not need to run on the deployment server.
- Ollama running locally: `ollama serve`
- Qwen2-VL model pulled: `ollama pull qwen2-vl`
- Pixel art assets present at `PIXELART_DATA_DIR` (not committed — deployed via CI/CD)

---

## Scope

**In scope:**
- Analyzer CLI that scans specified subdirectories of `data/` and calls Ollama to describe each tile
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
│   ├── moderninteriors-win/       # interior tiles, 48px grid unit
│   └── modernexteriors-win/       # exterior tiles, 16px grid unit
├── pixelart_map/
│   ├── __init__.py                # public API: get_catalog, render_map
│   ├── analyzer.py                # CLI: scans data/, calls Ollama, writes catalog.json
│   ├── catalog.py                 # loads catalog.json, TileInfo dataclass, query methods
│   └── renderer.py                # Pillow compositor
├── catalog.json                   # committed build artifact — updated when assets change
├── pyproject.toml
└── .gitignore                     # excludes data/ and moden_pixelart/
```

---

## 1. Analyzer

**Invocation:** `python -m pixelart_map.analyzer [--data-dir ./data]`

### Walk Scope

The analyzer does NOT walk all of `data/`. It scans only the following subtrees to avoid characters, spritesheets, autotiles, and duplicates:

| Subtree | map_type | grid_unit |
|---|---|---|
| `moderninteriors-win/1_Interiors/48x48/Theme_Sorter_Shadowless_Singles_48x48/` | interior | 48 |
| `modernexteriors-win/Modern_Exteriors_16x16/ME_Theme_Sorter_16x16/` | exterior | 16 |

Only the `*_Singles_*` subdirectories contain individual tile PNGs suitable for placement. Tilesheets, character sprites, animated sheets, autotiles, and character generator parts are excluded.

### Behavior

1. Walks the two subtrees above, collecting all `.png` files.
2. Loads existing `catalog.json` (empty dict if not present).
3. For each PNG whose full SHA-256 of the relative path is not a key in the catalog:
   - Derives `theme`, `map_type`, `grid_unit`, `pixel_width`, and `pixel_height` from path and image dimensions.
   - Base64-encodes the image.
   - POSTs to Ollama. Appends result to catalog dict.
4. Writes updated `catalog.json`.
5. Displays progress with `tqdm`. Skips already-analyzed tiles so re-runs are incremental.

### Path-derived fields

| Field | Derivation |
|---|---|
| `map_type` | `"interior"` for the interiors subtree, `"exterior"` for the exteriors subtree |
| `grid_unit` | `48` for interiors, `16` for exteriors (the base cell size in pixels) |
| `pixel_width`, `pixel_height` | Read from actual image dimensions via Pillow — tiles may span multiple cells |
| `theme` | Parent directory name, cleaned via the strip + normalize rules below |

**Theme derivation — strip rule (applied in order, all matches case-insensitive):**

1. Strip leading `NN_` numeric prefix (e.g. `5_` or `23_`)
2. Strip one of the following suffixes (longest match first):
   - `_Singles_Shadowless_NNxNN`
   - `_SIngles_Shadowless_NNxNN` *(asset pack typo — capital I)*
   - `_Singles_NNxNN`
   - `_Shadowless_NNxNN` *(used by `Music_and_Sport` which has no `Singles` component)*
   - `_NNxNN`

3. Apply normalization table for known asset pack typos:

| Raw stripped value | Normalized to |
|---|---|
| `MIlitary_Base` | `Military_Base` |

Example: `5_Classroom_and_Library_Singles_Shadowless_48x48` → strip prefix → `Classroom_and_Library_Singles_Shadowless_48x48` → strip suffix → `Classroom_and_Library`.

Example: `6_Music_and_Sport_Shadowless_48x48` → strip prefix → `Music_and_Sport_Shadowless_48x48` → strip `_Shadowless_48x48` → `Music_and_Sport`.

### Ollama API call

POST to `{OLLAMA_HOST}/api/chat`:

```json
{
  "model": "<OLLAMA_MODEL>",
  "stream": false,
  "format": "json",
  "messages": [{
    "role": "user",
    "content": "<prompt>",
    "images": ["<raw base64 string — no data-URI prefix>"]
  }]
}
```

Response: `response.json()["message"]["content"]` — a JSON string. Parse with `json.loads()`. If parsing fails or required keys are missing, log a warning and skip the tile (do not abort the run).

### Ollama prompt

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
    "<full SHA-256 of relative path>": {
      "id": "<full SHA-256 of relative path>",
      "path": "<relative path from data/ root>",
      "theme": "Classroom_and_Library",
      "map_type": "interior",
      "grid_unit": 48,
      "pixel_width": 48,
      "pixel_height": 96,
      "description": "School desk with chair, wooden, top-down view",
      "semantic_type": "furniture",
      "tags": ["desk", "chair", "school", "wooden"]
    }
  }
}
```

**Important:** The tile `id` and the catalog dict key are both the full SHA-256 hex string (64 chars). No truncation. This ensures the dedup check in the analyzer (key lookup) is consistent with the stored `id` field.

`pixel_width` and `pixel_height` are the actual image dimensions in pixels. `grid_unit` is the base cell size (48 or 16). A tile with `pixel_width=48, pixel_height=96, grid_unit=48` occupies 1 cell wide × 2 cells tall.

### Python query API (`catalog.py`)

```python
from pixelart_map import get_catalog

catalog = get_catalog()  # loads from PIXELART_CATALOG_PATH env var, else catalog.json next to __init__.py

catalog.themes() -> List[str]
catalog.map_types() -> List[str]                           # ["interior", "exterior"]
catalog.tiles_by_theme(theme: str) -> List[TileInfo]
catalog.tiles_by_map_type(map_type: str) -> List[TileInfo]
catalog.tiles_by_semantic_type(semantic_type: str) -> List[TileInfo]
catalog.search(query: str) -> List[TileInfo]               # case-insensitive substring over description + tags
catalog.get_tile(tile_id: str) -> TileInfo
```

`TileInfo` is a dataclass with fields matching the JSON schema above.

---

## 3. Renderer

### API

```python
from pixelart_map import render_map

result = render_map(
    grid_width=10,
    grid_height=10,
    placements=[
        {"x": 0, "y": 0, "tile_id": "<sha256>"},
        {"x": 1, "y": 0, "tile_id": "<sha256>"},
        ...
    ],
    data_dir="/path/to/data"   # required — no default. Set PIXELART_DATA_DIR or pass explicitly.
)

result.png_bytes: bytes        # PNG-encoded composited image
result.tilemap: List[dict]     # echo of placements with resolved TileInfo metadata per tile
```

`data_dir` has no default. If omitted, `PIXELART_DATA_DIR` must be set; otherwise a `ValueError` is raised immediately (not at render time).

### Behavior

1. Resolves `data_dir` from argument or `PIXELART_DATA_DIR`. Raises `ValueError` if neither is set.
2. Resolves each `tile_id` via the catalog. Raises `ValueError` for unknown IDs.
3. Validates all tiles share the same `map_type`. Raises `ValueError` on mismatch.
4. Determines `grid_unit` from the first resolved tile.
5. Creates a blank RGBA canvas: `grid_width × grid_unit` by `grid_height × grid_unit` pixels.
6. Iterates `placements` in order — caller controls draw order (floors first, furniture on top).
7. For each placement, retrieves the tile image from an internal LRU cache (keyed by absolute path, capacity 256). Opens from disk on cache miss.
8. Pastes the tile image at `(x * grid_unit, y * grid_unit)`. Tiles whose pixel dimensions exceed one cell (e.g. `pixel_height = 96` with `grid_unit = 48`) are pasted at their natural size — they will overlap adjacent cells. Callers are responsible for reserving those cells in their layout.
9. Encodes the canvas to PNG bytes and returns.

The LRU cache is module-level (persists across `render_map` calls within the same process), giving good performance for repeated game engine requests using the same tile set.

---

## 4. Configuration

| Env var | Default | Purpose |
|---|---|---|
| `PIXELART_DATA_DIR` | *(none — required at render time)* | Root path of asset folder |
| `PIXELART_CATALOG_PATH` | `catalog.json` next to `__init__.py` | Path to catalog file |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2-vl` | Vision model used for tile analysis |

---

## 5. Dependencies

```toml
[project]
requires-python = ">=3.11"

dependencies = [
  "pillow",     # image compositing
  "httpx",      # Ollama API calls (analyzer only)
  "tqdm",       # analyzer progress bar
]
```

Ollama is a runtime dependency only for the analyzer CLI. The core library (`get_catalog`, `render_map`) has no Ollama dependency.

---

## 6. Game Engine Integration

The game engine installs this package (e.g. `pip install git+https://github.com/.../pixelart-level-generator`) and sets `PIXELART_DATA_DIR` to the location of the deployed asset folder.

```python
# 1. Discover available tiles to inform LLM
from pixelart_map import get_catalog
catalog = get_catalog()
tiles = catalog.tiles_by_theme("Classroom_and_Library")
# → serialize tiles to pass to LLM with map generation prompt

# 2. Render the LLM-decided layout
from pixelart_map import render_map
result = render_map(
    grid_width=15,
    grid_height=15,
    placements=[...],  # LLM output, validated before passing here
    data_dir="/app/data"
)
# → serve result.png_bytes as image/png HTTP response
# → use result.tilemap for collision detection / game state
```

The game engine never accesses `data/` directly — all asset I/O goes through `render_map()`.

---

## 7. Asset Themes Reference

These are the exact values returned by `catalog.themes()` after strip + normalize.

### Interiors (grid_unit=48)
Living_Room, Bathroom, Bedroom, Classroom_and_Library, Music_and_Sport, Art, Gym, Fishing, Birthday_Party, Halloween, Kitchen, Conference_Hall, Basement, Christmas, Grocery_Store, Jail, Hospital, Japanese_Interiors, Clothing_Store, Museum, Television_and_Film_Studio, Ice_Cream_Shop, Shooting_Range, Condominium

### Exteriors (grid_unit=16)
Terrains_and_Fences, City_Terrains, City_Props, Generic_Building, Floor_Modular_Building, Garage_Sales, Villas, Worksite, Shopping_Center_and_Markets, Vehicles, Camping, Hotel_and_Hospital, School, Swimming_Pool, Police_Station, Office, Garden, Fire_Station, Graveyard, Subway_and_Train_Station, Beach, Post_Office, Military_Base, Additional_Houses

*Note: `Generic_Building` and `Floor_Modular_Building` are singular — this matches the actual asset pack directory names (`Generic_Building_Singles_16x16`, `Floor_Modular_Building_Singles_16x16`).*
