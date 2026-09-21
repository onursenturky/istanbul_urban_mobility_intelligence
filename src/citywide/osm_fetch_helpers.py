"""Shared helpers for citywide OSM raw-data fetches.

Lesson learned fetching citywide buildings: GeoJSON (a verbose text format)
produced a 12GB file for 745K polygons and took ~2 minutes just to
serialize — GeoPackage (a SQLite-backed binary format) is dramatically more
compact and faster for this volume. All citywide OSM raw caches use .gpkg
from this point on. This is a storage-FORMAT change only — it does not
alter the query, the fetched features, or any downstream feature
definition; the exact same frozen study-area geometry is still used for
all actual feature allocation, which happens later against the grid, not
against this raw cache's format.

Every function here is idempotent: if the target .gpkg already exists, it
is reused and NOT re-fetched, per the explicit instruction to cache every
expensive citywide raw fetch.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import geopandas as gpd
import osmnx as ox

ox.settings.timeout = 600
ox.settings.log_console = False


def fetch_or_load(
    out_path: Path,
    fetch_fn,
    meta: dict | None = None,
) -> tuple[gpd.GeoDataFrame, dict]:
    """`fetch_fn()` must return a GeoDataFrame. If `out_path` (.gpkg) already
    exists, it is loaded and returned with diagnostics marked as cached;
    otherwise fetch_fn is called, timed, and the result is saved to .gpkg."""
    meta_path = out_path.with_suffix(".meta.json")
    if out_path.exists():
        print(f"[cache] loading {out_path} (not re-fetched)")
        gdf = gpd.read_file(out_path)
        diag = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        diag["cache_hit"] = True
        return gdf, diag

    print(f"[fetch] {out_path.name} does not exist yet — fetching...")
    t0 = time.time()
    gdf = fetch_fn()
    elapsed = time.time() - t0
    print(f"[fetch] got {len(gdf)} features in {elapsed:.1f}s")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    # Object-dtype list columns (e.g. multi-valued OSM tags) break GPKG's
    # typed-column model; stringify them before writing.
    gdf_to_save = gdf.reset_index() if gdf.index.name else gdf.copy()
    for col in gdf_to_save.columns:
        if col == gdf_to_save.geometry.name:
            continue
        if gdf_to_save[col].apply(lambda v: isinstance(v, (list, dict))).any():
            gdf_to_save[col] = gdf_to_save[col].astype(str)
    # GPKG/OGR field names can't contain ':' (common in raw OSM tag keys
    # like "currency:try", "payment:visa"). This is a storage-compatibility
    # rename only, applied to raw passthrough tag columns never referenced
    # by feature-extraction logic (which keys off amenity/shop/office/
    # tourism/leisure/healthcare/building -- none contain ':'). Collisions
    # created by the rename (e.g. "a:b" and "a_b" both present) are
    # disambiguated with a numeric suffix.
    rename_map: dict[str, str] = {}
    seen = set(gdf_to_save.columns)
    for col in gdf_to_save.columns:
        if col == gdf_to_save.geometry.name or ":" not in col:
            continue
        new_col = col.replace(":", "_")
        while new_col in seen:
            new_col += "_"
        rename_map[col] = new_col
        seen.add(new_col)
    if rename_map:
        gdf_to_save = gdf_to_save.rename(columns=rename_map)
    gdf_to_save.to_file(out_path, driver="GPKG")
    save_elapsed = time.time() - t0
    print(f"[cache] wrote {out_path} in {save_elapsed:.1f}s")

    diag = {**(meta or {}), "n_features": len(gdf), "fetch_seconds": round(elapsed, 1), "save_seconds": round(save_elapsed, 1), "cache_hit": False}
    meta_path.write_text(json.dumps(diag, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return gdf, diag
