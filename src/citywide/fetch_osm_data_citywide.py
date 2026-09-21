"""Citywide OSM raw-data fetch for POIs, land-use/green polygons, and the
road network (Section 4). Buildings were already fetched and cached
separately (see compute_building_features_citywide.py's raw GPKG) and are
not repeated here.

Reuses the exact same OSM tag filters and query-buffer/simplify config as
the pilot fetch (src/data/fetch_osm_data.py) -- identical feature
semantics, only the query extent (citywide study area, via the _activate
config overlay) and cache filenames differ.

POIs and land-use are saved as plain GeoJSON, same as the pilot -- unlike
buildings (745K polygons -> 12GB), these are far fewer records with much
lighter geometry (points / modest polygons), so GeoJSON stays a
reasonably sized, simple, schema-free format. It also preserves every raw
OSM tag column (some POI records carry 700+ distinct tag keys, including
ones that collide once sanitized for GPKG's stricter column-name rules,
e.g. "currency:TRY" and "currency:try" both fold to "currency_try") without
lossy renaming -- consistent with "never modify raw data." GPKG is reserved
for cases that actually bloat like buildings did; if a citywide layer here
ever turns out similarly oversized, convert with ogr2ogr after fetching
(which resolves such column collisions on its own), the same fix already
applied to buildings, rather than writing GPKG directly from Python.

Every fetch is idempotent: an existing cache file is loaded, never
re-fetched.

Run from the project root:
    .venv/bin/python -m src.citywide.fetch_osm_data_citywide
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import requests

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.data import fetch_osm_data as pilot_fetch
from src.features import osm_tag_config as tags
from src.utils import config as cfg

RAW_OSM_DIR = cfg.DATA_RAW / "osm"

# osmnx's default 180s read timeout is tuned for pilot-scale (3-district)
# queries; a citywide (39-district) polygon query legitimately takes the
# shared public Overpass server longer to compute and return, independent
# of the connection-refusal flakiness below.
ox.settings.timeout = 900

# The public Overpass instance (overpass-api.de) has been observed to
# intermittently refuse connections specifically on /api/interpreter
# (query execution) while /api/status (which reports free slots, not
# rate-limited) stays reachable throughout -- confirmed by a minimal
# single-node test polygon failing identically to the full citywide query,
# ruling out our query size/complexity as the cause. This is backend-side
# flakiness on a shared public service, not a local network, code, or data
# problem. Retrying in-process with a patient backoff bridges it without
# restarting the whole script and re-doing already-cached work.
_RETRY_DELAYS_S = [30, 60, 120, 240, 300, 300, 300]


def _with_retry(fetch_fn, label: str):
    for attempt, delay in enumerate([0] + _RETRY_DELAYS_S, start=1):
        if delay:
            print(f"[retry] {label}: attempt {attempt} after transient failure, waiting {delay}s...")
            time.sleep(delay)
        try:
            return fetch_fn()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            print(f"[retry] {label}: attempt {attempt} failed: {type(exc).__name__}: {exc}")
            last_exc = exc
    raise last_exc


def _fetch_or_load_geojson(out_path: Path, fetch_fn, meta: dict) -> tuple[gpd.GeoDataFrame, dict]:
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
    fetch_elapsed = time.time() - t0
    print(f"[fetch] got {len(gdf)} features in {fetch_elapsed:.1f}s")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    gdf.to_file(out_path, driver="GeoJSON")
    save_elapsed = time.time() - t0
    print(f"[cache] wrote {out_path} in {save_elapsed:.1f}s")

    diag = {**meta, "n_features": len(gdf), "fetch_seconds": round(fetch_elapsed, 1), "save_seconds": round(save_elapsed, 1), "cache_hit": False}
    meta_path.write_text(json.dumps(diag, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return gdf, diag


def fetch_road_network_citywide(poly_ll):
    road_path = RAW_OSM_DIR / "osm_road_network_raw_citywide.graphml"
    meta_path = road_path.with_suffix(".meta.json")
    if road_path.exists():
        print(f"[cache] loading road network from {road_path} (not re-fetched)")
        return ox.load_graphml(road_path), {"cache_hit": True}

    print("[fetch] querying OSM for citywide road network (network_type='all')...")
    t0 = time.time()
    G = _with_retry(
        lambda: ox.graph_from_polygon(poly_ll, network_type="all", retain_all=True, simplify=True),
        "road_network",
    )
    elapsed = time.time() - t0
    RAW_OSM_DIR.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G, road_path)
    diag = {
        "layer": "road_network", "source": cfg.OSM_SOURCE, "license": cfg.OSM_LICENSE,
        "query_filter": {"network_type": "all", "retain_all": True, "simplify": True},
        "n_nodes": len(G.nodes), "n_edges": len(G.edges), "fetch_seconds": round(elapsed, 1),
        "cache_hit": False,
    }
    meta_path.write_text(json.dumps(diag, indent=2), encoding="utf-8")
    print(f"[cache] wrote graph ({len(G.nodes)} nodes, {len(G.edges)} edges) in {elapsed:.1f}s -> {road_path}")
    return G, diag


def main() -> None:
    print("Resolving citywide query polygon (from the frozen citywide study area)...")
    _, poly_ll = pilot_fetch.get_query_polygon()

    poi_path = RAW_OSM_DIR / "osm_pois_raw_citywide.geojson"
    pois, poi_diag = _fetch_or_load_geojson(
        poi_path,
        lambda: _with_retry(lambda: ox.features_from_polygon(poly_ll, tags=tags.POI_FETCH_TAGS).reset_index(), "pois"),
        meta={"layer": "pois", "query_filter": tags.POI_FETCH_TAGS, "source": cfg.OSM_SOURCE, "license": cfg.OSM_LICENSE},
    )
    print(f"POIs: {len(pois)} features -- {poi_diag}")

    landuse_path = RAW_OSM_DIR / "osm_landuse_green_raw_citywide.geojson"
    landuse, landuse_diag = _fetch_or_load_geojson(
        landuse_path,
        lambda: _with_retry(lambda: ox.features_from_polygon(poly_ll, tags=tags.LANDUSE_FETCH_TAGS).reset_index(), "landuse_green"),
        meta={"layer": "landuse_green", "query_filter": tags.LANDUSE_FETCH_TAGS, "source": cfg.OSM_SOURCE, "license": cfg.OSM_LICENSE},
    )
    print(f"Land-use/green: {len(landuse)} features -- {landuse_diag}")

    _, road_diag = fetch_road_network_citywide(poly_ll)
    print(f"Road network -- {road_diag}")

    print("\nAll citywide OSM layers cached under", RAW_OSM_DIR)


if __name__ == "__main__":
    main()
