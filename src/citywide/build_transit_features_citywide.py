"""Citywide transit features (Section 4, family 3 of 4 not requiring new
Overpass requests).

Both cached GTFS feeds already cover the ENTIRE city (they are agency-wide
publications, not pilot-scoped subsets), so no new fetch or geographic
extension is needed -- src.features.transit_infrastructure.load_all_transit_stops
already loads and classifies every stop in both feeds citywide, unchanged.
This script reuses that plus transit_accessibility.py and transit_service.py
UNCHANGED, only pointing them at the citywide 22,322-cell grid instead of
the 514-cell pilot grid.

Feed inventory (see transit_tag_config.py for full detail):
  - main_gtfs (İBB "Toplu Ulaşım GTFS Verisi"): metro/tram/rail/ferry.
    STATIC/INFRASTRUCTURE ONLY -- every calendar.csv service window had
    already expired as of retrieval (page states it will not be updated).
    Used for station locations and route topology, never departure
    frequency.
  - iett_gtfs (İETT GTFS Verisi): bus/metrobüs. Current as of retrieval
    (service_id=0 "WEEKDAYS" valid through 2026-12-31). Used for both
    infrastructure AND departure-frequency features.
These two feeds are never combined for frequency -- only main_gtfs's
STOPS/ROUTES are pooled with iett_gtfs's for station-count/distance
features; departure counts come from iett_gtfs alone.

Raw/static accessibility measures (distance-to-nearest, stop counts,
routes serving a cell) are kept separate from any composite/derived
measure -- this script produces only the former (as the pilot did); no
composite transit-accessibility index is computed here.

Outputs:
  data/processed/citywide/features/transit_features_citywide.parquet
  data/processed/citywide/qa/transit_qa_citywide.json
  data/processed/citywide/qa/coverage_gate_transit.json
  data/processed/citywide/qa/transit_feed_inventory.json
"""

from __future__ import annotations

import json
import time

import geopandas as gpd
import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.coverage_gate import coverage_report, print_report
from src.data.fetch_transit_data import fetch_iett_gtfs, fetch_main_gtfs
from src.features import transit_tag_config as tcfg
from src.features.transit_accessibility import (
    MODE_COUNT_COLS,
    compute_distance_and_accessibility_features,
    compute_station_counts,
)
from src.features.transit_infrastructure import load_all_transit_stops
from src.features.transit_service import compute_bus_departures, compute_route_diversity
from src.utils import config as cfg


def load_citywide_grid() -> gpd.GeoDataFrame:
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 22322, f"expected the frozen citywide grid (22,322 cells), found {len(grid)}"
    assert grid["grid_id"].is_unique
    return grid


def build_feed_inventory(main_meta_path, iett_meta_path) -> dict:
    main_meta = json.loads(main_meta_path.read_text(encoding="utf-8"))
    iett_meta = json.loads(iett_meta_path.read_text(encoding="utf-8"))
    return {
        "main_gtfs": {
            "provider": main_meta["provider"], "dataset_name": main_meta["dataset_name"],
            "modes_covered": main_meta["modes_covered"], "resource_last_modified": main_meta["resource_last_modified"],
            "retrieval_date": main_meta["retrieval_date"],
            "component_type": "STATIC_INFRASTRUCTURE_AND_ROUTE_TOPOLOGY_ONLY (calendar expired -- NOT used for frequency)",
            "reliability_note": main_meta["reliability_note"],
        },
        "iett_gtfs": {
            "provider": iett_meta["provider"], "dataset_name": iett_meta["dataset_name"],
            "modes_covered": iett_meta["modes_covered"], "resource_last_modified": iett_meta["resource_last_modified"],
            "retrieval_date": iett_meta["retrieval_date"],
            "component_type": "SCHEDULED_SERVICE (current calendar -- used for infrastructure AND departure frequency)",
            "reliability_note": iett_meta["reliability_note"],
        },
        "combination_policy": "Stops/routes from both feeds are pooled for station-count and distance-to-nearest "
        "features (both represent real, non-overlapping physical infrastructure once mode-deduplicated). "
        "Departure-frequency features use iett_gtfs ONLY -- main_gtfs's calendar is expired and cannot support "
        "a defensible current-day departure count, so no rail/tram/ferry departure-frequency column exists.",
        "temporal_alignment_caveat": "main_gtfs infrastructure last modified 2023-2024; iett_gtfs 2026-03-17; "
        "WorldPop population reference year 2020; OSM POIs/buildings retrieved 2026-09-18. Feeds are NOT temporally "
        "aligned with each other or with other feature families -- documented, not corrected, per project policy.",
    }


