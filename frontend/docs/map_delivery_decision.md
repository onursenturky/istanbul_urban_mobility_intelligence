# Map Delivery Decision (Phase 14)

## Question

The frozen analytical grid has 22,322 cells. Before Phase 14 the frontend shipped this as two
monolithic files fetched on every map page: `grid_map.geojson` (22.6MB -- geometry plus every
analytical/categorical field used across all 7 exploration pages) and `grid_attributes.json`
(27MB -- all 36 columns for all 22,322 cells, fetched in full the first time any cell was
clicked, anywhere in the app). Total: ~49.7MB before a user had done anything beyond opening a
page and clicking one cell. Phase 14 Section 8 asks: should this move to PMTiles/vector tiles,
or can an optimized GeoJSON + lazy-loading strategy solve it without new infrastructure?

## Decision

**Optimized GeoJSON, split into base geometry + per-layer lookups + per-district detail
chunks. Not PMTiles.**

## Why not PMTiles

PMTiles is a legitimate, well-regarded format for this class of problem, and was seriously
considered. It was rejected for this project for three concrete reasons, not because it is
unsophisticated:

1. **The dataset does not actually need tiling.** PMTiles earns its complexity when a dataset
   is too large to reasonably hold client-side at all (city-scale road networks, national
   parcel data, basemap-scale features) and needs spatial + zoom-level tiling to stay
   responsive. 22,322 polygons with a handful of categorical properties is not that dataset --
   the raw geometry alone is 5.2MB once stripped of duplicated properties (see below), which is
   a perfectly normal single fetch for a modern web app.
2. **It would require a new build step and a new runtime dependency** (a PMTiles writer in the
   data-prep pipeline, a PMTiles-aware MapLibre protocol handler at runtime) to solve a problem
   that a plain static-JSON split already solves. Phase 14 Section 7 explicitly says not to
   reach for heavier infrastructure than 22,322 cells actually requires.
3. **It would complicate, not simplify, the analytical-integrity guarantee.** Every value in
   this product must trace back to the frozen Phase 12 parquet files without transformation
   ambiguity. A flat `{grid_id: value}` JSON lookup is trivially auditable by a non-engineer
   (open the file, read the number). A binary tiled format is not.

PMTiles remains the right call if this product ever needs to add a second, much larger spatial
layer (e.g. building footprints, full street network) -- documented here for that future
decision, not adopted now.

## What was adopted instead

Three tiers, all plain static JSON, all served from `frontend/public/data/` exactly as before
(no server, no database, no external API -- Phase 14 Section 7's explicit constraint):

| Tier | Path | Contents | Size | Fetched when |
|---|---|---|---|---|
| Base geometry | `public/data/base/grid_geometry.json` | `grid_id`, `district`, geometry only | 5.2MB | Once per session, by every exploration page, on map mount |
| Layer lookups | `public/data/layers/<field>.json` (12 files) | Flat `{grid_id: value}` for one categorical field | 0.3-0.9MB each (7.15MB combined) | Only the field(s) a given page actually colors by -- 1-3 fetches, not 12 |
| District details | `public/data/details/<district>.json` (39 files) | Full 36-column record per cell, minus `district` (the chunk key) | ~0.72MB avg | Only the ONE district containing a clicked cell, on click, via `useGridAttributes` |
| Grid-district index | `public/data/details/_grid_district_index.json` | `grid_id -> district` | 0.5MB | Once, alongside the first detail-chunk fetch, so a shared `?grid=` URL resolves its district even without a matching `?district=` |

Client-side, `lib/mapDataCache.ts` fetches and merges: the base geometry's features get the
active layer's values merged into their properties (`feature.properties[field] = lookup[grid_id]`)
before being handed to MapLibre via `addSource`/`source.setData`. Every fetch is cached
in-memory per field/district for the session, so switching between a page's own layer options,
or revisiting a district already opened, never re-fetches.

No analytical value is recomputed, rounded, or dropped in this split -- it is a pure
re-partitioning of the same frozen numbers into smaller, independently-cacheable files. Verified
by `qa/data_qa.py` checks A, B, F, G, H, K, and the new check L (every tier's grid_id set is
byte-identical to the frozen source table).

## Result

- Old: every page fetched 22.6MB of geometry+properties, then 27MB more on the first cell
  click -- 49.7MB total, unconditionally.
- New: a typical single-layer page (Typology, 15-Minute, Cycling Gain, Transit, E-bike) fetches
  ~5.2MB (base) + ~0.3-0.8MB (its one layer) ≈ **5.5-6.0MB** before it can render and color the
  map -- under the <10MB target in Phase 14 Section 9. A cell click adds ~0.7MB (one district),
  not 27MB. See `qa/phase14_performance_report.json` for the full before/after/delta measurement.
