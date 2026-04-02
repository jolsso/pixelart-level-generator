import json
import pytest
from pathlib import Path
from PIL import Image
from pixelart_map.catalog import open_catalog_db, insert_tile

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_catalog_path(tmp_path):
    """SQLite catalog with the standard 3 test tiles, built from sample_catalog.json."""
    data = json.loads((FIXTURES_DIR / "sample_catalog.json").read_text())
    db_path = tmp_path / "sample_catalog.db"
    conn = open_catalog_db(db_path)
    for tile in data["tiles"].values():
        insert_tile(conn, tile)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def sample_catalog_data():
    return json.loads((FIXTURES_DIR / "sample_catalog.json").read_text())


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
    Image.new("RGBA", (48, 48), (255, 0, 0, 255)).save(interior_dir / "tile_01.png")
    # 48x96 blue tile (2-cell tall)
    Image.new("RGBA", (48, 96), (0, 0, 255, 255)).save(interior_dir / "tile_02.png")
    # 16x16 green tile
    Image.new("RGBA", (16, 16), (0, 255, 0, 255)).save(exterior_dir / "tile_01.png")

    return tmp_path


@pytest.fixture
def catalog_with_png_paths(tmp_path, data_dir, sample_catalog_data):
    """A catalog.db whose tile paths point to the tmp data_dir fixtures."""
    data = sample_catalog_data
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
    db_path = tmp_path / "catalog.db"
    conn = open_catalog_db(db_path)
    for tile in data["tiles"].values():
        insert_tile(conn, tile)
    conn.commit()
    conn.close()
    return db_path
