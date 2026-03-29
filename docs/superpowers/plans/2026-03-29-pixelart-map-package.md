# pixelart_map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `pixelart_map`, a Python package with an offline tile analyzer (Ollama/Qwen2-VL), a catalog query API, and a Pillow-based map renderer.

**Architecture:** Five focused modules — `catalog.py` (TileInfo dataclass + query API), `renderer.py` (Pillow compositor with LRU image cache), `_theme.py` (theme name strip/normalize logic), `_ollama.py` (Ollama HTTP client), `analyzer.py` (CLI + main loop). `__init__.py` exposes the public API. Tests use programmatically-created PNG fixtures and mocked Ollama — no real assets or GPU required.

**Tech Stack:** Python 3.11+, Pillow, httpx, tqdm, pytest

---

## File Map

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, deps, dev deps, CLI entrypoint |
| `pixelart_map/__init__.py` | Public exports: `get_catalog`, `render_map` |
| `pixelart_map/catalog.py` | `TileInfo` dataclass, `Catalog` class, `get_catalog()` |
| `pixelart_map/renderer.py` | `render_map()`, `RenderResult`, `_load_image()` with LRU cache |
| `pixelart_map/_theme.py` | `strip_theme_name(folder: str) -> str` |
| `pixelart_map/_ollama.py` | `analyze_tile(img_path, host, model) -> dict \| None` |
| `pixelart_map/analyzer.py` | CLI entrypoint, file walk, catalog writer |
| `tests/conftest.py` | Shared fixtures: sample catalog, PNG files, tmp dirs |
| `tests/test_catalog.py` | Catalog query API tests |
| `tests/test_theme.py` | Theme strip/normalize tests |
| `tests/test_renderer.py` | Renderer tests |
| `tests/test_ollama.py` | Ollama client tests (mocked httpx) |
| `tests/test_analyzer.py` | Analyzer CLI tests (mocked Ollama + filesystem) |

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `pixelart_map/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "pixelart-map"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pillow>=10.0",
    "httpx>=0.27",
    "tqdm>=4.66",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[project.scripts]
pixelart-analyze = "pixelart_map.analyzer:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package + test stubs**

```python
# pixelart_map/__init__.py
# Public API — populated in Task 9
```

```python
# tests/__init__.py
```

```python
# tests/conftest.py
# Shared fixtures — populated in Task 2
```

- [ ] **Step 3: Install in editable mode**

```bash
pip install -e ".[dev]"
```

Expected: installs without error, `pixelart-analyze` command available.

- [ ] **Step 4: Verify import**

```bash
python -c "import pixelart_map; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml pixelart_map/__init__.py tests/__init__.py tests/conftest.py
git commit -m "feat: scaffold pixelart_map package"
```

---

## Task 2: TileInfo + Catalog Loading

**Files:**
- Create: `pixelart_map/catalog.py`
- Create: `tests/fixtures/sample_catalog.json`
- Modify: `tests/conftest.py`
- Create: `tests/test_catalog.py`

- [ ] **Step 1: Create sample_catalog.json fixture**

```bash
mkdir -p tests/fixtures
```

```json
{
  "version": 1,
  "generated_at": "2026-03-29T00:00:00",
  "tiles": {
    "aaaa000000000000000000000000000000000000000000000000000000000001": {
      "id": "aaaa000000000000000000000000000000000000000000000000000000000001",
      "path": "moderninteriors-win/1_Interiors/48x48/Theme_Sorter_Shadowless_Singles_48x48/5_Classroom_and_Library_Singles_Shadowless_48x48/tile_01.png",
      "theme": "Classroom_and_Library",
      "map_type": "interior",
      "grid_unit": 48,
      "pixel_width": 48,
      "pixel_height": 48,
      "description": "A wooden school desk with a chair, top-down view",
      "semantic_type": "furniture",
      "tags": ["desk", "chair", "school", "wooden"]
    },
    "bbbb000000000000000000000000000000000000000000000000000000000002": {
      "id": "bbbb000000000000000000000000000000000000000000000000000000000002",
      "path": "moderninteriors-win/1_Interiors/48x48/Theme_Sorter_Shadowless_Singles_48x48/5_Classroom_and_Library_Singles_Shadowless_48x48/tile_02.png",
      "theme": "Classroom_and_Library",
      "map_type": "interior",
      "grid_unit": 48,
      "pixel_width": 48,
      "pixel_height": 96,
      "description": "A tall bookshelf, top-down view",
      "semantic_type": "furniture",
      "tags": ["bookshelf", "school", "library", "tall"]
    },
    "cccc000000000000000000000000000000000000000000000000000000000003": {
      "id": "cccc000000000000000000000000000000000000000000000000000000000003",
      "path": "modernexteriors-win/Modern_Exteriors_16x16/ME_Theme_Sorter_16x16/16_Office_Singles_16x16/tile_01.png",
      "theme": "Office",
      "map_type": "exterior",
      "grid_unit": 16,
      "pixel_width": 16,
      "pixel_height": 16,
      "description": "Office building facade, top-down view",
      "semantic_type": "building",
      "tags": ["office", "building", "facade"]
    }
  }
}
```

- [ ] **Step 2: Add catalog fixture to conftest.py**

```python
# tests/conftest.py
import json
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def sample_catalog_path():
    return FIXTURES_DIR / "sample_catalog.json"

