import json
import pytest
from pathlib import Path
from PIL import Image

import pixelart_map.browser as browser
from pixelart_map.catalog import open_catalog_db, insert_tile


def _seed_db(db_path, data_dir, count=5):
    """Create a catalog.db with test tiles and matching PNGs."""
    conn = open_catalog_db(db_path)
    for i in range(count):
        theme = "Kitchen" if i % 2 == 0 else "Bathroom"
        stype = "floor" if i % 3 == 0 else "object"
        tile = {
            "id": f"tile_{i}",
            "path": f"theme/{theme}/tile_{i}.png",
            "theme": theme,
            "map_type": "interior",
            "grid_unit": 48,
            "pixel_width": 48,
            "pixel_height": 48,
            "description": f"test object {i}",
            "semantic_type": stype,
            "tags": ["test", theme.lower()],
            "confidence": 0.5 + i * 0.1,
            "reasoning": f"looks like object {i}",
            "layer": "object" if stype == "object" else "base",
            "passable": stype == "floor",
        }
        insert_tile(conn, tile)

        # Create the actual PNG file
        img_path = data_dir / tile["path"]
        img_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (48, 48), (100 + i * 30, 50, 50, 255)).save(img_path)

    conn.commit()
    conn.close()


@pytest.fixture()
def seeded_app(tmp_path):
    db_path = tmp_path / "catalog.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _seed_db(db_path, data_dir)

    browser._db_path = db_path
    browser._data_dir = data_dir
    browser.app.config["TESTING"] = True
    with browser.app.test_client() as client:
        yield client


class TestIndex:
    def test_returns_html(self, seeded_app):
        resp = seeded_app.get("/")
        assert resp.status_code == 200
        assert b"Tile Catalog Browser" in resp.data


class TestApiTiles:
    def test_returns_all_tiles(self, seeded_app):
        resp = seeded_app.get("/api/tiles")
        data = resp.get_json()
        assert data["total"] == 5
        assert len(data["tiles"]) == 5

    def test_filter_by_theme(self, seeded_app):
        resp = seeded_app.get("/api/tiles?theme=Kitchen")
        data = resp.get_json()
        assert all(t["theme"] == "Kitchen" for t in data["tiles"])
        assert data["total"] == 3  # indices 0, 2, 4

    def test_filter_by_semantic_type(self, seeded_app):
        resp = seeded_app.get("/api/tiles?semantic_type=floor")
        data = resp.get_json()
        assert all(t["semantic_type"] == "floor" for t in data["tiles"])

    def test_filter_by_confidence_range(self, seeded_app):
        resp = seeded_app.get("/api/tiles?conf_min=0.7&conf_max=0.9")
        data = resp.get_json()
        for t in data["tiles"]:
            assert 0.7 <= t["confidence"] <= 0.9

    def test_search_by_description(self, seeded_app):
        resp = seeded_app.get("/api/tiles?search=object+3")
        data = resp.get_json()
        assert data["total"] == 1
        assert "object 3" in data["tiles"][0]["description"]

    def test_pagination(self, seeded_app):
        resp = seeded_app.get("/api/tiles?per_page=2&page=1")
        d1 = resp.get_json()
        assert len(d1["tiles"]) == 2
        assert d1["pages"] == 3

        resp = seeded_app.get("/api/tiles?per_page=2&page=3")
        d3 = resp.get_json()
        assert len(d3["tiles"]) == 1

    def test_filter_by_feedback(self, seeded_app):
        # Vote on one tile first
        seeded_app.post("/api/feedback",
                        json={"id": "tile_0", "feedback": 1},
                        content_type="application/json")
        resp = seeded_app.get("/api/tiles?feedback=up")
        data = resp.get_json()
        assert data["total"] == 1
        assert data["tiles"][0]["id"] == "tile_0"


class TestApiFilters:
    def test_returns_filter_options(self, seeded_app):
        resp = seeded_app.get("/api/filters")
        data = resp.get_json()
        assert "Kitchen" in data["themes"]
        assert "Bathroom" in data["themes"]
        assert data["total"] == 5


class TestApiFeedback:
    def test_thumbs_up(self, seeded_app):
        resp = seeded_app.post("/api/feedback",
                               json={"id": "tile_0", "feedback": 1},
                               content_type="application/json")
        assert resp.get_json()["ok"] is True

        # Verify it persisted
        resp = seeded_app.get("/api/tiles?feedback=up")
        assert resp.get_json()["tiles"][0]["feedback"] == 1

    def test_thumbs_down(self, seeded_app):
        seeded_app.post("/api/feedback",
                        json={"id": "tile_1", "feedback": -1},
                        content_type="application/json")
        resp = seeded_app.get("/api/tiles?feedback=down")
        assert resp.get_json()["tiles"][0]["feedback"] == -1

    def test_clear_feedback(self, seeded_app):
        seeded_app.post("/api/feedback",
                        json={"id": "tile_0", "feedback": 1},
                        content_type="application/json")
        seeded_app.post("/api/feedback",
                        json={"id": "tile_0", "feedback": None},
                        content_type="application/json")
        resp = seeded_app.get("/api/tiles?feedback=none")
        ids = [t["id"] for t in resp.get_json()["tiles"]]
        assert "tile_0" in ids

    def test_invalid_feedback_rejected(self, seeded_app):
        resp = seeded_app.post("/api/feedback",
                               json={"id": "tile_0", "feedback": 5},
                               content_type="application/json")
        assert resp.status_code == 400


class TestTileServing:
    def test_serves_image(self, seeded_app):
        resp = seeded_app.get("/tile/theme/Kitchen/tile_0.png")
        assert resp.status_code == 200
        assert resp.content_type == "image/png"

    def test_not_found(self, seeded_app):
        resp = seeded_app.get("/tile/nonexistent.png")
        assert resp.status_code == 404
