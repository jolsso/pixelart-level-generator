"""Live web monitor for the pixelart-analyze CLI.

Runs a Flask server in a background thread that streams analysis progress
via Server-Sent Events. Shows the current tile being analyzed, the next
tile in the queue, and the previous 3 analyzed tiles with their results.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path

from flask import Flask, Response, send_file

logger = logging.getLogger(__name__)


@dataclass
class TileState:
    """Snapshot of a tile shown in the monitor."""
    path: str  # relative path within data_dir
    abs_path: str  # absolute path for serving the image
    theme: str = ""
    description: str = ""
    semantic_type: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "theme": self.theme,
            "description": self.description,
            "semantic_type": self.semantic_type,
            "tags": self.tags,
        }


class AnalyzerMonitor:
    """Thread-safe state holder that bridges the analyzer loop and the web UI."""

    def __init__(self) -> None:
        self.total: int = 0
        self.processed: int = 0
        self.skipped: int = 0
        self.current: TileState | None = None
        self.next: TileState | None = None
        self.previous: list[TileState] = []  # most recent first, max 3
        self._subscribers: list[queue.Queue[str]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
            # Send current state immediately
            q.put(self._snapshot_event())
        return q

    def unsubscribe(self, q: queue.Queue[str]) -> None:
        with self._lock:
            self._subscribers = [s for s in self._subscribers if s is not q]

    def set_total(self, total: int, skipped: int) -> None:
        with self._lock:
            self.total = total
            self.skipped = skipped
            self._broadcast()

    def begin_tile(self, current: TileState, next_tile: TileState | None) -> None:
        with self._lock:
            self.current = current
            self.next = next_tile
            self._broadcast()

    def finish_tile(self, result: TileState) -> None:
        with self._lock:
            self.processed += 1
            self.previous.insert(0, result)
            self.previous = self.previous[:3]
            self.current = None
            self._broadcast()

    def finish_all(self) -> None:
        with self._lock:
            self.current = None
            self.next = None
            self._broadcast_raw("event: done\ndata: {}\n\n")

    def _snapshot_event(self) -> str:
        data = {
            "total": self.total,
            "processed": self.processed,
            "skipped": self.skipped,
            "current": self.current.to_dict() if self.current else None,
            "next": self.next.to_dict() if self.next else None,
            "previous": [t.to_dict() for t in self.previous],
        }
        return f"data: {json.dumps(data)}\n\n"

    def _broadcast(self) -> None:
        msg = self._snapshot_event()
        self._broadcast_raw(msg)

    def _broadcast_raw(self, msg: str) -> None:
        dead: list[queue.Queue[str]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            self._subscribers = [s for s in self._subscribers if s is not q]


# ── Singleton monitor instance ──────────────────────────────────────────────

_monitor: AnalyzerMonitor | None = None
_data_dir: Path | None = None


def get_monitor() -> AnalyzerMonitor:
    global _monitor
    if _monitor is None:
        _monitor = AnalyzerMonitor()
    return _monitor


# ── Flask app ────────────────────────────────────────────────────────────────

app = Flask(__name__)


@app.route("/")
def index():
    return _INDEX_HTML


@app.route("/events")
def events():
    monitor = get_monitor()
    q = monitor.subscribe()

    def stream():
        try:
            while True:
                msg = q.get()
                yield msg
        except GeneratorExit:
            monitor.unsubscribe(q)

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/tile/<path:rel_path>")
def serve_tile(rel_path: str):
    if _data_dir is None:
        return "data_dir not set", 500
    abs_path = (_data_dir / rel_path).resolve()
    if not abs_path.exists():
        return "not found", 404
    return send_file(str(abs_path), mimetype="image/png")


def start_server(data_dir: Path, port: int = 5555) -> AnalyzerMonitor:
    """Start the web monitor in a daemon thread and return the monitor."""
    global _data_dir
    _data_dir = data_dir.resolve()
    monitor = get_monitor()

    # Suppress Flask request logging
    wlog = logging.getLogger("werkzeug")
    wlog.setLevel(logging.WARNING)

    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    thread.start()
    print(f"Web monitor running at http://127.0.0.1:{port}")
    return monitor


# ── Inline HTML ──────────────────────────────────────────────────────────────

_INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pixelart-analyze monitor</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: #0f1117;
    color: #e0e0e0;
    min-height: 100vh;
    padding: 24px;
  }
  h1 { font-size: 1.4rem; margin-bottom: 16px; color: #a0a8c0; }
  .progress-bar-outer {
    background: #1e2130;
    border-radius: 8px;
    height: 28px;
    margin-bottom: 24px;
    overflow: hidden;
    position: relative;
  }
  .progress-bar-inner {
    background: linear-gradient(90deg, #4a6cf7, #6e8efb);
    height: 100%;
    transition: width 0.4s ease;
    border-radius: 8px;
  }
  .progress-text {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
    font-weight: 600;
    color: #fff;
    text-shadow: 0 1px 2px rgba(0,0,0,0.5);
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr 1fr 1fr;
    gap: 16px;
  }
  .card {
    background: #1a1d2e;
    border-radius: 12px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    align-items: center;
    border: 2px solid transparent;
    transition: border-color 0.3s;
    min-height: 240px;
  }
  .card.current { border-color: #4a6cf7; }
  .card.next { border-color: #3a3d50; }
  .card.previous { border-color: #2a2d3e; }
  .card.empty { opacity: 0.3; }
  .card-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 8px;
    color: #8890a8;
  }
  .card.current .card-label { color: #6e8efb; }
  .card img {
    max-width: 100%;
    max-height: 140px;
    image-rendering: pixelated;
    border-radius: 4px;
    background: #12141f;
    margin-bottom: 10px;
  }
  .card .path {
    font-size: 0.65rem;
    color: #5a6080;
    word-break: break-all;
    text-align: center;
    margin-bottom: 6px;
  }
  .card .description {
    font-size: 0.82rem;
    color: #c0c8e0;
    text-align: center;
    margin-bottom: 4px;
  }
  .card .semantic {
    font-size: 0.72rem;
    color: #8890a8;
    background: #252840;
    border-radius: 4px;
    padding: 2px 8px;
    margin-bottom: 4px;
  }
  .card .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    justify-content: center;
  }
  .card .tag {
    font-size: 0.65rem;
    background: #2a2d45;
    color: #9098b8;
    border-radius: 3px;
    padding: 1px 6px;
  }
  .status-line {
    margin-bottom: 8px;
    font-size: 0.85rem;
    color: #8890a8;
  }
  .done-banner {
    display: none;
    background: #1a3a1a;
    color: #6fbf6f;
    text-align: center;
    padding: 12px;
    border-radius: 8px;
    margin-bottom: 16px;
    font-weight: 600;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  .card.current img { animation: pulse 2s ease-in-out infinite; }
</style>
</head>
<body>
<h1>pixelart-analyze monitor</h1>
<div class="status-line" id="status">Connecting...</div>
<div class="progress-bar-outer">
  <div class="progress-bar-inner" id="bar" style="width: 0%"></div>
  <div class="progress-text" id="bar-text">0 / 0</div>
</div>
<div class="done-banner" id="done-banner">Analysis complete!</div>
<div class="grid" id="grid"></div>

<script>
const grid = document.getElementById('grid');
const bar = document.getElementById('bar');
const barText = document.getElementById('bar-text');
const statusEl = document.getElementById('status');
const doneBanner = document.getElementById('done-banner');

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

function buildCard(tile, label, cssClass) {
  const card = document.createElement('div');
  card.className = 'card ' + cssClass + (tile ? '' : ' empty');

  const labelEl = document.createElement('div');
  labelEl.className = 'card-label';
  labelEl.textContent = label;
  card.appendChild(labelEl);

  if (!tile) {
    const empty = document.createElement('div');
    empty.className = 'description';
    empty.style.marginTop = 'auto';
    empty.style.marginBottom = 'auto';
    empty.textContent = '--';
    card.appendChild(empty);
    return card;
  }

  if (tile.path) {
    const img = document.createElement('img');
    img.src = '/tile/' + tile.path;
    img.alt = 'tile';
    card.appendChild(img);

    const pathParts = tile.path.split(/[\/\\]/);
    const pathEl = document.createElement('div');
    pathEl.className = 'path';
    pathEl.textContent = pathParts.slice(-2).join('/');
    card.appendChild(pathEl);
  }

  if (tile.description) {
    const desc = document.createElement('div');
    desc.className = 'description';
    desc.textContent = tile.description;
    card.appendChild(desc);
  }

  if (tile.semantic_type) {
    const sem = document.createElement('div');
    sem.className = 'semantic';
    sem.textContent = tile.semantic_type;
    card.appendChild(sem);
  }

  if (tile.tags && tile.tags.length > 0) {
    const tagsDiv = document.createElement('div');
    tagsDiv.className = 'tags';
    tile.tags.forEach(function(t) {
      const span = document.createElement('span');
      span.className = 'tag';
      span.textContent = t;
      tagsDiv.appendChild(span);
    });
    card.appendChild(tagsDiv);
  }

  return card;
}

function render(data) {
  const pct = data.total > 0 ? (data.processed / data.total * 100) : 0;
  bar.style.width = pct.toFixed(1) + '%';
  barText.textContent = data.processed + ' / ' + data.total;
  statusEl.textContent = data.processed + ' analyzed, ' + data.skipped +
    ' skipped (already in DB), ' + data.total + ' new tiles';

  // Build cards: prev[2], prev[1], prev[0], current, next
  const prev = data.previous || [];
  grid.replaceChildren(
    buildCard(prev[2] || null, 'Previous 3', 'previous'),
    buildCard(prev[1] || null, 'Previous 2', 'previous'),
    buildCard(prev[0] || null, 'Previous 1', 'previous'),
    buildCard(data.current, 'Analyzing', 'current'),
    buildCard(data.next, 'Up next', 'next')
  );
}

const es = new EventSource('/events');
es.onmessage = function(e) {
  render(JSON.parse(e.data));
};
es.addEventListener('done', function() {
  doneBanner.style.display = 'block';
  statusEl.textContent = 'Done!';
  es.close();
});
es.onerror = function() {
  statusEl.textContent = 'Connection lost, retrying...';
};
</script>
</body>
</html>
"""
