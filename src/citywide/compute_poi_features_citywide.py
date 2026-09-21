"""Citywide POI features -- reuses src.features.poi_features.compute_poi_features
UNCHANGED (12-category classification, within-category node/way dedup,
representative-point cell assignment, count/density/diversity/entropy),
against the already-fetched citywide raw POI cache
(data/raw/osm/osm_pois_raw_citywide.geojson, 107,002 features, fetched
earlier in Section 4 -- not re-fetched here) and the frozen citywide grid.

This was the one already-fetched feature family that had not yet had its
per-cell features actually computed (buildings/population/terrain/transit/
cycling were completed; this closes that gap before the master merge).

Outputs:
  data/processed/citywide/features/poi_features_citywide.parquet
  data/processed/citywide/qa/poi_qa_citywide.json
  data/processed/citywide/qa/coverage_gate_poi.json
"""

from __future__ import annotations

import json
import time

import geopandas as gpd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.coverage_gate import coverage_report, print_report
from src.features import osm_tag_config as tags
from src.features.poi_features import compute_poi_features
from src.utils import config as cfg


def main() -> None:
    print("=" * 72)
    print("Citywide POI features (39 districts, 22,322-cell grid)")
    print("=" * 72)

    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 22322, f"expected the frozen citywide grid (22,322 cells), found {len(grid)}"
    assert grid["grid_id"].is_unique

    raw_path = cfg.DATA_RAW / "osm" / "osm_pois_raw_citywide.geojson"
    print(f"[load] raw POIs: {raw_path}")
    t0 = time.time()
    pois_raw = gpd.read_file(raw_path)
    load_elapsed = time.time() - t0
    print(f"  loaded {len(pois_raw)} raw POIs in {load_elapsed:.1f}s")
    assert len(pois_raw) == 107002, f"expected 107,002 raw POIs (matching the earlier citywide fetch), got {len(pois_raw)}"

    print("[compute] POI features...")
    t0 = time.time()
    result, diag = compute_poi_features(pois_raw, grid)
    compute_elapsed = time.time() - t0
    print(f"  computed for {len(result)} cells in {compute_elapsed:.1f}s")
    print(f"  diagnostics: {diag}")

    missing = set(grid["grid_id"]) - set(result["grid_id"])
    assert not missing, f"{len(missing)} grid cells disappeared during POI processing"
    assert len(result) == 22322 and result["grid_id"].is_unique

    base = grid[["grid_id", "district", "geometry"]]
    poi_gdf = gpd.GeoDataFrame(base.merge(result, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)

    out_dir = cfg.DATA_FEATURES
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "poi_features_citywide.parquet"
    poi_gdf.to_parquet(out_path)
    print(f"\n[save] {out_path}")

    qa_dir = cfg.DATA_PROCESSED / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    n_districts_present = poi_gdf["district"].nunique()
    qa = {
        "n_grid_cells": len(poi_gdf),
        "n_districts_present": n_districts_present,
        "fetch_diagnostics": diag,
        "n_zero_poi_cells": int((poi_gdf["total_poi_count"] == 0).sum()),
        "pct_zero_poi_cells": round(float((poi_gdf["total_poi_count"] == 0).mean() * 100), 2),
        "descriptive_stats": poi_gdf[["total_poi_count", "poi_density_km2", "poi_category_count", "poi_entropy"]].describe().T[["min", "50%", "mean", "max"]].rename(columns={"50%": "median"}).round(3).to_dict(orient="index"),
        "category_totals_citywide": {c: int(poi_gdf[c].sum()) for c in tags.POI_CATEGORIES},
    }
    qa_path = qa_dir / "poi_qa_citywide.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {qa_path}")

    value_cols = ["total_poi_count", "poi_density_km2", "poi_category_count"]
    report = coverage_report(poi_gdf, value_cols)
    print_report(report, "poi")
    gate_path = qa_dir / "coverage_gate_poi.json"
    gate_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[save] {gate_path}")

    print("\n--- SUMMARY ---")
    print(f"Districts present: {n_districts_present}/39")
    print(f"Cells with zero POIs: {qa['pct_zero_poi_cells']}%")
    print(f"Category totals: {qa['category_totals_citywide']}")


if __name__ == "__main__":
    main()
