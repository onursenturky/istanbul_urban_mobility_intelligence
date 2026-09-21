"""Phase 3E data acquisition: İBB bicycle infrastructure + OSM cycling ways.

Downloads/caches, once, under data/raw/cycling/:
  - İBB's official bicycle-paths and bicycle-parking GeoJSONs (untouched)
  - OSM cycling-relevant ways (highway=cycleway + cycleway=* attributed
    roads) for the buffered study area, via osmnx

Run from the project root:
    .venv/bin/python -m src.data.fetch_cycling_infrastructure_data
"""

from __future__ import annotations

import json

import geopandas as gpd
import osmnx as ox
import requests

from src.features import cycling_source_config as ccfg
from src.utils import config as cfg

ox.settings.timeout = 300
ox.settings.log_console = False


def _fetch_ibb_geojson(source_cfg: dict, out_name: str):
    out_path = cfg.DATA_RAW_CYCLING / f"{out_name}.geojson"
    meta_path = cfg.DATA_RAW_CYCLING / f"{out_name}.meta.json"
    if out_path.exists():
        print(f"[cache] {out_name} already cached at {out_path}")
        return out_path

    cfg.DATA_RAW_CYCLING.mkdir(parents=True, exist_ok=True)
    print(f"[fetch] downloading {source_cfg['dataset_name']} ...")
    resp = requests.get(source_cfg["download_url"], timeout=120, headers={"User-Agent": "istanbul-mobility-research/0.1"})
    resp.raise_for_status()
    out_path.write_bytes(resp.content)

    meta = {**source_cfg, "retrieval_date": cfg.CYCLING_RETRIEVAL_DATE, "file_size_bytes": len(resp.content)}
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[cache] wrote {out_name} ({len(resp.content)/1e3:.0f} KB) -> {out_path}")
    return out_path


def fetch_ibb_bike_paths():
    return _fetch_ibb_geojson(ccfg.IBB_BIKE_PATHS, "ibb_bisiklet_yollari")


def fetch_ibb_parking():
    return _fetch_ibb_geojson(ccfg.IBB_PARKING, "ibb_bisiklet_parking")


def get_query_polygon():
    sa = gpd.read_file(cfg.DATA_PROCESSED / "study_area_metric.gpkg")
    poly_m = sa.geometry.iloc[0].buffer(cfg.CYCLING_QUERY_BUFFER_M).simplify(25, preserve_topology=True)
    return gpd.GeoSeries([poly_m], crs=cfg.METRIC_CRS).to_crs(cfg.STORAGE_CRS).iloc[0]


def fetch_osm_cycling_ways():
    out_path = cfg.DATA_RAW_CYCLING / "osm_cycling_ways_raw.geojson"
    meta_path = cfg.DATA_RAW_CYCLING / "osm_cycling_ways_raw.meta.json"
    if out_path.exists():
        print(f"[cache] OSM cycling ways already cached at {out_path}")
        return out_path

    poly_ll = get_query_polygon()
    print("[fetch] querying OSM for cycling-relevant ways (highway=cycleway + cycleway=* tags)...")
    tags = {
        "highway": ["cycleway"],
        "cycleway": True,
        "cycleway:left": True,
        "cycleway:right": True,
        "cycleway:both": True,
    }
    gdf = ox.features_from_polygon(poly_ll, tags=tags)
    gdf = gdf.reset_index()
    gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])]

    cfg.DATA_RAW_CYCLING.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="GeoJSON")
    meta = {
        "source": "OpenStreetMap contributors",
        "license": ccfg.OSM_LICENSE,
        "retrieval_date": cfg.CYCLING_RETRIEVAL_DATE,
        "query_filter": tags,
        "query_buffer_m": cfg.CYCLING_QUERY_BUFFER_M,
        "n_features": len(gdf),
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[cache] wrote {len(gdf)} OSM cycling ways -> {out_path}")
    return out_path


def fetch_osm_bicycle_parking_for_completeness_check():
    """Fetched only for the QA completeness comparison — never merged into
    the primary bicycle_parking_count feature (İBB is used alone for that,
    per the stated source priority)."""
    out_path = cfg.DATA_RAW_CYCLING / "osm_bicycle_parking_raw.geojson"
    meta_path = cfg.DATA_RAW_CYCLING / "osm_bicycle_parking_raw.meta.json"
    if out_path.exists():
        print(f"[cache] OSM bicycle parking already cached at {out_path}")
        return out_path

    poly_ll = get_query_polygon()
    gdf = ox.features_from_polygon(poly_ll, tags={"amenity": ["bicycle_parking"]})
    gdf = gdf.reset_index()

    cfg.DATA_RAW_CYCLING.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="GeoJSON")
    meta = {
        "source": "OpenStreetMap contributors", "license": ccfg.OSM_LICENSE,
        "retrieval_date": cfg.CYCLING_RETRIEVAL_DATE, "query_filter": {"amenity": "bicycle_parking"},
        "n_features": len(gdf), "purpose": "completeness cross-check only, not merged into predictor table",
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[cache] wrote {len(gdf)} OSM bicycle parking points -> {out_path}")
    return out_path


def main() -> None:
    print("=" * 72)
    print("Istanbul Urban Mobility Intelligence — Phase 3E: Cycling infrastructure acquisition")
    print("=" * 72)
    fetch_ibb_bike_paths()
    fetch_ibb_parking()
    fetch_osm_cycling_ways()
    fetch_osm_bicycle_parking_for_completeness_check()


if __name__ == "__main__":
    main()
