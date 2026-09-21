"""Citywide building features (Section 4).

Reuses src.features.building_features.compute_building_features UNCHANGED
(same clipped-intersection area logic, same representative-point count
logic) against the frozen citywide grid, sourced from the already-fetched
raw buildings cache (converted from GeoJSON to GPKG for practicality —
same 745,253 features, no re-fetch, no semantic change).

Then runs the coverage gate before this family is considered done.
"""

from __future__ import annotations

import json
import time

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.coverage_gate import coverage_report, print_report
from src.features import building_features
from src.utils import config as cfg

import geopandas as gpd


def main() -> None:
    raw_path = cfg.DATA_RAW / "osm" / "osm_buildings_raw_citywide.gpkg"
    grid_path = cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg"

    print(f"[load] grid: {grid_path}")
    grid = gpd.read_file(grid_path)
    assert grid.crs.to_string() == cfg.METRIC_CRS
    print(f"  {len(grid)} cells, {grid['district'].nunique()} districts")

    print(f"[load] raw buildings: {raw_path}")
    t0 = time.time()
    buildings_raw = gpd.read_file(raw_path)
    load_elapsed = time.time() - t0
    print(f"  loaded {len(buildings_raw)} buildings in {load_elapsed:.1f}s")
    assert len(buildings_raw) == 745253, f"expected 745253 buildings, got {len(buildings_raw)} -- raw cache may be incomplete"

    print("[compute] building features (vectorized overlay)...")
    t0 = time.time()
    result, diagnostics = building_features.compute_building_features(buildings_raw, grid)
    compute_elapsed = time.time() - t0
    print(f"  computed for {len(result)} cells in {compute_elapsed:.1f}s")
    print(f"  diagnostics: {diagnostics}")

    out_dir = cfg.DATA_FEATURES
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "building_features_citywide.geojson"
    merged = grid[["grid_id", "district", "geometry"]].merge(result, on="grid_id", how="left")
    merged.to_file(out_path, driver="GeoJSON")
    print(f"[save] {out_path}")

    runtime_record = {
        "raw_fetch_seconds": 152.6,
        "raw_save_seconds_geojson": 122.6,
        "geojson_to_gpkg_conversion": "background ogr2ogr, timed separately",
        "raw_load_seconds_gpkg": round(load_elapsed, 1),
        "feature_compute_seconds": round(compute_elapsed, 1),
        "n_cells": len(result),
        "n_buildings": len(buildings_raw),
    }
    runtime_path = cfg.DATA_PROCESSED / "qa" / "building_features_runtime.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(json.dumps(runtime_record, indent=2), encoding="utf-8")
    print(f"[save] runtime record: {runtime_path}")

    value_cols = ["building_count", "building_footprint_area_m2", "building_coverage_ratio", "mean_building_footprint_m2"]
    report = coverage_report(merged, value_cols)
    print_report(report, "buildings")
    gate_path = cfg.DATA_PROCESSED / "qa" / "coverage_gate_buildings.json"
    gate_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[save] coverage gate report: {gate_path}")


if __name__ == "__main__":
    main()