def pilot_regression_check(transit_gdf: gpd.GeoDataFrame) -> dict:
    pilot_path = cfg.PROJECT_ROOT / "data" / "processed" / "features" / "transit_features.parquet"
    pilot_qa_path = cfg.PROJECT_ROOT / "data" / "processed" / "features" / "transit_qa_report.json"
    if not pilot_path.exists():
        return {"status": "SKIPPED", "reason": f"{pilot_path} not found"}

    pilot = gpd.read_parquet(pilot_path)
    pilot_qa = json.loads(pilot_qa_path.read_text(encoding="utf-8")) if pilot_qa_path.exists() else {}

    compare_cols = [
        "total_transit_stop_count", "bus_stop_count", "metro_station_count", "rail_station_count",
        "tram_station_count", "ferry_terminal_count", "distance_to_nearest_transit_m",
        "transit_stops_within_500m", "fixed_guideway_stations_within_1000m",
        "number_of_transit_modes_accessible", "bus_departures_per_day",
    ]
    compare_cols = [c for c in compare_cols if c in pilot.columns and c in transit_gdf.columns]

    comparison = {}
    for district in ["Kadıköy", "Üsküdar", "Maltepe"]:
        pilot_sub = pilot[pilot["district"] == district] if "district" in pilot.columns else None
        cw_sub = transit_gdf[transit_gdf["district"] == district]
        if pilot_sub is None or len(pilot_sub) == 0 or len(cw_sub) == 0:
            comparison[district] = {"status": "district not found in one of the two datasets"}
            continue
        d = {}
        for c in compare_cols:
            pilot_val = pilot_sub[c].sum() if c in ("total_transit_stop_count", "bus_stop_count", "metro_station_count", "rail_station_count", "tram_station_count", "ferry_terminal_count", "bus_departures_per_day") else pilot_sub[c].mean()
            cw_val = cw_sub[c].sum() if c in ("total_transit_stop_count", "bus_stop_count", "metro_station_count", "rail_station_count", "tram_station_count", "ferry_terminal_count", "bus_departures_per_day") else cw_sub[c].mean()
            d[c] = {"pilot": round(float(pilot_val), 2), "citywide": round(float(cw_val), 2), "diff": round(float(cw_val - pilot_val), 2)}
        comparison[district] = d

    return {
        "status": "COMPARED",
        "note": "Sum for count-type features (stop counts, departures), mean for distance/accessibility features. "
        "Small differences are expected only from a different grid build (citywide grid was rebuilt independently, "
        "so cell boundaries/centroids near district edges differ slightly); the underlying GTFS stop set is "
        "IDENTICAL (same cached feeds, no re-fetch) so large differences would indicate a real regression.",
        "pilot_total_stops_by_mode_citywide": pilot_qa.get("total_stops_by_mode_citywide"),
        "comparison": comparison,
    }


