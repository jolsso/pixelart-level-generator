# Feature Backlog

Unscheduled features ordered roughly by priority.

---

## [BACKLOG] Store analysis provenance per tile

**Motivation:** A future vision model may produce significantly better descriptions than the one used today. Without provenance, there is no way to identify which tiles were analyzed by which model, or when — making targeted re-analysis impossible.

**Proposed changes:**

Add two columns to the `tiles` SQLite table:

| Column | Type | Example |
|---|---|---|
| `analyzed_at` | TEXT (ISO 8601) | `2026-03-29T14:22:01+00:00` |
| `analyzed_by` | TEXT | `qwen2.5vl:7b` |

These are populated by `build_catalog()` / `main()` at analysis time. Exterior tiles resolved via filename parsing use `analyzed_by = "filename"` and a real timestamp.

**Re-analysis workflow (future):**

```bash
# Re-analyze only tiles indexed by an older model
pixelart-analyze --reanalyze-model qwen2.5vl:7b --data-dir ./data
```

This would select tile IDs where `analyzed_by = 'qwen2.5vl:7b'`, clear those rows, and re-run analysis with the current model.

---

## [BACKLOG] Only index the largest available resolution per logical tile

**Motivation:** The same logical tile exists at three resolutions (16×16, 32×32, 48×48). Indexing all three triples the catalog size (~34 k tiles) without adding new content. The largest resolution (48×48 for interiors, 48×48 for exteriors) contains the most visual detail and will yield better Ollama descriptions.

**Proposed changes:**

- In `_collect_pngs()`, scan all resolutions but deduplicate by logical tile identity (relative path with resolution segment normalised out), keeping only the highest `grid_unit` entry.
- Store `grid_unit` as before so the renderer still knows the tile's pixel size.
- Reduce total catalog size from ~34 k to ~11 k tiles.
- Reduce Ollama analysis time by ~3× for interior tiles.

**Open question:** Should the catalog record the available resolutions so the renderer can up/down-scale, or should separate smaller-resolution DB files be generated on demand?
