from __future__ import annotations

import os
from pathlib import Path

from pixelart_map.catalog import Catalog
from pixelart_map.renderer import render_map

__all__ = ["get_catalog", "render_map"]

_DEFAULT_CATALOG_PATH = Path(__file__).parent.parent / "catalog.db"


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
