"""Per-district chunked citywide OSM fetch for land-use/green polygons and
the road network, with a bounded, non-blocking fault-tolerance policy that
distinguishes a GLOBAL Overpass backend outage from a district-specific
query problem.

A single monolithic 39-district Overpass query proved unreliable (repeated
connection-refused / read-timeout failures on the shared public backend),
so each district is fetched as its own small, cheap, independently cached
query (resumable: a district with an existing chunk file is skipped).

Fault-tolerance policy, in order:

  1. Pass 1: try every district once (small bounded per-district retry
     budget: _RETRY_DELAYS_S). A district that still fails after that
     budget triggers an outage check (see below) rather than being
     assumed to be its own problem.
  2. Outage check: whenever _GLOBAL_OUTAGE_STREAK district-level failures
     happen in a row, an INDEPENDENT lightweight health check is run
     against the Overpass endpoint (see _check_overpass_health) before
     drawing any conclusion:
       - endpoint unavailable (connection refused) or overloaded/
         unresponsive -> this is treated as a GLOBAL outage. Acquisition
         PAUSES: the district(s) that failed during the streak are NOT
         marked deferred_failed (an outage is not their fault), the run
         cools down and re-checks health periodically, and once healthy
         again it resumes from that same first incomplete district --
         it does not restart from district 1, and it does not burn
         through the remaining districts marking each one failed.
       - endpoint healthy -> the repeated failures are treated as
         genuinely district-specific, that one district is deferred, and
         the pass continues normally to the next district.
  3. Pass 2: after pass 1 finishes, retry ONLY the districts that were
     individually deferred (not the ones skipped during an outage pause,
     which were already retried in place once the outage cleared).
  4. Pass 3 (subdivision): a district still failing after pass 2 -- and
     ONLY if the endpoint is confirmed healthy at that point -- is
     spatially subdivided into a 2x2 grid of tiles (intersected with its
     actual buffered polygon), each tile fetched independently, and the
     results merged back into that district's single chunk file (one more
     level of 2x2 subdivision is allowed per tile if needed). If the
     endpoint is not healthy when pass 3 would start, subdivision is
     skipped for now (it would not distinguish a real district problem
     from ongoing outage noise) and those districts stay deferred.
  5. A district (or tile) still failing after subdivision stays
     "deferred_failed". A district never attempted because a sustained
     outage exhausted the cooldown budget is recorded separately as
     "not_attempted_outage" -- NOT counted as a district-specific failure.
  6. The citywide merge step REFUSES to write the final combined file
     unless a chunk exists for all 39 districts -- the layer is never
     silently marked complete with missing coverage.

The Overpass endpoint is configurable via the CITYWIDE_OVERPASS_URL
environment variable (default: the standard https://overpass-api.de/api),
so a different healthy public instance can be used later WITHOUT changing
any acquisition logic. This script does not automatically try multiple
endpoints itself -- that would hammer several public services at once,
which is exactly the kind of behavior a shared free resource should not
see from an automated client. Switching endpoints is a manual, deliberate
choice (set the env var and re-run).

Buildings and POIs were already fetched successfully as monolithic
queries earlier and are NOT re-fetched here.

Run from the project root:
    .venv/bin/python -u -m src.citywide.fetch_osm_data_citywide_chunked
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
import requests
from shapely.geometry import box

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.features import osm_tag_config as tags
from src.utils import config as cfg

OVERPASS_ENDPOINT = os.environ.get("CITYWIDE_OVERPASS_URL", "https://overpass-api.de/api")
ox.settings.overpass_url = OVERPASS_ENDPOINT
ox.settings.timeout = 300  # per-district/per-tile queries are small; no need for a large ceiling

# Districts known (from prior runs) to be repeatedly hitting the shared
# Overpass backend's flakiness are processed LAST within pass 1, so they
# never sit ahead of and block districts that are likely to succeed
# quickly. This is purely an ordering hint -- they are still attempted the
# same as any other district, just later.
PROCESS_LAST = {"Kadıköy"}

RAW_OSM_DIR = cfg.DATA_RAW / "osm"
LANDUSE_CHUNK_DIR = RAW_OSM_DIR / "landuse_green_by_district"
ROAD_CHUNK_DIR = RAW_OSM_DIR / "road_network_by_district"

LANDUSE_FINAL_PATH = RAW_OSM_DIR / "osm_landuse_green_raw_citywide.geojson"
ROAD_FINAL_PATH = RAW_OSM_DIR / "osm_road_network_raw_citywide.graphml"

# Bounded per-attempt retry budget used within a single district fetch.
_RETRY_DELAYS_S = [15, 30, 60]

# How many consecutive district-level failures trigger an independent
# outage health check, instead of assuming each one is its own problem.
_GLOBAL_OUTAGE_STREAK = 2
# How long to wait between health re-checks once a global outage is
# suspected, and how many re-check cycles to allow before giving up on
# this run (giving up leaves the untried districts as "not_attempted_outage",
# never as district-specific failures).
_COOLDOWN_S = 180
_MAX_COOLDOWN_CYCLES = 20


class _DistrictFetchError(Exception):
    pass


def _with_retry(fetch_fn, label: str):
    last_exc = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS_S, start=1):
        if delay:
            print(f"    [retry] {label}: attempt {attempt} after failure, waiting {delay}s...", flush=True)
            time.sleep(delay)
        try:
            return fetch_fn()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            print(f"    [retry] {label}: attempt {attempt} failed: {type(exc).__name__}: {exc}", flush=True)
            last_exc = exc
    raise _DistrictFetchError(f"{label}: exhausted {len(_RETRY_DELAYS_S) + 1} attempts; last error: {last_exc}") from last_exc


# --------------------------------------------------------------------------
# Independent endpoint health check -- deliberately does NOT reuse the same
# code path as the district fetches, so it can positively distinguish
# "the query endpoint itself refuses/times out" from "this district's query
# specifically fails" rather than just re-running the same thing.
# --------------------------------------------------------------------------

def _check_overpass_health() -> dict:
    status_reachable = None
    try:
        r = requests.get(f"{OVERPASS_ENDPOINT}/status", timeout=10)
        status_reachable = True
        status_text_snippet = r.text[:200].replace("\n", " | ")
    except requests.exceptions.ConnectionError:
        return {"status": "unavailable", "detail": "status endpoint: connection refused"}
    except requests.exceptions.Timeout:
        return {"status": "unresponsive", "detail": "status endpoint: timed out"}

    try:
        r2 = requests.post(f"{OVERPASS_ENDPOINT}/interpreter", data={"data": "[out:json];node(1);out;"}, timeout=20)
    except requests.exceptions.ConnectionError:
        return {
            "status": "unavailable",
            "detail": f"interpreter endpoint: connection refused (status endpoint WAS reachable: {status_text_snippet})",
        }
    except requests.exceptions.Timeout:
        return {"status": "unresponsive", "detail": "interpreter endpoint: timed out (status endpoint was reachable)"}

    if r2.status_code in (429, 504):
        return {"status": "overloaded", "detail": f"interpreter returned HTTP {r2.status_code}"}
    return {"status": "healthy", "detail": f"interpreter endpoint reachable (HTTP {r2.status_code})"}


def _cooldown_until_healthy() -> bool:
    for cycle in range(1, _MAX_COOLDOWN_CYCLES + 1):
        print(f"  [cooldown] waiting {_COOLDOWN_S}s before re-checking endpoint health "
              f"(cycle {cycle}/{_MAX_COOLDOWN_CYCLES})...", flush=True)
        time.sleep(_COOLDOWN_S)
        health = _check_overpass_health()
        print(f"  [cooldown] health check: {health}", flush=True)
        if health["status"] == "healthy":
            print("  [cooldown] endpoint healthy again -- resuming acquisition", flush=True)
            return True
    print(f"  [cooldown] endpoint still not healthy after {_MAX_COOLDOWN_CYCLES} cooldown cycles "
          f"(~{_MAX_COOLDOWN_CYCLES * _COOLDOWN_S / 60:.0f} min) -- giving up for this run", flush=True)
    return False


# --------------------------------------------------------------------------

def _buffered_polygon_metric(geom_metric):
    return geom_metric.buffer(cfg.OSM_QUERY_BUFFER_M).simplify(
        cfg.OSM_QUERY_SIMPLIFY_TOLERANCE_M, preserve_topology=True
    )


def _to_wgs84(poly_metric):
    return gpd.GeoSeries([poly_metric], crs=cfg.METRIC_CRS).to_crs(cfg.STORAGE_CRS).iloc[0]


def _subdivide_polygon_metric(poly_metric, n: int = 2) -> list:
    """Split poly's bounding box into an n x n grid and intersect each cell
    with the actual polygon, so the tiles' union exactly equals the input
    polygon (no gaps, no added area) and only non-empty tiles are kept."""
    minx, miny, maxx, maxy = poly_metric.bounds
    dx, dy = (maxx - minx) / n, (maxy - miny) / n
    tiles = []
    for i in range(n):
        for j in range(n):
            cell = box(minx + i * dx, miny + j * dy, minx + (i + 1) * dx, miny + (j + 1) * dy)
            clipped = poly_metric.intersection(cell)
            if not clipped.is_empty and clipped.area > 0:
                tiles.append(clipped)
    return tiles


def _empty_gdf():
    return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=cfg.STORAGE_CRS)


def _dedup(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    id_cols = [c for c in ["element_type", "osmid", "id"] if c in gdf.columns]
    return gdf.drop_duplicates(subset=id_cols, keep="first").reset_index(drop=True) if id_cols and len(gdf) else gdf


# --------------------------------------------------------------------------
# Generic outage-aware pass runner, shared by both layers.
# --------------------------------------------------------------------------

def _run_pass(names: list[str], status: dict, layer_label: str, chunk_exists, fetch_one, on_success) -> list[str]:
    """Runs one pass over `names`.

    chunk_exists(name) -> bool
    fetch_one(name) -> result (raises _DistrictFetchError on failure)
    on_success(name, result, elapsed) -> persists the chunk, returns a
        status dict to record for that district.

    Returns the list of districts individually deferred as district-
    specific failures. Districts left unattempted because a sustained
    outage exhausted the cooldown budget are recorded in `status` as
    "not_attempted_outage" and are NOT included in the returned list
    (they are not district-specific failures).
    """
    pending = list(names)
    deferred: list[str] = []
    consecutive_failures = 0
    idx = 0
    while idx < len(pending):
        name = pending[idx]
        if chunk_exists(name):
            status[name] = {"status": "success", "cache_hit": True}
            idx += 1
            continue

        print(f"[fetch] {layer_label}/{name}: querying...", flush=True)
        t0 = time.time()
        try:
            result = fetch_one(name)
        except _DistrictFetchError as exc:
            consecutive_failures += 1
            print(f"[fail] {layer_label}/{name}: {exc}", flush=True)

            if consecutive_failures >= _GLOBAL_OUTAGE_STREAK:
                health = _check_overpass_health()
                print(f"[health-check] {health}", flush=True)
                if health["status"] != "healthy":
                    print(f"[pause] endpoint condition {health['status']!r} -- treating this as a GLOBAL "
                          f"outage, not a {name}-specific problem. Pausing acquisition; recent failures "
                          f"will NOT be counted as district-specific.", flush=True)
                    resumed = _cooldown_until_healthy()
                    consecutive_failures = 0
                    if resumed:
                        continue  # retry the SAME district (idx unchanged), fresh streak
                    remaining = pending[idx:]
                    print(f"[pause] giving up for this run; {len(remaining)} district(s) not yet "
                          f"attempted due to a sustained outage: {remaining}", flush=True)
                    for n in remaining:
                        status[n] = {"status": "not_attempted_outage"}
                    return deferred
                # Endpoint confirmed healthy -- the streak was coincidental,
                # not a global issue. Reset it here (only here) so the count
                # only ever accumulates ACROSS consecutive failing districts
                # up to the point a health check actually resolves it.
                print(f"[info] endpoint is currently healthy -- treating this as a {name}-specific issue.", flush=True)
                consecutive_failures = 0

            status[name] = {"status": "deferred_failed", "reason": str(exc)}
            deferred.append(name)
            idx += 1
            continue

        elapsed = time.time() - t0
        status[name] = on_success(name, result, elapsed)
        consecutive_failures = 0
        idx += 1
    return deferred


# --------------------------------------------------------------------------
# Land-use / green polygons
# --------------------------------------------------------------------------

def _fetch_landuse_polygon(poly_ll, label: str) -> gpd.GeoDataFrame:
    try:
        return _with_retry(
            lambda: ox.features_from_polygon(poly_ll, tags=tags.LANDUSE_FETCH_TAGS).reset_index(), label
        )
    except _DistrictFetchError:
        raise
    except Exception as exc:  # noqa: BLE001 -- zero matching features is a normal, not a failure, outcome
        if "InsufficientResponseError" in type(exc).__name__ or "no matching features" in str(exc).lower():
            return _empty_gdf()
        raise


def _fetch_landuse_district_subdivided(name: str, poly_metric, depth: int = 0) -> gpd.GeoDataFrame:
    """Only called from the pass-3 subdivision step (endpoint already
    confirmed healthy at that point), never inline within a plain attempt."""
    print(f"    [subdivide] landuse/{name}: splitting into a 2x2 tile grid", flush=True)
    tiles = _subdivide_polygon_metric(poly_metric, n=2)
    parts = []
    for k, tile in enumerate(tiles):
        label = f"{name}_tile{k}"
        try:
            parts.append(_fetch_landuse_polygon(_to_wgs84(tile), f"landuse/{label}"))
        except _DistrictFetchError:
            if depth >= 1:
                raise
            parts.append(_fetch_landuse_district_subdivided(label, tile, depth=depth + 1))
    return _dedup(gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=cfg.STORAGE_CRS)) if parts else _empty_gdf()


def fetch_landuse_chunked(districts: gpd.GeoDataFrame) -> dict:
    LANDUSE_CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    districts_by_name = dict(zip(districts["district"], districts.geometry))
    names = sorted(districts["district"], key=lambda n: n in PROCESS_LAST)
    status: dict = {}

    def chunk_exists(name):
        return (LANDUSE_CHUNK_DIR / f"{name}.geojson").exists()

    def make_on_success(chunk_dir):
        def on_success(name, gdf, elapsed):
            gdf = gdf.copy()
            gdf["_source_district"] = name
            gdf.to_file(chunk_dir / f"{name}.geojson", driver="GeoJSON")
            print(f"[cache] landuse/{name}: {len(gdf)} features in {elapsed:.1f}s -> {chunk_dir / f'{name}.geojson'}", flush=True)
            return {"status": "success", "cache_hit": False, "n_features": len(gdf), "fetch_seconds": round(elapsed, 1)}
        return on_success

    on_success = make_on_success(LANDUSE_CHUNK_DIR)

    print("-- pass 1: every district once (bounded retries; outage-aware) --", flush=True)
    deferred = _run_pass(
        names, status, "landuse", chunk_exists,
        lambda name: _fetch_landuse_polygon(_to_wgs84(_buffered_polygon_metric(districts_by_name[name])), f"landuse/{name}"),
        on_success,
    )

    if deferred:
        print(f"\n-- pass 2: retrying {len(deferred)} deferred district(s) plainly: {deferred} --", flush=True)
        deferred = _run_pass(
            deferred, status, "landuse", chunk_exists,
            lambda name: _fetch_landuse_polygon(_to_wgs84(_buffered_polygon_metric(districts_by_name[name])), f"landuse/{name}"),
            on_success,
        )

    if deferred:
        health = _check_overpass_health()
        if health["status"] != "healthy":
            print(f"\n-- skipping pass 3 (subdivision): endpoint not currently healthy ({health}); "
                  f"{len(deferred)} district(s) remain deferred: {deferred} --", flush=True)
        else:
            print(f"\n-- pass 3: endpoint healthy; spatially subdividing {len(deferred)} "
                  f"still-failing district(s): {deferred} --", flush=True)

            def fetch_one_subdivide(name):
                try:
                    return _fetch_landuse_polygon(_to_wgs84(_buffered_polygon_metric(districts_by_name[name])), f"landuse/{name}")
                except _DistrictFetchError:
                    return _fetch_landuse_district_subdivided(name, _buffered_polygon_metric(districts_by_name[name]))

            deferred = _run_pass(deferred, status, "landuse", chunk_exists, fetch_one_subdivide, on_success)

    if deferred:
        print(f"\n-- {len(deferred)} district(s) still deferred after subdivision: {deferred} --", flush=True)

    return {"n_districts": len(districts), "status": status, "still_deferred": deferred}


def merge_landuse_chunks(districts: gpd.GeoDataFrame) -> gpd.GeoDataFrame | None:
    missing = [n for n in districts["district"] if not (LANDUSE_CHUNK_DIR / f"{n}.geojson").exists()]
    if missing:
        print(f"[merge] landuse: REFUSING to write final file -- missing chunks for {len(missing)} "
              f"district(s): {missing}. Layer is NOT complete.", flush=True)
        return None

    parts = [gpd.read_file(LANDUSE_CHUNK_DIR / f"{n}.geojson") for n in districts["district"]]
    parts = [p for p in parts if len(p)]
    merged = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=cfg.STORAGE_CRS)
    n_before = len(merged)
    merged = _dedup(merged)
    print(f"[merge] landuse: {n_before} raw rows across {len(districts)} district chunks -> "
          f"{len(merged)} unique features after cross-boundary dedup ({n_before - len(merged)} duplicates removed)", flush=True)
    return merged


# --------------------------------------------------------------------------
# Road network
# --------------------------------------------------------------------------

def _fetch_road_polygon(poly_ll, label: str):
    return _with_retry(
        lambda: ox.graph_from_polygon(poly_ll, network_type="all", retain_all=True, simplify=True), label
    )


def _fetch_road_district_subdivided(name: str, poly_metric, depth: int = 0):
    print(f"    [subdivide] roads/{name}: splitting into a 2x2 tile grid", flush=True)
    tiles = _subdivide_polygon_metric(poly_metric, n=2)
    graphs = []
    for k, tile in enumerate(tiles):
        label = f"{name}_tile{k}"
        try:
            graphs.append(_fetch_road_polygon(_to_wgs84(tile), f"roads/{label}"))
        except _DistrictFetchError:
            if depth >= 1:
                continue  # an empty tile (e.g. water-only) may legitimately have no roads
            try:
                graphs.append(_fetch_road_district_subdivided(label, tile, depth=depth + 1))
            except _DistrictFetchError:
                continue
    if not graphs:
        raise _DistrictFetchError(f"roads/{name}: no tile produced a graph after subdivision")
    composed = nx.compose_all(graphs)
    composed.graph["crs"] = graphs[0].graph["crs"]
    return composed


def fetch_road_network_chunked(districts: gpd.GeoDataFrame) -> dict:
    ROAD_CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    districts_by_name = dict(zip(districts["district"], districts.geometry))
    names = sorted(districts["district"], key=lambda n: n in PROCESS_LAST)
    status: dict = {}

    def chunk_exists(name):
        return (ROAD_CHUNK_DIR / f"{name}.graphml").exists()

    def on_success(name, G, elapsed):
        chunk_path = ROAD_CHUNK_DIR / f"{name}.graphml"
        ox.save_graphml(G, chunk_path)
        print(f"[cache] roads/{name}: {len(G.nodes)} nodes, {len(G.edges)} edges in {elapsed:.1f}s -> {chunk_path}", flush=True)
        return {"status": "success", "cache_hit": False, "n_nodes": len(G.nodes), "n_edges": len(G.edges), "fetch_seconds": round(elapsed, 1)}

    print("-- pass 1: every district once (bounded retries; outage-aware) --", flush=True)
    deferred = _run_pass(
        names, status, "roads", chunk_exists,
        lambda name: _fetch_road_polygon(_to_wgs84(_buffered_polygon_metric(districts_by_name[name])), f"roads/{name}"),
        on_success,
    )

    if deferred:
        print(f"\n-- pass 2: retrying {len(deferred)} deferred district(s) plainly: {deferred} --", flush=True)
        deferred = _run_pass(
            deferred, status, "roads", chunk_exists,
            lambda name: _fetch_road_polygon(_to_wgs84(_buffered_polygon_metric(districts_by_name[name])), f"roads/{name}"),
            on_success,
        )

    if deferred:
        health = _check_overpass_health()
        if health["status"] != "healthy":
            print(f"\n-- skipping pass 3 (subdivision): endpoint not currently healthy ({health}); "
                  f"{len(deferred)} district(s) remain deferred: {deferred} --", flush=True)
        else:
            print(f"\n-- pass 3: endpoint healthy; spatially subdividing {len(deferred)} "
                  f"still-failing district(s): {deferred} --", flush=True)

            def fetch_one_subdivide(name):
                try:
                    return _fetch_road_polygon(_to_wgs84(_buffered_polygon_metric(districts_by_name[name])), f"roads/{name}")
                except _DistrictFetchError:
                    return _fetch_road_district_subdivided(name, _buffered_polygon_metric(districts_by_name[name]))

            deferred = _run_pass(deferred, status, "roads", chunk_exists, fetch_one_subdivide, on_success)

    if deferred:
        print(f"\n-- {len(deferred)} district(s) still deferred after subdivision: {deferred} --", flush=True)

    return {"n_districts": len(districts), "status": status, "still_deferred": deferred}


def merge_road_chunks(districts: gpd.GeoDataFrame):
    missing = [n for n in districts["district"] if not (ROAD_CHUNK_DIR / f"{n}.graphml").exists()]
    if missing:
        print(f"[merge] roads: REFUSING to write final file -- missing chunks for {len(missing)} "
              f"district(s): {missing}. Layer is NOT complete.", flush=True)
        return None

    graphs = [ox.load_graphml(ROAD_CHUNK_DIR / f"{n}.graphml") for n in districts["district"]]
    n_nodes_sum = sum(len(g.nodes) for g in graphs)
    n_edges_sum = sum(len(g.edges) for g in graphs)
    composed = nx.compose_all(graphs)
    composed.graph["crs"] = graphs[0].graph["crs"]
    print(f"[merge] roads: {n_nodes_sum} node-instances / {n_edges_sum} edge-instances across "
          f"{len(districts)} district chunks -> {len(composed.nodes)} unique nodes, "
          f"{len(composed.edges)} unique edges after compose", flush=True)
    return composed


# --------------------------------------------------------------------------
# Independent stages -- land-use and roads are separate feature families
# with separate manifests and separate completion states. Neither stage
# blocks on the other; each can be invoked, paused, and resumed on its own.
# --------------------------------------------------------------------------

LANDUSE_MANIFEST_PATH = RAW_OSM_DIR / "landuse_green_by_district.meta.json"
ROAD_MANIFEST_PATH = RAW_OSM_DIR / "road_network_by_district.meta.json"


def write_landuse_partial_manifest(districts: gpd.GeoDataFrame) -> dict:
    """Records the CURRENT on-disk state of the land-use chunks as an
    explicit PARTIAL manifest, without attempting any further fetches or
    touching the merge step. Existing chunk files are never
    deleted/overwritten by this -- it only reads what's already cached."""
    all_names = list(districts["district"])
    cached = [n for n in all_names if (LANDUSE_CHUNK_DIR / f"{n}.geojson").exists()]
    pending = [n for n in all_names if n not in cached]
    manifest = {
        "layer_status": "PARTIAL" if pending else "COMPLETE_CHUNKS",
        "n_districts": len(all_names),
        "n_cached": len(cached),
        "cached_districts": cached,
        "pending_districts": pending,
    }
    LANDUSE_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[manifest] landuse: {len(cached)}/{len(all_names)} cached, {len(pending)} pending "
          f"(status=PARTIAL) -> {LANDUSE_MANIFEST_PATH}", flush=True)
    print(f"[manifest] landuse: pending districts kept for a later recovery pass: {pending}", flush=True)
    return manifest


