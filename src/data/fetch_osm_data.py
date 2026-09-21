"""Phase 3A data acquisition: fetch and cache raw OSM data once.

Downloads POIs, building footprints, land-use/green polygons and the road
network for the pilot study area (Kadıköy, Üsküdar, Maltepe) plus a buffer,
and caches each as an untouched raw artifact under data/raw/osm/. Re-running
this script loads the cache instead of re-fetching; delete a cache file to
force a re-fetch of that layer.

Run from the project root:
    .venv/bin/python -m src.data.fetch_osm_data
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import requests

from src.features import osm_tag_config as tags
from src.utils import config as cfg

ox.settings.timeout = 300
ox.settings.log_console = False

RAW_OSM_DIR = cfg.DATA_RAW / "osm"


def get_osm_data_timestamp() -> str | None:
    """A trivial Overpass query just to read the live database timestamp
    (osm3s.timestamp_osm_base), i.e. how current the fetched data is."""
    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": "[out:json];node(1);out;"},
            headers={"User-Agent": "istanbul-mobility-research/0.1"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("osm3s", {}).get("timestamp_osm_base")
    except Exception as exc:  # noqa: BLE001 - metadata is best-effort, never fatal
        print(f"[WARN] could not retrieve OSM data timestamp: {exc}")
        return None


def get_query_polygon() -> tuple[object, object]:
    """Returns (polygon_metric, polygon_wgs84): the buffered, simplified
    study-area polygon used to bound every OSM query."""
    study_area_path = cfg.DATA_PROCESSED / "study_area_metric.gpkg"
    if not study_area_path.exists():
        raise FileNotFoundError(
            f"{study_area_path} not found. Run src.data.build_study_grid first "
            "(Phase 2 must exist before Phase 3A can query a study-area extent)."
        )
    sa = gpd.read_file(study_area_path)
    assert sa.crs.to_string() == cfg.METRIC_CRS, "study area must be in the metric CRS before buffering"

    poly_m = sa.geometry.iloc[0].buffer(cfg.OSM_QUERY_BUFFER_M).simplify(
        cfg.OSM_QUERY_SIMPLIFY_TOLERANCE_M, preserve_topology=True
    )
    poly_ll = gpd.GeoSeries([poly_m], crs=cfg.METRIC_CRS).to_crs(cfg.STORAGE_CRS).iloc[0]
    return poly_m, poly_ll


def _write_meta(path: Path, layer: str, extra: dict) -> None:
    meta = {
        "layer": layer,
        "source": cfg.OSM_SOURCE,
        "license": cfg.OSM_LICENSE,
        "retrieval_date": cfg.OSM_RETRIEVAL_DATE,
        "osm_data_timestamp": get_osm_data_timestamp(),
        "query_buffer_m": cfg.OSM_QUERY_BUFFER_M,
        "query_polygon_simplify_tolerance_m": cfg.OSM_QUERY_SIMPLIFY_TOLERANCE_M,
        "software": {
            "python": platform.python_version(),
            "geopandas": gpd.__version__,
            "osmnx": ox.__version__,
        },
        **extra,
    }
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def fetch_pois(poly_ll) -> gpd.GeoDataFrame:
    raw_path = RAW_OSM_DIR / "osm_pois_raw.geojson"
    meta_path = RAW_OSM_DIR / "osm_pois_raw.meta.json"
    if raw_path.exists():
        print(f"[cache] loading POIs from {raw_path}")
        return gpd.read_file(raw_path)

    print("[fetch] querying OSM for POIs (amenity/shop/office/tourism/leisure/healthcare)...")
    gdf = ox.features_from_polygon(poly_ll, tags=tags.POI_FETCH_TAGS)
    gdf = gdf.reset_index()  # keep element_type/osmid as columns rather than a MultiIndex
    RAW_OSM_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_file(raw_path, driver="GeoJSON")
    _write_meta(meta_path, "pois", {"query_filter": tags.POI_FETCH_TAGS, "n_features": len(gdf)})
    print(f"[cache] wrote {len(gdf)} POIs -> {raw_path}")
    return gdf


def fetch_buildings(poly_ll) -> gpd.GeoDataFrame:
    raw_path = RAW_OSM_DIR / "osm_buildings_raw.geojson"
    meta_path = RAW_OSM_DIR / "osm_buildings_raw.meta.json"
    if raw_path.exists():
        print(f"[cache] loading buildings from {raw_path}")
        return gpd.read_file(raw_path)

    print("[fetch] querying OSM for building footprints...")
    gdf = ox.features_from_polygon(poly_ll, tags=tags.BUILDING_FETCH_TAGS)
    gdf = gdf.reset_index()
    RAW_OSM_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_file(raw_path, driver="GeoJSON")
    _write_meta(meta_path, "buildings", {"query_filter": tags.BUILDING_FETCH_TAGS, "n_features": len(gdf)})
    print(f"[cache] wrote {len(gdf)} buildings -> {raw_path}")
    return gdf


def fetch_landuse(poly_ll) -> gpd.GeoDataFrame:
    raw_path = RAW_OSM_DIR / "osm_landuse_green_raw.geojson"
    meta_path = RAW_OSM_DIR / "osm_landuse_green_raw.meta.json"
    if raw_path.exists():
        print(f"[cache] loading land-use/green polygons from {raw_path}")
        return gpd.read_file(raw_path)

    print("[fetch] querying OSM for land-use/green polygons (leisure/landuse/natural)...")
    gdf = ox.features_from_polygon(poly_ll, tags=tags.LANDUSE_FETCH_TAGS)
    gdf = gdf.reset_index()
    RAW_OSM_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_file(raw_path, driver="GeoJSON")
    _write_meta(meta_path, "landuse_green", {"query_filter": tags.LANDUSE_FETCH_TAGS, "n_features": len(gdf)})
    print(f"[cache] wrote {len(gdf)} land-use/green polygons -> {raw_path}")
    return gdf


def fetch_road_network(poly_ll):
    raw_path = RAW_OSM_DIR / "osm_road_network_raw.graphml"
    meta_path = RAW_OSM_DIR / "osm_road_network_raw.meta.json"
    if raw_path.exists():
        print(f"[cache] loading road network from {raw_path}")
        return ox.load_graphml(raw_path)

    print("[fetch] querying OSM for the road network (network_type='all')...")
    G = ox.graph_from_polygon(poly_ll, network_type="all", retain_all=True, simplify=True)
    RAW_OSM_DIR.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G, raw_path)
    _write_meta(
        meta_path,
        "road_network",
        {
            "query_filter": {"network_type": "all", "retain_all": True, "simplify": True},
            "n_nodes": len(G.nodes),
            "n_edges": len(G.edges),
        },
    )
    print(f"[cache] wrote graph ({len(G.nodes)} nodes, {len(G.edges)} edges) -> {raw_path}")
    return G


def main() -> None:
    print("=" * 72)
    print("Istanbul Urban Mobility Intelligence — Phase 3A: OSM data acquisition")
    print("=" * 72)
    _, poly_ll = get_query_polygon()

    fetch_pois(poly_ll)
    fetch_buildings(poly_ll)
    fetch_landuse(poly_ll)
    fetch_road_network(poly_ll)

    print("\nAll raw OSM layers cached under", RAW_OSM_DIR)


if __name__ == "__main__":
    main()
