"""One-off, sequential evaluation of alternative public Overpass API
endpoints, run because the default overpass-api.de backend has shown
repeated instability across both the land-use and road-network chunked
acquisition stages (see fetch_osm_data_citywide_chunked.py).

Tests candidates ONE AT A TIME (never concurrently) with a small pause
between endpoints and between sub-tests, using only small, cheap queries
against the smallest district (Adalar) -- this is a deliberate conservative
choice so evaluating alternatives does not itself become a burden on any
of these shared public services.

For each candidate, records:
  1. status endpoint reachability
  2. a trivial single-node query (interpreter reachability)
  3. a real district-level land-use query (Adalar, LANDUSE_FETCH_TAGS)
  4. a real district-level road-network query (Adalar, network_type="all")
and whether each returned structurally valid data (non-empty, valid
geometries / a connected-enough graph), plus response time for each.

This script only REPORTS results. It does not select an endpoint for the
acquisition scripts automatically -- that is a manual decision made from
its printed comparison, then set via the CITYWIDE_OVERPASS_URL environment
variable read by fetch_osm_data_citywide_chunked.py.

Run from the project root:
    .venv/bin/python -u -m src.citywide.test_overpass_endpoints
"""

from __future__ import annotations

import time

import osmnx as ox
import requests

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.features import osm_tag_config as tags
from src.utils import config as cfg

import geopandas as gpd

ox.settings.timeout = 60  # these are meant to be small, fast test queries

CANDIDATES = [
    "https://overpass.kumi.systems/api",
    "https://overpass.openstreetmap.fr/api",
    "https://overpass.openstreetmap.ru/api",
]

PAUSE_BETWEEN_SUBTESTS_S = 3
PAUSE_BETWEEN_ENDPOINTS_S = 10


def _get_adalar_polygon():
    districts = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    adalar = districts.loc[districts["district"] == "Adalar", "geometry"].iloc[0]
    buffered = adalar.buffer(cfg.OSM_QUERY_BUFFER_M).simplify(cfg.OSM_QUERY_SIMPLIFY_TOLERANCE_M, preserve_topology=True)
    return gpd.GeoSeries([buffered], crs=cfg.METRIC_CRS).to_crs(cfg.STORAGE_CRS).iloc[0]


def _test_status(endpoint: str) -> dict:
    try:
        t0 = time.time()
        r = requests.get(f"{endpoint}/status", timeout=15)
        elapsed = time.time() - t0
        return {"reachable": True, "http_status": r.status_code, "seconds": round(elapsed, 2), "body_snippet": r.text[:150].replace("\n", " | ")}
    except requests.exceptions.ConnectionError as exc:
        return {"reachable": False, "error": f"ConnectionError: {exc}"}
    except requests.exceptions.Timeout as exc:
        return {"reachable": False, "error": f"Timeout: {exc}"}


def _test_tiny_query(endpoint: str) -> dict:
    try:
        t0 = time.time()
        r = requests.post(f"{endpoint}/interpreter", data={"data": "[out:json];node(1);out;"}, timeout=20)
        elapsed = time.time() - t0
        ok = r.status_code == 200
        return {"success": ok, "http_status": r.status_code, "seconds": round(elapsed, 2)}
    except requests.exceptions.ConnectionError as exc:
        return {"success": False, "error": f"ConnectionError: {exc}"}
    except requests.exceptions.Timeout as exc:
        return {"success": False, "error": f"Timeout: {exc}"}


def _test_landuse_query(endpoint: str, poly_ll) -> dict:
    ox.settings.overpass_url = endpoint
    try:
        t0 = time.time()
        gdf = ox.features_from_polygon(poly_ll, tags=tags.LANDUSE_FETCH_TAGS)
        elapsed = time.time() - t0
        valid_geom = gdf.geometry.is_valid.all() if len(gdf) else None
        return {"success": True, "seconds": round(elapsed, 2), "n_features": len(gdf), "geometries_valid": bool(valid_geom) if valid_geom is not None else "n/a (0 features)"}
    except Exception as exc:  # noqa: BLE001 -- report whatever happens, this is a diagnostic script
        if "InsufficientResponseError" in type(exc).__name__ or "no matching features" in str(exc).lower():
            return {"success": True, "seconds": None, "n_features": 0, "geometries_valid": "n/a (0 features)"}
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def _test_road_query(endpoint: str, poly_ll) -> dict:
    ox.settings.overpass_url = endpoint
    try:
        t0 = time.time()
        G = ox.graph_from_polygon(poly_ll, network_type="all", retain_all=True, simplify=True)
        elapsed = time.time() - t0
        return {"success": True, "seconds": round(elapsed, 2), "n_nodes": len(G.nodes), "n_edges": len(G.edges)}
    except Exception as exc:  # noqa: BLE001
        if "InsufficientResponseError" in type(exc).__name__ or "no matching features" in str(exc).lower():
            return {"success": True, "seconds": None, "n_nodes": 0, "n_edges": 0}
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    poly_ll = _get_adalar_polygon()
    results = {}

    for i, endpoint in enumerate(CANDIDATES):
        print(f"\n{'=' * 72}\nTesting endpoint {i + 1}/{len(CANDIDATES)}: {endpoint}\n{'=' * 72}", flush=True)

        print("[1/4] status check...", flush=True)
        status_result = _test_status(endpoint)
        print(f"      {status_result}", flush=True)
        time.sleep(PAUSE_BETWEEN_SUBTESTS_S)

        print("[2/4] tiny single-node query...", flush=True)
        tiny_result = _test_tiny_query(endpoint)
        print(f"      {tiny_result}", flush=True)
        time.sleep(PAUSE_BETWEEN_SUBTESTS_S)

        print("[3/4] district-level land-use query (Adalar)...", flush=True)
        landuse_result = _test_landuse_query(endpoint, poly_ll)
        print(f"      {landuse_result}", flush=True)
        time.sleep(PAUSE_BETWEEN_SUBTESTS_S)

        print("[4/4] district-level road-network query (Adalar)...", flush=True)
        road_result = _test_road_query(endpoint, poly_ll)
        print(f"      {road_result}", flush=True)

        results[endpoint] = {
            "status": status_result, "tiny_query": tiny_result,
            "landuse_query": landuse_result, "road_query": road_result,
        }

        if i < len(CANDIDATES) - 1:
            print(f"\n[pause] waiting {PAUSE_BETWEEN_ENDPOINTS_S}s before testing the next endpoint...", flush=True)
            time.sleep(PAUSE_BETWEEN_ENDPOINTS_S)

    print(f"\n{'=' * 72}\nSUMMARY\n{'=' * 72}", flush=True)
    for endpoint, r in results.items():
        landuse_ok = r["landuse_query"].get("success", False)
        road_ok = r["road_query"].get("success", False)
        passes_both = landuse_ok and road_ok
        print(f"\n{endpoint}", flush=True)
        print(f"  status reachable:   {r['status'].get('reachable', 'ERROR: ' + str(r['status'].get('error')))}", flush=True)
        print(f"  tiny query success: {r['tiny_query'].get('success', False)} "
              f"({r['tiny_query'].get('seconds', '?')}s)" if 'seconds' in r['tiny_query'] else f"  tiny query: {r['tiny_query']}", flush=True)
        print(f"  landuse query:      {r['landuse_query']}", flush=True)
        print(f"  road query:         {r['road_query']}", flush=True)
        print(f"  PASSES BOTH REPRESENTATIVE TESTS: {passes_both}", flush=True)


if __name__ == "__main__":
    main()