def main() -> None:
    print("=" * 72)
    print("Citywide transit features (39 districts, 22,322-cell grid)")
    print("=" * 72)

    grid = load_citywide_grid()

    print("\n[0/4] Feed inventory...")
    main_dir = fetch_main_gtfs()
    iett_dir = fetch_iett_gtfs()
    inventory = build_feed_inventory(main_dir / "_meta.json", iett_dir / "_meta.json")
    print(json.dumps(inventory, indent=2, ensure_ascii=False))

    print("\n[1/4] Loading + classifying stops (citywide by construction, no re-fetch)...")
    t0 = time.time()
    stops, load_diag = load_all_transit_stops(main_dir, iett_dir)
    print(f"  loaded {len(stops)} stop-mode rows in {time.time() - t0:.1f}s")
    print(f"  stops by mode (citywide): {load_diag['n_stops_by_mode_total_citywide']}")
    print(f"  duplicate stops removed: {load_diag['n_duplicate_stops_removed']}")

    print("\n[2/4] Station counts, distance/accessibility, route diversity, bus departures...")
    t0 = time.time()
    counts_df = compute_station_counts(stops, grid)
    print(f"  station counts: {time.time() - t0:.1f}s")

    t0 = time.time()
    dist_df = compute_distance_and_accessibility_features(stops, grid)
    print(f"  distance/accessibility: {time.time() - t0:.1f}s")

    t0 = time.time()
    route_df = compute_route_diversity(stops, grid)
    print(f"  route diversity: {time.time() - t0:.1f}s")

    t0 = time.time()
    departures_df, departures_diag = compute_bus_departures(iett_dir, stops, grid)
    print(f"  bus departures: {time.time() - t0:.1f}s")

    grid_ids = grid["grid_id"]
    for df, label in [(counts_df, "counts"), (dist_df, "distance"), (route_df, "routes"), (departures_df, "departures")]:
        missing = set(grid_ids) - set(df["grid_id"])
        assert not missing, f"{label}: {len(missing)} grid cells disappeared"
        assert len(df) == len(grid_ids)

    merged = counts_df.merge(dist_df, on="grid_id").merge(route_df, on="grid_id").merge(departures_df, on="grid_id")
    assert len(merged) == 22322 and merged["grid_id"].is_unique

    base = grid[["grid_id", "district", "land_area_m2", "geometry"]]
    transit_gdf = gpd.GeoDataFrame(base.merge(merged, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)

    print("\n[3/4] QA...")
    numeric_cols = [c for c in merged.columns if c != "grid_id" and pd.api.types.is_numeric_dtype(merged[c])]
    desc = transit_gdf[numeric_cols].describe().T[["min", "50%", "mean", "max"]].rename(columns={"50%": "median"}).round(3).to_dict(orient="index")

    flagged = []
    for c in numeric_cols:
        vals = transit_gdf[c]
        mu, sigma = vals.mean(), vals.std()
        if sigma == 0 or np.isnan(sigma):
            continue
        z = (vals - mu) / sigma
        extreme = transit_gdf.loc[z.abs() > 4, ["grid_id", "district"]].copy()
        if len(extreme):
            extreme["feature"] = c
            extreme["value"] = vals.loc[extreme.index]
            extreme["z_score"] = z.loc[extreme.index]
            flagged.append(extreme)
    flagged_df = pd.concat(flagged, ignore_index=True) if flagged else pd.DataFrame(columns=["grid_id", "district", "feature", "value", "z_score"])

    stops_metric = stops.to_crs(cfg.METRIC_CRS) if stops.crs.to_string() != cfg.METRIC_CRS else stops
    study_area = gpd.read_file(cfg.DATA_PROCESSED / "study_area_metric.gpkg").geometry.iloc[0]
    in_study_area = stops_metric[stops_metric.geometry.within(study_area)]

    districts_gdf = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    stops_by_district = gpd.sjoin(stops_metric, districts_gdf[["district", "geometry"]], predicate="within", how="left")
    n_stops_no_district = int(stops_by_district["district"].isna().sum())
    stops_per_district = stops_by_district["district"].value_counts().to_dict()
    districts_with_zero_stops = [d for d in districts_gdf["district"] if d not in stops_per_district]

    by_district_zero_transit = transit_gdf.groupby("district")["total_transit_stop_count"].apply(lambda s: (s == 0).mean() * 100).round(1).to_dict()

    # Implausible concentration check: is any single grid cell holding an
    # outsized share of a citywide stop-mode total (would suggest a
    # duplicate-coordinate or join bug rather than real infrastructure)?
    concentration_flags = {}
    for mode, col in MODE_COUNT_COLS.items():
        total = transit_gdf[col].sum()
        if total > 0:
            max_cell = transit_gdf[col].max()
            share = max_cell / total * 100
            if share > 20 and total > 5:
                concentration_flags[mode] = {"max_single_cell_count": int(max_cell), "pct_of_citywide_total": round(share, 1)}

    edge_cells = transit_gdf[transit_gdf["distance_to_nearest_transit_m"] > transit_gdf["distance_to_nearest_transit_m"].quantile(0.99)]

    regression = pilot_regression_check(transit_gdf)

    qa = {
        "n_grid_cells": len(transit_gdf),
        "n_districts_present": transit_gdf["district"].nunique(),
        "total_stops_by_mode_citywide": load_diag["n_stops_by_mode_total_citywide"],
        "stops_inside_study_area_by_mode": in_study_area["mode"].value_counts().to_dict(),
        "n_duplicate_stops_removed": load_diag["n_duplicate_stops_removed"],
        "n_stops_with_no_in_scope_route": {
            "main_gtfs": load_diag["main_gtfs"]["n_stops_with_no_in_scope_route"],
            "iett_gtfs": load_diag["iett_gtfs"]["n_stops_with_no_in_scope_route"],
        },
        "n_stops_with_unrecoverable_invalid_coordinates_iett": load_diag["iett_gtfs"].get("n_stops_with_unrecoverable_invalid_coordinates", 0),
        "district_coverage": {
            "n_districts_with_zero_transit_stops_entirely": len(districts_with_zero_stops),
            "districts_with_zero_transit_stops_entirely": districts_with_zero_stops,
            "n_stops_not_falling_in_any_district_polygon": n_stops_no_district,
            "stop_count_by_district": stops_per_district,
            "pct_cells_zero_transit_by_district": by_district_zero_transit,
        },
        "implausible_concentration_flags": concentration_flags,
        "pct_grids_with_zero_transit_stop": float((transit_gdf["total_transit_stop_count"] == 0).mean() * 100),
        "pct_grids_within_500m_of_transit": float((transit_gdf["transit_stops_within_500m"] > 0).mean() * 100),
        "pct_grids_within_1km_of_fixed_guideway": float((transit_gdf["fixed_guideway_stations_within_1000m"] > 0).mean() * 100),
        "n_edge_cells_over_p99_distance": len(edge_cells),
        "p99_distance_to_nearest_transit_m": float(transit_gdf["distance_to_nearest_transit_m"].quantile(0.99)),
        "max_distance_to_nearest_transit_m": float(transit_gdf["distance_to_nearest_transit_m"].max()),
        "descriptive_stats": desc,
        "n_extreme_value_cells_flagged": len(flagged_df),
        "top_flagged_cells": flagged_df.sort_values("z_score", ascending=False).head(20).to_dict(orient="records") if len(flagged_df) else [],
        "missing_values": {c: int(transit_gdf[c].isna().sum()) for c in numeric_cols},
        "bus_departures_diagnostics": departures_diag,
        "pilot_3_district_regression_check": regression,
        "raw_vs_composite_note": "All features here are raw/static (stop counts, nearest-distance, route counts, "
        "scheduled departure counts) -- no composite/derived accessibility index is computed in this stage.",
        "completeness_status": "COMPLETE for all GTFS-derivable features; no OSM road-network information used.",
    }

    out_dir = cfg.DATA_FEATURES
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "transit_features_citywide.parquet"
    transit_gdf.to_parquet(out_path)
    print(f"\n[save] {out_path}")

    qa_dir = cfg.DATA_PROCESSED / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_path = qa_dir / "transit_qa_citywide.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {qa_path}")

    inv_path = qa_dir / "transit_feed_inventory.json"
    inv_path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[save] {inv_path}")

    value_cols = ["total_transit_stop_count", "transit_stops_within_500m", "number_of_transit_modes_accessible"]
    report = coverage_report(transit_gdf, value_cols)
    print_report(report, "transit")
    gate_path = qa_dir / "coverage_gate_transit.json"
    gate_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[save] {gate_path}")

    print("\n--- SUMMARY ---")
    print(f"Districts present: {qa['n_districts_present']}/39")
    print(f"Districts with ZERO transit stops entirely: {qa['district_coverage']['n_districts_with_zero_transit_stops_entirely']} "
          f"{qa['district_coverage']['districts_with_zero_transit_stops_entirely']}")
    print(f"Cells with zero transit stop present: {qa['pct_grids_with_zero_transit_stop']:.1f}%")
    print(f"Cells within 500m of any transit: {qa['pct_grids_within_500m_of_transit']:.1f}%")
    print(f"Implausible concentration flags: {concentration_flags if concentration_flags else 'none'}")
    print(f"Pilot 3-district regression check: {regression['status']}")


if __name__ == "__main__":
    main()
