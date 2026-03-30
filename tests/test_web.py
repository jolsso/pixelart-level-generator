import json
import pytest
from pathlib import Path
from pixelart_map.web import AnalyzerMonitor, TileState, app


class TestTileState:
    def test_to_dict(self):
        ts = TileState(
            path="foo/bar.png", abs_path="/abs/foo/bar.png",
            theme="Office", description="A desk", semantic_type="furniture",
            tags=["desk", "office"],
        )
        d = ts.to_dict()
        assert d["path"] == "foo/bar.png"
        assert d["description"] == "A desk"
        assert d["tags"] == ["desk", "office"]
        assert "abs_path" not in d


class TestAnalyzerMonitor:
    def test_subscribe_gets_initial_state(self):
        m = AnalyzerMonitor()
        m.set_total(10, 5)
        q = m.subscribe()
        msg = q.get_nowait()
        data = json.loads(msg.removeprefix("data: ").strip())
        assert data["total"] == 10
        assert data["skipped"] == 5

    def test_begin_and_finish_tile(self):
        m = AnalyzerMonitor()
        m.set_total(2, 0)
        q = m.subscribe()
        q.get_nowait()  # discard initial

        current = TileState(path="a.png", abs_path="/a.png", theme="T")
        nxt = TileState(path="b.png", abs_path="/b.png", theme="T")
        m.begin_tile(current, nxt)
        msg = json.loads(q.get_nowait().removeprefix("data: ").strip())
        assert msg["current"]["path"] == "a.png"
        assert msg["next"]["path"] == "b.png"

        result = TileState(
            path="a.png", abs_path="/a.png", theme="T",
            description="A tile", semantic_type="floor", tags=["tag"],
        )
        m.finish_tile(result)
        msg = json.loads(q.get_nowait().removeprefix("data: ").strip())
        assert msg["processed"] == 1
        assert msg["previous"][0]["description"] == "A tile"

    def test_previous_limited_to_3(self):
        m = AnalyzerMonitor()
        for i in range(5):
            m.finish_tile(TileState(
                path=f"{i}.png", abs_path=f"/{i}.png",
                description=f"tile {i}", semantic_type="floor", tags=[],
            ))
        assert len(m.previous) == 3
        assert m.previous[0].description == "tile 4"

    def test_finish_all_sends_done_event(self):
        m = AnalyzerMonitor()
        q = m.subscribe()
        q.get_nowait()  # discard initial
        m.finish_all()
        msg = q.get_nowait()
        assert "event: done" in msg


class TestFlaskRoutes:
    @pytest.fixture()
    def client(self):
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"pixelart-analyze monitor" in resp.data

    def test_tile_serves_image(self, client, tmp_path):
        import pixelart_map.web as web
        web._data_dir = tmp_path
        img_path = tmp_path / "sub" / "tile.png"
        img_path.parent.mkdir()
        from PIL import Image
        Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(img_path)

        resp = client.get("/tile/sub/tile.png")
        assert resp.status_code == 200
        assert resp.content_type == "image/png"

    def test_tile_not_found(self, client, tmp_path):
        import pixelart_map.web as web
        web._data_dir = tmp_path
        resp = client.get("/tile/nonexistent.png")
        assert resp.status_code == 404