def run_landuse_stage(districts: gpd.GeoDataFrame, attempt_fetch: bool = True) -> None:
    print("\n=== Land-use / green polygons (independent stage) ===", flush=True)
    if LANDUSE_FINAL_PATH.exists():
        print(f"[cache] {LANDUSE_FINAL_PATH} already exists (layer already complete, not re-fetched)", flush=True)
        return

    if attempt_fetch:
        landuse_summary = fetch_landuse_chunked(districts)
        LANDUSE_MANIFEST_PATH.write_text(json.dumps(landuse_summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # Whether or not a fetch was attempted this call, the manifest always
    # reflects the true current on-disk state -- so a caller that skips
    # fetching (e.g. to hand off to the road stage instead) still gets an
    # accurate PARTIAL record rather than a stale or missing one.
    manifest = write_landuse_partial_manifest(districts)

    if not manifest["pending_districts"]:
        merged = merge_landuse_chunks(districts)
        if merged is not None:
            merged.to_file(LANDUSE_FINAL_PATH, driver="GeoJSON")
            print(f"[save] {LANDUSE_FINAL_PATH} ({len(merged)} features) -- land-use layer NOW complete", flush=True)
    else:
        print(f"[status] land-use layer remains PARTIAL: {manifest['n_cached']}/{manifest['n_districts']} districts. "
              f"Final citywide file NOT written.", flush=True)


def run_road_stage(districts: gpd.GeoDataFrame) -> None:
    print("\n=== Road network (independent stage) ===", flush=True)
    if ROAD_FINAL_PATH.exists():
        print(f"[cache] {ROAD_FINAL_PATH} already exists (layer already complete, not re-fetched)", flush=True)
        return

    print("[health-check] checking Overpass endpoint before starting road acquisition...", flush=True)
    health = _check_overpass_health()
    print(f"[health-check] {health}", flush=True)

    if health["status"] != "healthy":
        cached = [n for n in districts["district"] if (ROAD_CHUNK_DIR / f"{n}.graphml").exists()]
        pending = [n for n in districts["district"] if n not in cached]
        manifest = {
            "layer_status": "PENDING_ENDPOINT_OUTAGE",
            "health_check": health,
            "n_districts": len(districts),
            "n_cached": len(cached),
            "cached_districts": cached,
            "pending_districts": pending,
        }
        ROAD_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[pending] endpoint not healthy ({health['status']}) -- recording roads as "
              f"PENDING_ENDPOINT_OUTAGE without spending any road retry budget. "
              f"{len(cached)}/{len(districts)} already cached, {len(pending)} pending. "
              f"Manifest -> {ROAD_MANIFEST_PATH}", flush=True)
        return

    print("[health-check] endpoint healthy -- beginning road-network acquisition", flush=True)
    road_summary = fetch_road_network_chunked(districts)
    ROAD_MANIFEST_PATH.write_text(json.dumps(road_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    composed = merge_road_chunks(districts)
    if composed is not None:
        ox.save_graphml(composed, ROAD_FINAL_PATH)
        print(f"[save] {ROAD_FINAL_PATH} ({len(composed.nodes)} nodes, {len(composed.edges)} edges) "
              f"-- road network layer NOW complete", flush=True)
    else:
        print("[status] road network layer remains incomplete. Final citywide file NOT written.", flush=True)


def main() -> None:
    import sys

    districts = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    assert districts.crs.to_string() == cfg.METRIC_CRS
    assert len(districts) == 39, f"expected 39 districts, found {len(districts)}"
    print(f"Chunked citywide fetch across {len(districts)} districts (Overpass endpoint: {OVERPASS_ENDPOINT})", flush=True)

    stage = sys.argv[1] if len(sys.argv) > 1 else "both"
    valid_stages = {"both", "landuse", "roads", "landuse-manifest-only"}
    if stage not in valid_stages:
        raise SystemExit(f"unknown stage {stage!r}; expected one of {sorted(valid_stages)}")

    if stage == "landuse-manifest-only":
        write_landuse_partial_manifest(districts)
        return

    if stage in ("both", "landuse"):
        run_landuse_stage(districts)

    if stage in ("both", "roads"):
        run_road_stage(districts)

    print(f"\nLand-use layer complete: {LANDUSE_FINAL_PATH.exists()}. "
          f"Road network layer complete: {ROAD_FINAL_PATH.exists()}.", flush=True)


if __name__ == "__main__":
    main()
