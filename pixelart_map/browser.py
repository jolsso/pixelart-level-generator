"""Catalog browser — a Flask app for reviewing and rating analyzed tiles.

Run via: pixelart-browse --data-dir ./data --catalog catalog.db
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
from pathlib import Path

from flask import Flask, Response, request, send_file

from pixelart_map.catalog import open_catalog_db

logger = logging.getLogger(__name__)

app = Flask(__name__)

_db_path: Path | None = None
_data_dir: Path | None = None


def _get_conn() -> sqlite3.Connection:
    assert _db_path is not None
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ── API endpoints ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return _INDEX_HTML


@app.route("/api/tiles")
def api_tiles():
    """Paginated, filterable tile listing."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 48, type=int)
    per_page = min(per_page, 200)

    # Filters
    theme = request.args.get("theme", "")
    semantic_type = request.args.get("semantic_type", "")
    map_type = request.args.get("map_type", "")
    layer = request.args.get("layer", "")
    search = request.args.get("search", "")
    conf_min = request.args.get("conf_min", 0.0, type=float)
    conf_max = request.args.get("conf_max", 1.0, type=float)
    feedback_filter = request.args.get("feedback", "")  # "up", "down", "none", ""
    passable = request.args.get("passable", "")  # "true", "false", ""

    where = []
    params: list = []

    if theme:
        where.append("theme = ?")
        params.append(theme)
    if semantic_type:
        where.append("semantic_type = ?")
        params.append(semantic_type)
    if map_type:
        where.append("map_type = ?")
        params.append(map_type)
    if layer:
        where.append("layer = ?")
        params.append(layer)
    if search:
        where.append("(description LIKE ? OR tags LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if conf_min > 0:
        where.append("(confidence IS NULL OR confidence >= ?)")
        params.append(conf_min)
    if conf_max < 1.0:
        where.append("(confidence IS NULL OR confidence <= ?)")
        params.append(conf_max)
    if feedback_filter == "up":
        where.append("feedback = 1")
    elif feedback_filter == "down":
        where.append("feedback = -1")
    elif feedback_filter == "none":
        where.append("feedback IS NULL")
    if passable == "true":
        where.append("passable = 1")
    elif passable == "false":
        where.append("passable = 0")

    where_clause = " AND ".join(where) if where else "1=1"
    offset = (page - 1) * per_page

    conn = _get_conn()
    count = conn.execute(
        f"SELECT COUNT(*) FROM tiles WHERE {where_clause}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"SELECT * FROM tiles WHERE {where_clause} ORDER BY path "
        f"LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()

    tiles = []
    for r in rows:
        tiles.append({
            "id": r["id"],
            "path": r["path"],
            "theme": r["theme"],
            "map_type": r["map_type"],
            "semantic_type": r["semantic_type"],
            "description": r["description"],
            "tags": json.loads(r["tags"]),
            "confidence": r["confidence"],
            "reasoning": r["reasoning"],
            "layer": r["layer"],
            "passable": bool(r["passable"]) if r["passable"] is not None else None,
            "feedback": r["feedback"],
        })
    conn.close()

    return {
        "tiles": tiles,
        "total": count,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (count + per_page - 1) // per_page),
    }


@app.route("/api/filters")
def api_filters():
    """Return distinct values for filter dropdowns."""
    conn = _get_conn()
    themes = [r[0] for r in conn.execute("SELECT DISTINCT theme FROM tiles ORDER BY theme")]
    types = [r[0] for r in conn.execute("SELECT DISTINCT semantic_type FROM tiles ORDER BY semantic_type")]
    map_types = [r[0] for r in conn.execute("SELECT DISTINCT map_type FROM tiles ORDER BY map_type")]
    layers = [r[0] for r in conn.execute("SELECT DISTINCT layer FROM tiles WHERE layer IS NOT NULL ORDER BY layer")]
    total = conn.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]
    conn.close()
    return {"themes": themes, "semantic_types": types, "map_types": map_types, "layers": layers, "total": total}


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """Set feedback for a tile. Body: {"id": "...", "feedback": 1|-1|null}"""
    data = request.get_json()
    tile_id = data.get("id")
    feedback = data.get("feedback")  # 1, -1, or None
    if tile_id is None:
        return {"error": "missing id"}, 400
    if feedback not in (1, -1, None):
        return {"error": "feedback must be 1, -1, or null"}, 400

    conn = _get_conn()
    conn.execute("UPDATE tiles SET feedback = ? WHERE id = ?", (feedback, tile_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.route("/tile/<path:rel_path>")
def serve_tile(rel_path: str):
    if _data_dir is None:
        return "data_dir not set", 500
    abs_path = (_data_dir / rel_path).resolve()
    if not abs_path.exists():
        return "not found", 404
    return send_file(str(abs_path), mimetype="image/png")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Browse the tile catalog")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("PIXELART_DATA_DIR", "./data"),
        help="Root path of the pixel art asset folder",
    )
    parser.add_argument(
        "--catalog",
        default="catalog.db",
        help="Path to catalog.db (default: catalog.db)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5556,
        help="Port to run the browser on (default: 5556)",
    )
    args = parser.parse_args()

    global _db_path, _data_dir
    _db_path = Path(args.catalog).resolve()
    _data_dir = Path(args.data_dir).resolve()

    if not _db_path.exists():
        print(f"Catalog not found: {_db_path}")
        return

    # Ensure migration runs
    conn = open_catalog_db(_db_path)
    total = conn.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]
    conn.close()
    print(f"Catalog: {total:,} tiles")
    print(f"Browse at http://127.0.0.1:{args.port}")

    wlog = logging.getLogger("werkzeug")
    wlog.setLevel(logging.WARNING)
    app.run(host="127.0.0.1", port=args.port, debug=False)


# ── HTML ─────────────────────────────────────────────────────────────────────

_INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tile Catalog Browser</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  background: #0f1117; color: #e0e0e0;
  min-height: 100vh;
}
.header {
  padding: 16px 24px;
  background: #161825;
  border-bottom: 1px solid #252840;
  position: sticky; top: 0; z-index: 10;
}
.header h1 { font-size: 1.2rem; color: #a0a8c0; margin-bottom: 12px; }
.filters {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
}
.filters select, .filters input {
  background: #1e2130; color: #c0c8e0; border: 1px solid #303450;
  border-radius: 6px; padding: 5px 10px; font-size: 0.8rem;
}
.filters select:focus, .filters input:focus {
  outline: none; border-color: #4a6cf7;
}
.filters input[type="text"] { width: 160px; }
.filters input[type="number"] { width: 70px; }
.filters label { font-size: 0.75rem; color: #8890a8; }
.filter-group { display: flex; align-items: center; gap: 4px; }
.stats {
  padding: 8px 24px; font-size: 0.8rem; color: #6a7090;
  border-bottom: 1px solid #1e2130;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px; padding: 16px 24px;
}
.card {
  background: #1a1d2e; border-radius: 10px; padding: 12px;
  display: flex; flex-direction: column; align-items: center;
  border: 2px solid #252840; transition: border-color 0.2s;
  cursor: default;
}
.card:hover { border-color: #3a3d60; }
.card.voted-up { border-color: #2a6a2a; }
.card.voted-down { border-color: #6a2a2a; }
.card img {
  max-width: 100%; max-height: 96px;
  image-rendering: pixelated; border-radius: 4px;
  background: #12141f; margin-bottom: 8px;
}
.card .desc {
  font-size: 0.8rem; color: #c0c8e0; text-align: center;
  margin-bottom: 4px; font-weight: 500;
}
.card .meta {
  display: flex; flex-wrap: wrap; gap: 4px; justify-content: center;
  margin-bottom: 4px;
}
.badge {
  font-size: 0.6rem; background: #252840; color: #8890a8;
  border-radius: 3px; padding: 1px 6px;
}
.card .tags {
  display: flex; flex-wrap: wrap; gap: 3px; justify-content: center;
  margin-bottom: 6px;
}
.tag {
  font-size: 0.6rem; background: #2a2d45; color: #7880a0;
  border-radius: 3px; padding: 1px 5px;
}
.conf {
  font-size: 0.65rem; font-weight: 600; border-radius: 4px;
  padding: 1px 8px; margin-bottom: 6px;
}
.conf.high { background: #1a3a1a; color: #6fbf6f; }
.conf.med { background: #3a3a1a; color: #bfbf4f; }
.conf.low { background: #3a1a1a; color: #bf4f4f; }
.vote-row {
  display: flex; gap: 8px; margin-top: auto;
}
.vote-btn {
  background: #252840; border: 1px solid #303450; border-radius: 6px;
  padding: 4px 12px; cursor: pointer; font-size: 0.9rem;
  transition: all 0.15s;
}
.vote-btn:hover { background: #303450; }
.vote-btn.active-up { background: #1a4a1a; border-color: #2a6a2a; }
.vote-btn.active-down { background: #4a1a1a; border-color: #6a2a2a; }
.pagination {
  display: flex; justify-content: center; align-items: center;
  gap: 12px; padding: 20px;
}
.pagination button {
  background: #252840; border: 1px solid #303450; color: #c0c8e0;
  border-radius: 6px; padding: 6px 16px; cursor: pointer;
  font-size: 0.8rem;
}
.pagination button:hover { background: #303450; }
.pagination button:disabled { opacity: 0.3; cursor: default; }
.pagination span { font-size: 0.85rem; color: #8890a8; }
.reasoning {
  font-size: 0.6rem; color: #5a6080; font-style: italic;
  text-align: center; margin-bottom: 4px;
}
.path-label {
  font-size: 0.55rem; color: #4a5070; text-align: center;
  word-break: break-all; margin-bottom: 4px;
}
</style>
</head>
<body>
<div class="header">
  <h1>Tile Catalog Browser</h1>
  <div class="filters" id="filters">
    <div class="filter-group">
      <label>Theme</label>
      <select id="f-theme"><option value="">All</option></select>
    </div>
    <div class="filter-group">
      <label>Type</label>
      <select id="f-type"><option value="">All</option></select>
    </div>
    <div class="filter-group">
      <label>Map</label>
      <select id="f-map"><option value="">All</option></select>
    </div>
    <div class="filter-group">
      <label>Layer</label>
      <select id="f-layer"><option value="">All</option></select>
    </div>
    <div class="filter-group">
      <label>Passable</label>
      <select id="f-passable">
        <option value="">All</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    </div>
    <div class="filter-group">
      <label>Feedback</label>
      <select id="f-feedback">
        <option value="">All</option>
        <option value="up">Thumbs up</option>
        <option value="down">Thumbs down</option>
        <option value="none">Unrated</option>
      </select>
    </div>
    <div class="filter-group">
      <label>Confidence</label>
      <input type="number" id="f-conf-min" min="0" max="1" step="0.1" value="0" placeholder="min">
      <span style="color:#6a7090">-</span>
      <input type="number" id="f-conf-max" min="0" max="1" step="0.1" value="1" placeholder="max">
    </div>
    <div class="filter-group">
      <label>Search</label>
      <input type="text" id="f-search" placeholder="description or tag...">
    </div>
  </div>
</div>
<div class="stats" id="stats"></div>
<div class="grid" id="grid"></div>
<div class="pagination" id="pagination"></div>

<script>
let currentPage = 1;
let totalPages = 1;

function qs(id) { return document.getElementById(id); }

async function loadFilters() {
  const r = await fetch('/api/filters');
  const d = await r.json();
  fillSelect('f-theme', d.themes);
  fillSelect('f-type', d.semantic_types);
  fillSelect('f-map', d.map_types);
  fillSelect('f-layer', d.layers);
}

function fillSelect(id, items) {
  const sel = qs(id);
  items.forEach(function(v) {
    const o = document.createElement('option');
    o.value = v; o.textContent = v;
    sel.appendChild(o);
  });
}

function getFilters() {
  return {
    theme: qs('f-theme').value,
    semantic_type: qs('f-type').value,
    map_type: qs('f-map').value,
    layer: qs('f-layer').value,
    passable: qs('f-passable').value,
    feedback: qs('f-feedback').value,
    conf_min: qs('f-conf-min').value,
    conf_max: qs('f-conf-max').value,
    search: qs('f-search').value,
    page: currentPage,
  };
}

async function loadTiles() {
  const f = getFilters();
  const params = new URLSearchParams();
  Object.entries(f).forEach(function(kv) { if (kv[1]) params.set(kv[0], kv[1]); });
  const r = await fetch('/api/tiles?' + params.toString());
  const d = await r.json();
  totalPages = d.pages;
  qs('stats').textContent = d.total + ' tiles found \u2014 page ' + d.page + ' of ' + d.pages;
  renderGrid(d.tiles);
  renderPagination(d.page, d.pages);
}

function renderGrid(tiles) {
  const grid = qs('grid');
  grid.replaceChildren();
  tiles.forEach(function(t) {
    const card = document.createElement('div');
    card.className = 'card' + (t.feedback === 1 ? ' voted-up' : t.feedback === -1 ? ' voted-down' : '');
    card.dataset.id = t.id;

    const img = document.createElement('img');
    img.src = '/tile/' + t.path;
    img.alt = t.description;
    card.appendChild(img);

    const pathParts = t.path.split(/[\/\\]/);
    const pathEl = document.createElement('div');
    pathEl.className = 'path-label';
    pathEl.textContent = pathParts.slice(-2).join('/');
    card.appendChild(pathEl);

    const desc = document.createElement('div');
    desc.className = 'desc';
    desc.textContent = t.description;
    card.appendChild(desc);

    const meta = document.createElement('div');
    meta.className = 'meta';
    [t.semantic_type, t.layer, t.passable != null ? (t.passable ? 'passable' : 'blocking') : null, t.theme]
      .filter(Boolean).forEach(function(v) {
        const b = document.createElement('span');
        b.className = 'badge'; b.textContent = v;
        meta.appendChild(b);
      });
    card.appendChild(meta);

    if (t.confidence != null) {
      const conf = document.createElement('div');
      const pct = (t.confidence * 100).toFixed(0);
      conf.className = 'conf ' + (t.confidence >= 0.7 ? 'high' : t.confidence >= 0.4 ? 'med' : 'low');
      conf.textContent = pct + '%';
      card.appendChild(conf);
    }

    if (t.tags && t.tags.length > 0) {
      const tagsDiv = document.createElement('div');
      tagsDiv.className = 'tags';
      t.tags.forEach(function(tag) {
        const s = document.createElement('span');
        s.className = 'tag'; s.textContent = tag;
        tagsDiv.appendChild(s);
      });
      card.appendChild(tagsDiv);
    }

    if (t.reasoning) {
      const reas = document.createElement('div');
      reas.className = 'reasoning';
      reas.textContent = t.reasoning;
      card.appendChild(reas);
    }

    const voteRow = document.createElement('div');
    voteRow.className = 'vote-row';

    const upBtn = document.createElement('button');
    upBtn.className = 'vote-btn' + (t.feedback === 1 ? ' active-up' : '');
    upBtn.textContent = '\u{1F44D}';
    upBtn.onclick = function() { vote(t.id, t.feedback === 1 ? null : 1, card); };

    const downBtn = document.createElement('button');
    downBtn.className = 'vote-btn' + (t.feedback === -1 ? ' active-down' : '');
    downBtn.textContent = '\u{1F44E}';
    downBtn.onclick = function() { vote(t.id, t.feedback === -1 ? null : -1, card); };

    voteRow.appendChild(upBtn);
    voteRow.appendChild(downBtn);
    card.appendChild(voteRow);

    grid.appendChild(card);
  });
}

async function vote(id, feedback, card) {
  await fetch('/api/feedback', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id: id, feedback: feedback}),
  });
  // Update card visually
  card.className = 'card' + (feedback === 1 ? ' voted-up' : feedback === -1 ? ' voted-down' : '');
  const btns = card.querySelectorAll('.vote-btn');
  btns[0].className = 'vote-btn' + (feedback === 1 ? ' active-up' : '');
  btns[1].className = 'vote-btn' + (feedback === -1 ? ' active-down' : '');
}

function renderPagination(page, pages) {
  const div = qs('pagination');
  div.replaceChildren();

  const prev = document.createElement('button');
  prev.textContent = 'Previous';
  prev.disabled = page <= 1;
  prev.onclick = function() { currentPage--; loadTiles(); };

  const info = document.createElement('span');
  info.textContent = page + ' / ' + pages;

  const next = document.createElement('button');
  next.textContent = 'Next';
  next.disabled = page >= pages;
  next.onclick = function() { currentPage++; loadTiles(); };

  div.appendChild(prev);
  div.appendChild(info);
  div.appendChild(next);
}

// Wire up filter changes
document.querySelectorAll('.filters select, .filters input').forEach(function(el) {
  el.addEventListener('change', function() { currentPage = 1; loadTiles(); });
});
qs('f-search').addEventListener('input', debounce(function() { currentPage = 1; loadTiles(); }, 300));

function debounce(fn, ms) {
  let t;
  return function() {
    clearTimeout(t);
    t = setTimeout(fn, ms);
  };
}

loadFilters().then(loadTiles);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
