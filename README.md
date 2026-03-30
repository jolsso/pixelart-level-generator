# pixelart-level-generator

A Python package for cataloging pixel art tile assets and compositing them into map images.

## What it does

`pixelart_map` has three responsibilities:

1. **Offline analyzer** — scans pixel art tile PNGs using a local Ollama vision model (Qwen2-VL) and produces a `catalog.db` describing every tile
2. **Catalog API** — query interface over the catalog (filter by theme, map type, semantic type, or free-text search)
3. **Renderer** — composites a list of tile placements into a PNG image using Pillow

The package is consumed by a separate game engine that owns all LLM-based map generation, HTTP endpoints, and game state. This package has no HTTP server.

## Prerequisites

- Python ≥ 3.11
- For the **analyzer only**: [Ollama](https://ollama.com/download) installed and running with `qwen2.5vl:7b` pulled, and pixel art assets present at `PIXELART_DATA_DIR`

```bash
# macOS (Homebrew)
brew install ollama

# or download the installer from https://ollama.com/download

ollama serve          # start the Ollama server (skip if already running as a service)
ollama pull qwen2.5vl:7b
```

## Installation

```bash
pip install git+https://github.com/jolsso/pixelart-level-generator
```

For development:

```bash
git clone git@github.com:jolsso/pixelart-level-generator.git
cd pixelart-level-generator
pip install -e ".[dev]"
```

## Usage

### Build the catalog (offline, one-time)

```bash
pixelart-analyze --data-dir ./data --output catalog.db
```

Re-runs are incremental — already-analyzed tiles are skipped.

### Query the catalog

```python
from pixelart_map import get_catalog

catalog = get_catalog()

catalog.themes()                                 # -> List[str]
catalog.tiles_by_theme("Classroom_and_Library")  # -> List[TileInfo]
catalog.tiles_by_map_type("interior")            # -> List[TileInfo]
catalog.tiles_by_semantic_type("furniture")      # -> List[TileInfo]
catalog.search("desk")                           # -> List[TileInfo]
catalog.get_tile("<sha256-tile-id>")             # -> TileInfo
```

### Render a map

```python
from pixelart_map import render_map

result = render_map(
    grid_width=15,
    grid_height=15,
    placements=[
        {"x": 0, "y": 0, "tile_id": "<sha256>"},
        {"x": 1, "y": 0, "tile_id": "<sha256>"},
    ],
    data_dir="/path/to/data",
)

result.png_bytes  # PNG-encoded image as bytes
result.tilemap    # placements with resolved theme/semantic_type/dimensions
```

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `PIXELART_DATA_DIR` | *(required at render time)* | Root path of the asset folder |
| `PIXELART_CATALOG_PATH` | `catalog.db` next to package root | Override catalog location |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5vl:7b` | Vision model for tile analysis |

## Running tests

No assets or GPU needed — all fixtures are generated programmatically.

```bash
pytest
```

## Asset setup

The pixel art assets are **not included** in this repository and must be purchased and set up manually:

1. Buy the asset packs from itch.io:
   - [Modern Interiors](https://limezu.itch.io/moderninteriors)
   - [Modern Exteriors](https://limezu.itch.io/modernexteriors)

2. Unzip both packages into the `data/` directory at the repo root:
   ```
   data/
   ├── moderninteriors-win/
   └── modernexteriors-win/
   ```

3. Run the analyzer to build `catalog.db`:
   ```bash
   pixelart-analyze --data-dir ./data --output catalog.db
   ```

## Asset credits

Pixel art assets by [LimeZu](https://limezu.itch.io/).
