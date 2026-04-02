# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

`pixelart_map` is a Python package with three responsibilities:
1. **Offline analyzer** (`python -m pixelart_map.analyzer`) — scans pixel art tile PNGs in `data/`, calls either local Ollama/Qwen2-VL or Anthropic's Batch API, writes `catalog.db`
2. **Catalog API** (`get_catalog()`) — query interface over `catalog.db`
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
python -m pixelart_map.analyzer --data-dir ./data --output catalog.db

# Or via installed entrypoint
pixelart-analyze --data-dir ./data

# Run the analyzer with live web monitor at http://127.0.0.1:5555
pixelart-analyze --data-dir ./data --web

# Run the analyzer using Claude Batch API (requires ANTHROPIC_API_KEY, processes all new tiles at once)
pixelart-analyze --data-dir ./data --backend claude

# Run the analyzer using Claude Batch API, processing only 100 new tiles
pixelart-analyze --data-dir ./data --backend claude --limit 100

# Analyzer options
pixelart-analyze --help
# Options:
#   --data-dir DIR        Root path of pixel art assets (default: ./data or PIXELART_DATA_DIR)
#   --output PATH         Output catalog.db path (default: catalog.db)
#   --host URL            Ollama server URL (default: OLLAMA_HOST or http://localhost:11434, only for --backend ollama)
#   --model NAME          Ollama model name (default: auto-picked or OLLAMA_MODEL, only for --backend ollama)
#   --resolution N        Only analyze tiles at grid unit N px (default: 48, use 0 for all)
#   --web                 Launch live web monitor at http://127.0.0.1:5555
#   --web-port PORT       Port for web monitor (default: 5555)
#   --backend {ollama,claude}  Analysis backend (default: ollama)
#     ollama: Use local Ollama server with qwen2.5vl model (requires GPU)
#     claude: Use Anthropic Batch API (requires ANTHROPIC_API_KEY env var)
#   --limit N             Max sprites to process in a single run (default: all)

# Browse and rate the catalog
pixelart-browse --data-dir ./data --catalog catalog.db
```

## Architecture

The package has nine focused modules plus a public API surface:

| Module | Role |
|---|---|
| `pixelart_map/__init__.py` | Public API: `get_catalog()`, `render_map()` |
| `pixelart_map/catalog.py` | `TileInfo` dataclass, `Catalog` class |
| `pixelart_map/renderer.py` | `render_map()`, `RenderResult`, module-level LRU image cache (cap 256) |
| `pixelart_map/_theme.py` | `strip_theme_name(folder)` — strip/normalize tile folder names |
| `pixelart_map/_filename.py` | `parse_exterior_filename()` — parse exterior tile filenames to skip Ollama |
| `pixelart_map/_ollama.py` | `analyze_tile()` — httpx POST to Ollama, returns `dict | None` |
| `pixelart_map/_claude_batch.py` | Anthropic Batch API orchestration: submit, poll, parse results; resume from state file |
| `pixelart_map/analyzer.py` | CLI: dynamically discovers singles subtrees, dispatches to `_ollama` or `_claude_batch`, writes `catalog.db` |
| `pixelart_map/web.py` | Live web monitor for the analyzer: Flask SSE server at `http://127.0.0.1:5555` |
| `pixelart_map/browser.py` | Catalog browser: Flask app to review and rate analyzed tiles |

**The package is a library + offline CLI.** It includes two optional Flask servers (web monitor, catalog browser) that run locally as dev tools. The game engine (a separate project) installs this package and owns all LLM map-generation logic and HTTP endpoints.

### Data flow

```
data/ (gitignored assets)
    ↓  analyzer.py (offline, dispatches to _ollama or _claude_batch)
    ├─ Ollama: local httpx POST to vision model (needs GPU)
    └─ Claude: Anthropic Batch API (needs ANTHROPIC_API_KEY)
catalog.db  (committed build artifact)
    ↓  catalog.py
Catalog / TileInfo  →  game engine passes tile list to LLM
    ↓  renderer.py
PNG bytes + tilemap metadata  →  game engine serves as HTTP response
```

### Key design decisions

- **Exterior tile fast-path** — `_filename.py` parses ~6,000 exterior tile filenames directly (description, semantic_type, tags, confidence=1.0) without calling Ollama or Claude. Interior tiles always fall through to analysis.
- **Tile ID** = full 64-char SHA-256 of the relative path string. Used as the SQLite primary key and `TileInfo.id`.
- **Analyzer dedup** = `SELECT id FROM tiles` on startup; already-present IDs are skipped. Each new tile is committed immediately so progress is never lost on interruption.
- **Analyzer walk scope** is dynamic — it auto-discovers all qualifying singles subtrees under `data/`. Interior: all `Theme_Sorter_Shadowless_Singles` variants at every available resolution. Exterior: all `ME_Theme_Sorter_NNxNN` variants at every available resolution; root-level spritesheets directly in `ME_Theme_Sorter_NNxNN` are skipped. `Complete_Singles`, `Black_Shadow`, autotiles, and character folders are all excluded.
- **`data_dir` has no default in `render_map()`** — must be passed explicitly or via `PIXELART_DATA_DIR`; raises `ValueError` immediately if absent.
- **LRU image cache** is module-level in `renderer.py`, persists across `render_map()` calls within the same process. Call `renderer._load_image.cache_clear()` in tests that check cache hit counts.
- **`_theme.py`** handles several typos in the original asset pack directory names (e.g. `SIngles`, `MIlitary`).
- **Mixed tile sizes**: a tile with `pixel_height=96` and `grid_unit=48` spans 2 cells tall, pasted at natural size. Callers must reserve those cells.
- **Claude Batch API resume** — `_claude_batch.py` saves batch state to `.pixelart_batch_state.json` after submission. If the CLI is interrupted or crashes, rerunning the same command resumes from the saved batch ID instead of resubmitting. State is cleaned up after results are processed.

## Environment Variables

| Var | Default | Purpose |
|---|---|---|
| `PIXELART_DATA_DIR` | *(required at render time)* | Root path of the asset folder |
| `PIXELART_CATALOG_PATH` | `catalog.db` next to package root | Override catalog location |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL (for `--backend ollama`) |
| `OLLAMA_MODEL` | `qwen2.5vl:7b` | Vision model for tile analysis (for `--backend ollama`) |
| `ANTHROPIC_API_KEY` | *(required for `--backend claude`)* | Anthropic API key (for `--backend claude`) |

## Testing

Tests create all PNG fixtures programmatically with Pillow and mock Ollama via `unittest.mock` — **no real assets or GPU required**. The `data/` directory is gitignored.