@pytest.fixture
def sample_catalog_data(sample_catalog_path):
    return json.loads(sample_catalog_path.read_text())
```

- [ ] **Step 3: Write failing test**

```python
# tests/test_catalog.py
from pixelart_map.catalog import Catalog, TileInfo

TILE_ID_1 = "aaaa000000000000000000000000000000000000000000000000000000000001"

def test_get_tile_returns_tile_info(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    tile = catalog.get_tile(TILE_ID_1)
    assert isinstance(tile, TileInfo)
    assert tile.id == TILE_ID_1
    assert tile.theme == "Classroom_and_Library"
    assert tile.map_type == "interior"
    assert tile.grid_unit == 48
    assert tile.pixel_width == 48
    assert tile.pixel_height == 48
    assert tile.semantic_type == "furniture"
    assert "desk" in tile.tags

def test_get_tile_unknown_raises(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    with pytest.raises(KeyError):
        catalog.get_tile("nonexistent")
```

- [ ] **Step 4: Run test — expect FAIL**

```bash
pytest tests/test_catalog.py -v
```

Expected: `ImportError` or `ModuleNotFoundError`

- [ ] **Step 5: Implement TileInfo + Catalog._load() + get_tile()**

```python
# pixelart_map/catalog.py
from __future__ import annotations
import json
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
        return self._tiles[tile_id]  # raises KeyError if not found
```

- [ ] **Step 6: Run test — expect PASS**

```bash
pytest tests/test_catalog.py -v
```

Expected: 2 tests PASS

- [ ] **Step 7: Commit**

```bash
git add pixelart_map/catalog.py tests/fixtures/sample_catalog.json tests/conftest.py tests/test_catalog.py
git commit -m "feat: TileInfo dataclass and catalog loading"
```

---

## Task 3: Catalog Query Methods

**Files:**
- Modify: `pixelart_map/catalog.py`
- Modify: `tests/test_catalog.py`

- [ ] **Step 1: Write failing tests**

```python
# append to tests/test_catalog.py
import pytest
from pixelart_map.catalog import Catalog, TileInfo

TILE_ID_1 = "aaaa000000000000000000000000000000000000000000000000000000000001"
TILE_ID_2 = "bbbb000000000000000000000000000000000000000000000000000000000002"
TILE_ID_3 = "cccc000000000000000000000000000000000000000000000000000000000003"

def test_themes(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    themes = catalog.themes()
    assert set(themes) == {"Classroom_and_Library", "Office"}

def test_map_types(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    assert set(catalog.map_types()) == {"interior", "exterior"}

def test_tiles_by_theme(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    tiles = catalog.tiles_by_theme("Classroom_and_Library")
    assert len(tiles) == 2
    assert all(t.theme == "Classroom_and_Library" for t in tiles)

def test_tiles_by_theme_empty(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    assert catalog.tiles_by_theme("Nonexistent") == []

def test_tiles_by_map_type(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    interiors = catalog.tiles_by_map_type("interior")
    assert len(interiors) == 2
    assert all(t.map_type == "interior" for t in interiors)

def test_tiles_by_semantic_type(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    furniture = catalog.tiles_by_semantic_type("furniture")
    assert len(furniture) == 2

def test_search_by_tag(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    results = catalog.search("desk")
    assert len(results) == 1
    assert results[0].id == TILE_ID_1

def test_search_by_description(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    results = catalog.search("bookshelf")
    assert len(results) == 1
    assert results[0].id == TILE_ID_2

def test_search_case_insensitive(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    assert catalog.search("DESK") == catalog.search("desk")

def test_search_no_results(sample_catalog_path):
    catalog = Catalog(sample_catalog_path)
    assert catalog.search("xyzzy") == []
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_catalog.py -v
```

Expected: all new tests fail with `AttributeError`

- [ ] **Step 3: Implement query methods**

Add to the `Catalog` class in `pixelart_map/catalog.py`:

```python
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
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_catalog.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add pixelart_map/catalog.py tests/test_catalog.py
git commit -m "feat: catalog query methods (themes, search, filter)"
```

---

## Task 4: Theme Strip + Normalize

**Files:**
- Create: `pixelart_map/_theme.py`
- Create: `tests/test_theme.py`

- [ ] **Step 1: Write failing tests**

These use the actual asset pack directory names from the spec's walk scope.

```python
# tests/test_theme.py
import pytest
from pixelart_map._theme import strip_theme_name

@pytest.mark.parametrize("folder,expected", [
    # Standard interior: _Singles_Shadowless_NNxNN suffix
    ("5_Classroom_and_Library_Singles_Shadowless_48x48", "Classroom_and_Library"),
    ("2_Living_Room_Singles_Shadowless_48x48",           "Living_Room"),
    ("4_Bedroom_Singles_Shadowless_48x48",               "Bedroom"),
    ("3_Bathroom_Singles_Shadowless_48x48",              "Bathroom"),
    ("8_Gym_Singles_Shadowless_48x48",                   "Gym"),
    ("7_Art_Singles_Shadowless_48x48",                   "Art"),
    ("14_Basement_Singles_Shadowless_48x48",             "Basement"),
    ("26_Condominium_Singles_Shadowless_48x48",          "Condominium"),
    # Interior with asset pack typo: SIngles (capital I)
    ("19_Hospital_SIngles_Shadowless_48x48",             "Hospital"),
    # Interior without "Singles": only _Shadowless_NNxNN suffix
    ("6_Music_and_Sport_Shadowless_48x48",               "Music_and_Sport"),
    # Standard exterior: _Singles_NNxNN suffix
    ("16_Office_Singles_16x16",                          "Office"),
    ("13_School_Singles_16x16",                          "School"),
    ("1_Terrains_and_Fences_Singles_16x16",              "Terrains_and_Fences"),
    ("9_Shopping_Center_and_Markets_Singles_16x16",      "Shopping_Center_and_Markets"),
    # Exterior with normalization: MIlitary typo
    ("23_MIlitary_Base_Singles_16x16",                   "Military_Base"),
    # Exterior singular names (not plural — matches actual asset pack)
    ("4_Generic_Building_Singles_16x16",                 "Generic_Building"),
    ("5_Floor_Modular_Building_Singles_16x16",           "Floor_Modular_Building"),
])
def test_strip_theme_name(folder, expected):
    assert strip_theme_name(folder) == expected
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_theme.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement strip_theme_name()**

```python
# pixelart_map/_theme.py
import re

# Suffixes to strip, tried in order (longest match first, case-insensitive)
_SUFFIXES = [
    r"_Singles_Shadowless_\d+x\d+$",
    r"_SIngles_Shadowless_\d+x\d+$",  # asset pack typo
    r"_Singles_\d+x\d+$",
    r"_Shadowless_\d+x\d+$",
    r"_\d+x\d+$",
]

# Known typos in asset pack directory names
_NORMALIZATIONS: dict[str, str] = {
    "MIlitary_Base": "Military_Base",
}


def strip_theme_name(folder: str) -> str:
    """Derive a clean theme name from an asset pack directory name.

    Example: '5_Classroom_and_Library_Singles_Shadowless_48x48' -> 'Classroom_and_Library'
    """
    # 1. Strip leading numeric prefix (e.g. "5_" or "23_")
    name = re.sub(r"^\d+_", "", folder)

    # 2. Strip recognized suffix (case-insensitive, longest match first)
    for pattern in _SUFFIXES:
        stripped = re.sub(pattern, "", name, flags=re.IGNORECASE)
        if stripped != name:
            name = stripped
            break

    # 3. Apply normalization table
    return _NORMALIZATIONS.get(name, name)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_theme.py -v
```

Expected: all 17 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pixelart_map/_theme.py tests/test_theme.py
git commit -m "feat: theme name strip and normalize logic"
```

---

## Task 5: Renderer Core

**Files:**
- Create: `pixelart_map/renderer.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_renderer.py`

- [ ] **Step 1: Add PNG fixtures to conftest.py**

```python
# append to tests/conftest.py
import io
from PIL import Image

@pytest.fixture
def data_dir(tmp_path):
    """Fake data/ directory with tiny test PNGs at real relative paths."""
    interior_dir = (
        tmp_path
        / "moderninteriors-win"
        / "1_Interiors"
        / "48x48"
        / "Theme_Sorter_Shadowless_Singles_48x48"
        / "5_Classroom_and_Library_Singles_Shadowless_48x48"
    )
    interior_dir.mkdir(parents=True)

    exterior_dir = (
        tmp_path
        / "modernexteriors-win"
        / "Modern_Exteriors_16x16"
        / "ME_Theme_Sorter_16x16"
        / "16_Office_Singles_16x16"
    )
    exterior_dir.mkdir(parents=True)

    # 48x48 red tile (1-cell)
    img_48 = Image.new("RGBA", (48, 48), (255, 0, 0, 255))
    img_48.save(interior_dir / "tile_01.png")

    # 48x96 blue tile (2-cell tall)
    img_tall = Image.new("RGBA", (48, 96), (0, 0, 255, 255))
    img_tall.save(interior_dir / "tile_02.png")

    # 16x16 green tile
    img_16 = Image.new("RGBA", (16, 16), (0, 255, 0, 255))
    img_16.save(exterior_dir / "tile_01.png")

    return tmp_path


@pytest.fixture
def catalog_with_png_paths(tmp_path, data_dir, sample_catalog_path):
    """A catalog.json whose tile paths point to the tmp data_dir fixtures."""
    import json
    data = json.loads(sample_catalog_path.read_text())
    # Rewrite paths to match real filenames in data_dir
    data["tiles"]["aaaa000000000000000000000000000000000000000000000000000000000001"]["path"] = (
        "moderninteriors-win/1_Interiors/48x48/Theme_Sorter_Shadowless_Singles_48x48"
        "/5_Classroom_and_Library_Singles_Shadowless_48x48/tile_01.png"
    )
    data["tiles"]["bbbb000000000000000000000000000000000000000000000000000000000002"]["path"] = (
        "moderninteriors-win/1_Interiors/48x48/Theme_Sorter_Shadowless_Singles_48x48"
        "/5_Classroom_and_Library_Singles_Shadowless_48x48/tile_02.png"
    )
    data["tiles"]["cccc000000000000000000000000000000000000000000000000000000000003"]["path"] = (
        "modernexteriors-win/Modern_Exteriors_16x16/ME_Theme_Sorter_16x16"
        "/16_Office_Singles_16x16/tile_01.png"
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(data))
    return catalog_path
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_renderer.py
import io
import pytest
from PIL import Image
from pixelart_map.catalog import Catalog
from pixelart_map.renderer import render_map, RenderResult

TILE_1 = "aaaa000000000000000000000000000000000000000000000000000000000001"
TILE_2 = "bbbb000000000000000000000000000000000000000000000000000000000002"
TILE_3 = "cccc000000000000000000000000000000000000000000000000000000000003"


def test_render_returns_result(catalog_with_png_paths, data_dir):
    catalog = Catalog(catalog_with_png_paths)
    result = render_map(
        grid_width=2, grid_height=2,
        placements=[{"x": 0, "y": 0, "tile_id": TILE_1}],
        data_dir=str(data_dir),
        catalog=catalog,
    )
    assert isinstance(result, RenderResult)
    assert isinstance(result.png_bytes, bytes)
    assert len(result.png_bytes) > 0


def test_render_png_dimensions(catalog_with_png_paths, data_dir):
    catalog = Catalog(catalog_with_png_paths)
    result = render_map(
        grid_width=3, grid_height=2,
        placements=[{"x": 0, "y": 0, "tile_id": TILE_1}],
        data_dir=str(data_dir),
        catalog=catalog,
    )
    img = Image.open(io.BytesIO(result.png_bytes))
    assert img.size == (3 * 48, 2 * 48)  # 144x96


def test_render_tilemap_contains_metadata(catalog_with_png_paths, data_dir):
    catalog = Catalog(catalog_with_png_paths)
    result = render_map(
        grid_width=2, grid_height=2,
        placements=[{"x": 0, "y": 0, "tile_id": TILE_1}],
        data_dir=str(data_dir),
        catalog=catalog,
    )
    assert len(result.tilemap) == 1
    entry = result.tilemap[0]
    assert entry["x"] == 0
    assert entry["y"] == 0
    assert entry["tile_id"] == TILE_1
    assert entry["theme"] == "Classroom_and_Library"
    assert entry["semantic_type"] == "furniture"


def test_render_raises_on_unknown_tile(catalog_with_png_paths, data_dir):
    catalog = Catalog(catalog_with_png_paths)
    with pytest.raises(ValueError, match="Unknown tile_id"):
        render_map(
            grid_width=2, grid_height=2,
            placements=[{"x": 0, "y": 0, "tile_id": "unknown_id"}],
            data_dir=str(data_dir),
            catalog=catalog,
        )


def test_render_raises_on_map_type_mismatch(catalog_with_png_paths, data_dir):
    catalog = Catalog(catalog_with_png_paths)
    with pytest.raises(ValueError, match="map_type"):
        render_map(
            grid_width=2, grid_height=2,
            placements=[
                {"x": 0, "y": 0, "tile_id": TILE_1},  # interior
                {"x": 1, "y": 0, "tile_id": TILE_3},  # exterior
            ],
            data_dir=str(data_dir),
            catalog=catalog,
        )


def test_render_raises_when_no_data_dir(catalog_with_png_paths, monkeypatch):
    monkeypatch.delenv("PIXELART_DATA_DIR", raising=False)
    catalog = Catalog(catalog_with_png_paths)
    with pytest.raises(ValueError, match="data_dir"):
        render_map(
            grid_width=2, grid_height=2,
            placements=[{"x": 0, "y": 0, "tile_id": TILE_1}],
            catalog=catalog,
        )
```

- [ ] **Step 3: Run tests — expect FAIL**

```bash
pytest tests/test_renderer.py -v
```

Expected: `ImportError`

- [ ] **Step 4: Implement renderer.py**

```python
# pixelart_map/renderer.py
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
        # Empty grid — return blank canvas
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
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
pytest tests/test_renderer.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add pixelart_map/renderer.py tests/conftest.py tests/test_renderer.py
git commit -m "feat: renderer with validation and LRU image cache"
```

---

## Task 6: Verify LRU Cache Behavior

**Files:**
- Modify: `tests/test_renderer.py`

- [ ] **Step 1: Write cache test**

```python
# append to tests/test_renderer.py
from unittest.mock import patch
from pixelart_map import renderer as renderer_module

def test_lru_cache_loads_image_once(catalog_with_png_paths, data_dir):
    renderer_module._load_image.cache_clear()
    catalog = Catalog(catalog_with_png_paths)
    placements = [
        {"x": 0, "y": 0, "tile_id": TILE_1},
        {"x": 1, "y": 0, "tile_id": TILE_1},
        {"x": 0, "y": 1, "tile_id": TILE_1},
    ]
    render_map(
        grid_width=3, grid_height=3,
        placements=placements,
        data_dir=str(data_dir),
        catalog=catalog,
    )
    info = renderer_module._load_image.cache_info()
    assert info.hits == 2   # second and third placement hit cache
    assert info.misses == 1  # first placement loads from disk
```

- [ ] **Step 2: Run test — expect PASS** (cache is already implemented)

```bash
pytest tests/test_renderer.py::test_lru_cache_loads_image_once -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_renderer.py
git commit -m "test: verify LRU cache hits on repeated tile placements"
```

---

## Task 7: Ollama Client

**Files:**
- Create: `pixelart_map/_ollama.py`
- Create: `tests/test_ollama.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ollama.py
import json
import pytest
import httpx
from unittest.mock import patch, MagicMock
from pathlib import Path
from PIL import Image
import io

from pixelart_map._ollama import analyze_tile


@pytest.fixture
def tiny_png(tmp_path) -> Path:
    img = Image.new("RGBA", (48, 48), (200, 100, 50, 255))
    p = tmp_path / "tile.png"
    img.save(p)
    return p


def _mock_response(content: dict) -> MagicMock:
    mock = MagicMock(spec=httpx.Response)
    mock.raise_for_status.return_value = None
    mock.json.return_value = {"message": {"content": json.dumps(content)}}
    return mock


def test_analyze_tile_returns_dict(tiny_png):
    expected = {
        "description": "A red square tile",
        "semantic_type": "floor",
        "tags": ["red", "floor"],
    }
    with patch("httpx.post", return_value=_mock_response(expected)) as mock_post:
        result = analyze_tile(tiny_png, host="http://localhost:11434", model="qwen2-vl")

    assert result == expected
    mock_post.assert_called_once()


def test_analyze_tile_request_format(tiny_png):
    expected = {"description": "x", "semantic_type": "floor", "tags": []}
    with patch("httpx.post", return_value=_mock_response(expected)) as mock_post:
        analyze_tile(tiny_png, host="http://localhost:11434", model="qwen2-vl")

    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
    assert payload["stream"] is False
    assert payload["format"] == "json"
    assert payload["model"] == "qwen2-vl"
    msg = payload["messages"][0]
    assert msg["role"] == "user"
    assert len(msg["images"]) == 1
    # Must be raw base64, not a data-URI
    assert not msg["images"][0].startswith("data:")


def test_analyze_tile_returns_none_on_bad_json(tiny_png):
    mock = MagicMock(spec=httpx.Response)
    mock.raise_for_status.return_value = None
    mock.json.return_value = {"message": {"content": "not valid json {"}}
    with patch("httpx.post", return_value=mock):
        result = analyze_tile(tiny_png, host="http://localhost:11434", model="qwen2-vl")
    assert result is None


def test_analyze_tile_returns_none_on_missing_keys(tiny_png):
    with patch("httpx.post", return_value=_mock_response({"description": "x"})):
        result = analyze_tile(tiny_png, host="http://localhost:11434", model="qwen2-vl")
    assert result is None


def test_analyze_tile_returns_none_on_http_error(tiny_png):
    with patch("httpx.post", side_effect=httpx.RequestError("connection refused")):
        result = analyze_tile(tiny_png, host="http://localhost:11434", model="qwen2-vl")
    assert result is None
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_ollama.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement _ollama.py**

```python
# pixelart_map/_ollama.py
from __future__ import annotations
import base64
import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_PROMPT = (
    "You are analyzing a pixel art tile for a top-down 2D game.\n"
    "Respond with valid JSON only, no markdown, matching this schema:\n"
    '{\n'
    '  "description": "<one sentence: what this tile depicts>",\n'
    '  "semantic_type": "<one of: floor, wall, furniture, decoration, terrain, prop, building, vehicle>",\n'
    '  "tags": ["<keyword>", ...]\n'
    '}'
)

_REQUIRED_KEYS = {"description", "semantic_type", "tags"}


def analyze_tile(
    image_path: Path,
    host: str = "http://localhost:11434",
    model: str = "qwen2-vl",
) -> dict | None:
    """Call Ollama to describe a tile image. Returns parsed dict or None on failure."""
    image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [{
            "role": "user",
            "content": _PROMPT,
            "images": [image_b64],
        }],
    }
    try:
        response = httpx.post(f"{host}/api/chat", json=payload, timeout=60.0)
        response.raise_for_status()
        raw = response.json()["message"]["content"]
        result = json.loads(raw)
    except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Ollama call failed for %s: %s", image_path, e)
        return None

    if not _REQUIRED_KEYS.issubset(result.keys()):
        logger.warning("Ollama response missing keys for %s: %s", image_path, result)
        return None

    return result
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_ollama.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pixelart_map/_ollama.py tests/test_ollama.py
git commit -m "feat: Ollama client with error handling"
```

---

## Task 8: Analyzer CLI

**Files:**
- Create: `pixelart_map/analyzer.py`
- Create: `tests/test_analyzer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analyzer.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch, call
from pixelart_map.analyzer import build_catalog, compute_tile_id


def make_asset_tree(base: Path) -> dict[str, Path]:
    """Create a minimal fake asset tree with 2 interior + 1 exterior PNG."""
    interior_dir = (
        base
        / "moderninteriors-win"
        / "1_Interiors"
        / "48x48"
        / "Theme_Sorter_Shadowless_Singles_48x48"
        / "5_Classroom_and_Library_Singles_Shadowless_48x48"
    )
    exterior_dir = (
        base
        / "modernexteriors-win"
        / "Modern_Exteriors_16x16"
        / "ME_Theme_Sorter_16x16"
        / "16_Office_Singles_16x16"
    )
    interior_dir.mkdir(parents=True)
    exterior_dir.mkdir(parents=True)

    from PIL import Image
    tiles = {}
    for name, size, d in [
        ("tile_a.png", (48, 48), interior_dir),
        ("tile_b.png", (48, 96), interior_dir),
        ("tile_c.png", (16, 16), exterior_dir),
    ]:
        p = d / name
        Image.new("RGBA", size, (100, 100, 100, 255)).save(p)
        tiles[name] = p
    return tiles


def _fake_analyze(path, host, model):
    return {
        "description": f"A tile at {Path(path).name}",
        "semantic_type": "floor",
        "tags": ["test"],
    }


def test_build_catalog_produces_entries(tmp_path):
    make_asset_tree(tmp_path)
    with patch("pixelart_map.analyzer.analyze_tile", side_effect=_fake_analyze):
        catalog = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")

    assert len(catalog["tiles"]) == 3
    assert catalog["version"] == 1
    assert "generated_at" in catalog


def test_build_catalog_tile_fields(tmp_path):
    make_asset_tree(tmp_path)
    with patch("pixelart_map.analyzer.analyze_tile", side_effect=_fake_analyze):
        catalog = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")

    tiles = list(catalog["tiles"].values())
    interior = next(t for t in tiles if t["map_type"] == "interior" and t["pixel_height"] == 48)
    assert interior["theme"] == "Classroom_and_Library"
    assert interior["grid_unit"] == 48
    assert interior["pixel_width"] == 48

    tall = next(t for t in tiles if t["pixel_height"] == 96)
    assert tall["map_type"] == "interior"
    assert tall["pixel_height"] == 96

    exterior = next(t for t in tiles if t["map_type"] == "exterior")
    assert exterior["theme"] == "Office"
    assert exterior["grid_unit"] == 16


def test_build_catalog_skips_already_analyzed(tmp_path):
    make_asset_tree(tmp_path)
    with patch("pixelart_map.analyzer.analyze_tile", side_effect=_fake_analyze) as mock_analyze:
        catalog1 = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")
        assert mock_analyze.call_count == 3

        # Second run with existing catalog should call analyze_tile 0 times
        catalog2 = build_catalog(
            data_dir=tmp_path,
            host="http://localhost:11434",
            model="qwen2-vl",
            existing=catalog1,
        )
        assert mock_analyze.call_count == 3  # unchanged


def test_build_catalog_skips_failed_tiles(tmp_path):
    make_asset_tree(tmp_path)
    with patch("pixelart_map.analyzer.analyze_tile", return_value=None):
        catalog = build_catalog(data_dir=tmp_path, host="http://localhost:11434", model="qwen2-vl")
    # Failed tiles are skipped, not added
    assert len(catalog["tiles"]) == 0


def test_compute_tile_id_is_sha256(tmp_path):
    import hashlib
    rel_path = "some/path/tile.png"
    expected = hashlib.sha256(rel_path.encode()).hexdigest()
    assert compute_tile_id(rel_path) == expected
    assert len(compute_tile_id(rel_path)) == 64
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_analyzer.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement analyzer.py**

```python
# pixelart_map/analyzer.py
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
        default=os.environ.get("OLLAMA_MODEL", "qwen2-vl"),
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
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_analyzer.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pixelart_map/analyzer.py tests/test_analyzer.py
git commit -m "feat: analyzer CLI with incremental catalog building"
```

---

## Task 9: Public API + get_catalog()

**Files:**
- Modify: `pixelart_map/__init__.py`
- Modify: `tests/test_catalog.py`

- [ ] **Step 1: Write failing tests**

```python
# append to tests/test_catalog.py
import os
from pixelart_map import get_catalog, render_map


def test_public_imports():
    """Both public functions are importable from pixelart_map."""
    assert callable(get_catalog)
    assert callable(render_map)


def test_get_catalog_uses_env_var(sample_catalog_path, monkeypatch):
    monkeypatch.setenv("PIXELART_CATALOG_PATH", str(sample_catalog_path))
    catalog = get_catalog()
    assert len(catalog.themes()) > 0


def test_get_catalog_called_twice_returns_same_data(sample_catalog_path, monkeypatch):
    monkeypatch.setenv("PIXELART_CATALOG_PATH", str(sample_catalog_path))
    c1 = get_catalog()
    c2 = get_catalog()
    assert c1.themes() == c2.themes()
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_catalog.py::test_public_imports tests/test_catalog.py::test_get_catalog_uses_env_var -v
```

Expected: `ImportError` on `get_catalog`

- [ ] **Step 3: Implement __init__.py**

```python
# pixelart_map/__init__.py
from __future__ import annotations
import os
from pathlib import Path

from pixelart_map.catalog import Catalog
from pixelart_map.renderer import render_map

__all__ = ["get_catalog", "render_map"]

_DEFAULT_CATALOG_PATH = Path(__file__).parent.parent / "catalog.json"


def get_catalog() -> Catalog:
    """Load and return the tile catalog.

    Resolution order:
    1. PIXELART_CATALOG_PATH environment variable
    2. catalog.json next to the package root
    """
    path = os.environ.get("PIXELART_CATALOG_PATH")
    if path:
        return Catalog(Path(path))
    return Catalog(_DEFAULT_CATALOG_PATH)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_catalog.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Run the full test suite**

```bash
pytest --tb=short -v
```

Expected: all tests PASS, no warnings about missing fixtures

- [ ] **Step 6: Commit**

```bash
git add pixelart_map/__init__.py tests/test_catalog.py
git commit -m "feat: public API — get_catalog() and render_map() exports"
```

---

## Task 10: CLAUDE.md

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Create CLAUDE.md**

```markdown
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

# Run the analyzer (requires Ollama running + qwen2-vl pulled + data/ present)
python -m pixelart_map.analyzer --data-dir ./data --output catalog.json

# Or via installed entrypoint
pixelart-analyze --data-dir ./data
```

## Key Architecture Notes

- `data/` is gitignored — never committed. Assets are deployed via CI/CD.
- `catalog.json` IS committed — it's the build artifact produced by the offline analyzer.
- The analyzer scans only two specific subtrees (see spec), not all of `data/`.
- Tile IDs are full 64-char SHA-256 hashes of the relative path string.
- `_theme.py` contains the strip/normalize logic for turning folder names into theme names — it handles several typos in the original asset pack directory names.
- The renderer's `_load_image()` is LRU-cached at the module level (capacity 256). Call `renderer._load_image.cache_clear()` in tests that care about cache hit counts.
- Tests create all PNG fixtures programmatically with Pillow — no real assets needed.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md with commands and architecture notes"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
pytest --tb=short -v
```

Expected: all tests PASS

- [ ] **Verify CLI entrypoint is installed**

```bash
pixelart-analyze --help
```

Expected: shows usage with `--data-dir`, `--output`, `--host`, `--model` options

- [ ] **Verify package imports cleanly**

```bash
python -c "from pixelart_map import get_catalog, render_map; print('ok')"
```

Expected: `ok`
