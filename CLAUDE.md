# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

`pixelart_map` is a Python package with three responsibilities:
1. **Offline analyzer** (`python -m pixelart_map.analyzer`) — scans pixel art tile PNGs in `data/`, calls local Ollama/Qwen2-VL, writes `catalog.json`
2. **Catalog API** (`get_catalog()`) — query interface over `catalog.json`
3. **Renderer** (`render_map()`) — composites tile placements into a PNG using Pillow

See `docs/superpowers/specs/2026-03-29-map-generator-design.md` for full design rationale.

## Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run all tests (no Ollama or GPU required)
pytest

# Run a single test file
pytest tests/test_renderer.py -v

# Run a single test
pytest tests/test_theme.py::test_strip_theme_name[5_Classroom_and_Library_Singles_Shadowless_48x48-Classroom_and_Library] -v

# Run the analyzer (requires Ollama running + qwen2.5vl:7b pulled + data/ present)
python -m pixelart_map.analyzer --data-dir ./data --output catalog.json

# Or via installed entrypoint
pixelart-analyze --data-dir ./data
```

## Architecture

The package has five focused modules plus a public API surface:

| Module | Role |
|---|---|
| `pixelart_map/__init__.py` | Public API: `get_catalog()`, `render_map()` |
| `pixelart_map/catalog.py` | `TileInfo` dataclass, `Catalog` class |
| `pixelart_map/renderer.py` | `render_map()`, `RenderResult`, module-level LRU image cache (cap 256) |
| `pixelart_map/_theme.py` | `strip_theme_name(folder)` — strip/normalize tile folder names |
| `pixelart_map/_ollama.py` | `analyze_tile()` — httpx POST to Ollama, returns `dict | None` |
| `pixelart_map/analyzer.py` | CLI: walks two specific subtrees, calls `_ollama`, writes `catalog.json` |

**The package is a library + offline CLI only — no HTTP server.** The game engine (a separate project) installs this package and owns all LLM map-generation logic and HTTP endpoints.

### Data flow

```
data/ (gitignored assets)
    ↓  analyzer.py (offline, needs Ollama + GPU)
catalog.json  (committed build artifact)
    ↓  catalog.py
Catalog / TileInfo  →  game engine passes tile list to LLM
    ↓  renderer.py
PNG bytes + tilemap metadata  →  game engine serves as HTTP response
```

### Key design decisions

- **Tile ID** = full 64-char SHA-256 of the relative path string. Used as both the catalog dict key and `TileInfo.id`.
- **Analyzer dedup** = key lookup in existing catalog dict. Re-runs are incremental.
- **Analyzer walk scope** is restricted to two specific subtrees — do not walk all of `data/`.
- **`data_dir` has no default in `render_map()`** — must be passed explicitly or via `PIXELART_DATA_DIR`; raises `ValueError` immediately if absent.
- **LRU image cache** is module-level in `renderer.py`, persists across `render_map()` calls within the same process. Call `renderer._load_image.cache_clear()` in tests that check cache hit counts.
- **`_theme.py`** handles several typos in the original asset pack directory names (e.g. `SIngles`, `MIlitary`).
- **Mixed tile sizes**: a tile with `pixel_height=96` and `grid_unit=48` spans 2 cells tall, pasted at natural size. Callers must reserve those cells.

## Environment Variables

| Var | Default | Purpose |
|---|---|---|
| `PIXELART_DATA_DIR` | *(required at render time)* | Root path of the asset folder |
| `PIXELART_CATALOG_PATH` | `catalog.json` next to package root | Override catalog location |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5vl:7b` | Vision model for tile analysis |

## Testing

Tests create all PNG fixtures programmatically with Pillow and mock Ollama via `unittest.mock` — **no real assets or GPU required**. The `data/` directory is gitignored.

## Asset Data

`data/` is gitignored (third-party pixel art from limezu.itch.io). Two subtrees are scanned by the analyzer:

- `data/moderninteriors-win/1_Interiors/48x48/Theme_Sorter_Shadowless_Singles_48x48/` — interior tiles, `grid_unit=48`
- `data/modernexteriors-win/Modern_Exteriors_16x16/ME_Theme_Sorter_16x16/` — exterior tiles, `grid_unit=16`

Only `*_Singles_*` subdirectories contain individual tile PNGs. Spritesheets, characters, autotiles, and character generator parts are excluded.
