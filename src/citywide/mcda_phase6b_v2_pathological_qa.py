"""Phase 6B-V2: pathological-case QA. Reports failures instead of silently
adjusting the model -- if a check fails, that is reported as a
methodological concern, not quietly patched.
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.mcda_phase6b_v2_scoring import load_data
from src.utils import config as cfg

FEATURES_DIR = cfg.DATA_FEATURES
OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda_v2" / "phase6b"
TRANSIT_FEED_META_PATH = cfg.DATA_PROCESSED / "qa" / "transit_feed_inventory.json"


def main() -> None:
    print("=" * 72)
    print("Phase 6B-V2: pathological-case QA")
    print("=" * 72)

    df = load_data()
    extra = pd.read_parquet(FEATURES_DIR / "urban_mobility_features_citywide_v2.parquet",
                             columns=["grid_id", "building_coverage_ratio"])
    df = df.merge(extra, on="grid_id")

    readiness_df = gpd.read_parquet(OUT_DIR / "ebike_readiness_baseline.parquet")
    opportunity_df = pd.read_parquet(OUT_DIR / "ebike_opportunity_baseline.parquet")
    s = df[["grid_id", "district"]].merge(
        readiness_df[["grid_id", "ebike_readiness"]], on="grid_id").merge(
        opportunity_df[["grid_id", "ebike_opportunity", "demand_potential", "cycling_gap"]], on="grid_id")
    s = s.merge(df, on=["grid_id", "district"])

    cases = []

    def add_case(label, mask, note=""):
        n = int(mask.sum())
        if n == 0:
            cases.append({"case": label, "n_cells": 0, "note": note or "no matching cells found"})
            return
        cases.append({
            "case": label, "n_cells": n, "note": note,
            "mean_readiness": round(float(s.loc[mask, "ebike_readiness"].mean()), 4),
            "max_readiness": round(float(s.loc[mask, "ebike_readiness"].max()), 4),
            "mean_opportunity": round(float(s.loc[mask, "ebike_opportunity"].mean()), 4),
            "max_opportunity": round(float(s.loc[mask, "ebike_opportunity"].max()), 4),
            "mean_demand": round(float(s.loc[mask, "demand_potential"].mean()), 4),
        })

    print("\n[1] zero population AND zero buildings...")
    zero_pop_bldg = (s["population_density_calibrated_km2"] == 0) & (s["building_coverage_ratio"] == 0)
    add_case("zero_population_and_zero_buildings", zero_pop_bldg)

    print("[2] zero POI / remote rural (Çatalca, Silivri, Şile)...")
    remote_rural = s["district"].isin(["Çatalca", "Silivri", "Şile"]) & (s["poi_density_km2"] == 0)
    add_case("remote_rural_zero_poi", remote_rural)

    print("[3] dense commercial cores (top 1% POI density)...")
    dense_commercial = s["poi_density_km2"] > s["poi_density_km2"].quantile(0.99)
    add_case("dense_commercial_core_top1pct_poi", dense_commercial)

    print("[4] transit-rich, cycling-poor...")
    transit_rich_cycling_poor = (s["distance_to_nearest_transit_m"] < s["distance_to_nearest_transit_m"].quantile(0.10)) & \
                                 (s["cycle_infrastructure_density_km_per_km2_ibb_only"] == 0)
    add_case("transit_rich_cycling_poor", transit_rich_cycling_poor)

    print("[5] cycling-rich, lower-demand...")
    has_cycling = s["cycle_infrastructure_density_km_per_km2_ibb_only"] > 0
    poi_median_among_cycling = s.loc[has_cycling, "poi_density_km2"].median()
    cycling_rich_low_demand = has_cycling & (s["poi_density_km2"] <= poi_median_among_cycling)
    add_case("cycling_rich_lower_demand", cycling_rich_low_demand,
              note=f"threshold: poi_density_km2<={poi_median_among_cycling:.2f} (median among {int(has_cycling.sum())} cycling-served cells)")

    print("[6] steep / high-road-grade cells...")
    steep_terrain = s["mean_slope_deg"] > 10
    add_case("steep_terrain_slope_gt10deg", steep_terrain)
    high_road_grade = s["mean_absolute_road_grade_pct"] > 10
    add_case("high_road_grade_gt10pct", high_road_grade)

    print("[7] roadless cells...")
    roadless = s["road_density_km_per_km2"] == 0
    add_case("roadless_cells", roadless, note="road_density_km_per_km2==0; mean_absolute_road_grade_pct is NaN for these, excluded from Terrain row-mean, never treated as 0 or worst-case")
    grade_nan_matches_roadless = (s["mean_absolute_road_grade_pct"].isna() == roadless).mean()
    print(f"    grade-NaN matches roadless mask: {grade_nan_matches_roadless*100:.2f}% of cells")

    print("[8] very low road-network denominator (small land_area_m2 boundary slivers with a road present)...")
    s2 = s
    small_denom = (s2["land_area_m2"] < s2["land_area_m2"].quantile(0.01)) & (s2["road_density_km_per_km2"] > 0)
    add_case("small_land_area_denominator_with_road", small_denom,
              note=f"land_area_m2 < p1 ({s2['land_area_m2'].quantile(0.01):.0f} m^2) AND road present -- checks for denominator-driven extreme density/grade values")
    extreme_density_small = s2.loc[small_denom, "road_density_km_per_km2"]
    if len(extreme_density_small):
        print(f"    road_density_km_per_km2 among small-denominator cells: max={extreme_density_small.max():.1f}, "
              f"citywide max={s2['road_density_km_per_km2'].max():.1f}")

    print("[9] stale main-GTFS coverage (metro/tram/rail/ferry static feed, 2023-2024 vintage, topology only)...")
    transit_feed_note = json.loads(TRANSIT_FEED_META_PATH.read_text(encoding="utf-8")) if TRANSIT_FEED_META_PATH.exists() else None
    fixed_guideway_zero_pct = float((s["fixed_guideway_stations_within_1000m"] == 0).mean() * 100)
    print(f"    main_gtfs reliability_note: {transit_feed_note['main_gtfs']['reliability_note'][:150] if transit_feed_note else 'N/A'}...")
    print(f"    pct cells with zero fixed_guideway_stations_within_1000m: {fixed_guideway_zero_pct:.1f}% "
          "(descriptive only -- no ground truth available to test for missing post-2024 stations)")

    print("[10] districts with known transit feed limitations (same main_gtfs staleness, citywide -- not district-specific)...")
    by_district_readiness = s.groupby("district")["ebike_readiness"].mean()
    transit_dim_cols = ["distance_to_nearest_transit_m", "transit_stops_within_500m", "bus_departures_per_day", "fixed_guideway_stations_within_1000m"]
    print("    NOTE: main_gtfs staleness affects station-location topology citywide (not one specific district) -- "
          "no district-specific correction is possible without a newer feed; documented as a blanket limitation.")

    sanity_df = pd.DataFrame(cases)
    print("\n--- pathological case summary ---")
    print(sanity_df.to_string(index=False))

    print("\n[CRITICAL CHECK] remote zero-demand cells must not dominate Opportunity...")
    remote_opp = s.loc[remote_rural, "ebike_opportunity"]
    p90 = s["ebike_opportunity"].quantile(0.90)
    p75 = s["ebike_opportunity"].quantile(0.75)
    pct_top_decile = float((remote_opp >= p90).mean() * 100)
    pct_top_quartile = float((remote_opp >= p75).mean() * 100)
    print(f"  remote rural zero-POI cells (n={int(remote_rural.sum())}): mean_opp={remote_opp.mean():.4f}, "
          f"pct in citywide top decile={pct_top_decile:.2f}%, pct in top quartile={pct_top_quartile:.2f}%")
    check_passed = (pct_top_decile == 0.0) and (pct_top_quartile < 25.0)
    if check_passed:
        print("  PASSED: remote zero-demand cells do not reach the citywide top decile and are under-represented in the top quartile.")
    else:
        print("  *** FAILED *** remote zero-demand cells are over-represented in high-opportunity classes -- reporting, not silently adjusting.")

    qa_output = {
        "cases": cases,
        "critical_check_remote_zero_demand_not_dominating_opportunity": {
            "n_cells": int(remote_rural.sum()), "mean_opportunity": round(float(remote_opp.mean()), 4),
            "pct_in_citywide_top_decile": round(pct_top_decile, 2), "pct_in_citywide_top_quartile": round(pct_top_quartile, 2),
            "passed": bool(check_passed),
        },
        "roadless_cells_grade_handling": {
            "n_roadless": int(roadless.sum()), "pct_roadless": round(float(roadless.mean() * 100), 2),
            "grade_nan_matches_roadless_mask_pct": round(float(grade_nan_matches_roadless * 100), 2),
        },
        "stale_main_gtfs_note": transit_feed_note["main_gtfs"]["reliability_note"] if transit_feed_note else None,
        "pct_cells_zero_fixed_guideway_within_1000m": round(fixed_guideway_zero_pct, 2),
        "methodological_concerns": [] if check_passed else ["CRITICAL CHECK FAILED -- see critical_check_remote_zero_demand_not_dominating_opportunity"],
    }
    (OUT_DIR / "pathological_case_qa.json").write_text(json.dumps(qa_output, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[save] {OUT_DIR / 'pathological_case_qa.json'}")


if __name__ == "__main__":
    main()
