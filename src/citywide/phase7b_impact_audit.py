"""Phase 7B: V1 -> V2 impact audit -- schema/integrity/distribution/coverage,
redundancy (Spearman), and scaling-risk (Phase 5C failure-mode) checks.

Read-only analysis over urban_mobility_features_citywide.parquet (V1) and
urban_mobility_features_citywide_v2.parquet (V2). No transformation is
applied to either file; this only measures and reports.

Outputs:
  data/processed/citywide/qa/phase7b_impact_audit.json
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

FEATURES_DIR = cfg.DATA_FEATURES
QA_DIR = cfg.DATA_PROCESSED / "qa"

V1_PATH = FEATURES_DIR / "urban_mobility_features_citywide.parquet"
V2_PATH = FEATURES_DIR / "urban_mobility_features_citywide_v2.parquet"

NEW_ROAD_COLS = ["road_length_m", "major_road_length_m", "local_road_length_m", "walkable_road_length_m",
                 "cycle_accessible_road_length_m", "road_density_km_per_km2", "intersection_count",
                 "intersection_density_km2"]
NEW_LANDUSE_COLS = ["green_area_m2", "green_area_ratio", "residential_area_ratio", "commercial_area_ratio",
                     "retail_area_ratio", "industrial_area_ratio", "landuse_data_coverage_pct"]
NEW_ROAD_GRADE_COLS = ["mean_absolute_road_grade_pct", "median_absolute_road_grade_pct",
                        "pct_road_length_grade_gt_5pct", "pct_road_length_grade_gt_8pct", "road_grade_sample_length_m"]
NEW_CYCLING_OVERLAP_COLS = ["pct_road_network_with_cycle_infrastructure"]
ALL_NEW_COLS = NEW_ROAD_COLS + NEW_LANDUSE_COLS + NEW_ROAD_GRADE_COLS + NEW_CYCLING_OVERLAP_COLS
ROAD_FAMILY_INTERNAL = NEW_ROAD_COLS + NEW_ROAD_GRADE_COLS + NEW_CYCLING_OVERLAP_COLS

EXISTING_TRANSIT_URBANFORM_CYCLING = [
    "building_count", "mean_building_footprint_m2", "building_footprint_area_m2", "building_coverage_ratio",
    "metro_station_count", "tram_station_count", "rail_station_count", "metrobus_station_count", "bus_stop_count",
    "ferry_terminal_count", "total_transit_stop_count", "distance_to_nearest_metro_m", "distance_to_nearest_tram_m",
    "distance_to_nearest_rail_m", "distance_to_nearest_metrobus_m", "distance_to_nearest_bus_stop_m",
    "distance_to_nearest_ferry_m", "distance_to_nearest_transit_m", "transit_stops_within_500m",
    "transit_stops_within_1000m", "bus_stops_within_500m", "fixed_guideway_stations_within_1000m",
    "number_of_transit_modes_accessible", "routes_serving_grid", "unique_bus_routes", "unique_rail_lines",
    "bus_departures_per_day", "bus_departures_peak_hour",
    "cycle_infrastructure_length_km_ibb_only", "cycle_infrastructure_density_km_per_km2_ibb_only",
    "protected_cycleway_length_km_ibb_only", "protected_cycleway_density_km_per_km2_ibb_only",
    "distance_to_nearest_cycle_infrastructure_m_ibb_only", "distance_to_nearest_bicycle_parking_m",
    "bicycle_parking_count", "distance_to_nearest_micromobility_parking_m", "micromobility_parking_count",
]
EXISTING_POI_POPULATION_BUILDING = [
    "hospital_count", "university_count", "school_count", "healthcare_count", "cafe_count", "restaurant_count",
    "bar_pub_count", "supermarket_count", "retail_count", "office_count", "tourism_count", "leisure_count",
    "total_poi_count", "poi_density_km2", "poi_category_count", "poi_entropy",
    "population_worldpop_raw", "population_density_worldpop_raw_km2", "population_calibrated",
    "population_density_calibrated_km2",
    "building_count", "mean_building_footprint_m2", "building_footprint_area_m2", "building_coverage_ratio",
]

REDUNDANCY_THRESHOLD = 0.90


def schema_impact(v1: pd.DataFrame, v2: pd.DataFrame) -> dict:
    id_geom_cols = {"grid_id", "district", "cell_area_m2", "land_area_m2", "geometry"}
    v1_predictors = set(v1.columns) - id_geom_cols
    v2_predictors = set(v2.columns) - id_geom_cols
    pending = {"road_grade_status", "pct_road_network_with_cycle_infrastructure_status"}
    added = v2_predictors - v1_predictors
    removed = v1_predictors - v2_predictors
    shared = v1_predictors & v2_predictors
    return {
        "n_v1_predictors": len(v1_predictors),
        "n_v2_predictors": len(v2_predictors),
        "n_added": len(added),
        "n_resolved_from_pending": len(removed & pending),
        "n_removed_non_pending": len(removed - pending),
        "added_columns": sorted(added),
        "removed_columns": sorted(removed),
        "n_shared_unchanged_columns": len(shared),
    }


def existing_feature_integrity(v1: pd.DataFrame, v2: pd.DataFrame) -> dict:
    id_geom_cols = {"grid_id", "district", "cell_area_m2", "land_area_m2", "geometry"}
    pending = {"road_grade_status", "pct_road_network_with_cycle_infrastructure_status"}
    shared_cols = (set(v1.columns) & set(v2.columns)) - id_geom_cols - pending
    v1i = v1.set_index("grid_id")
    v2i = v2.set_index("grid_id")
    mismatches = {}
    for col in sorted(shared_cols):
        s1, s2 = v1i[col], v2i.loc[v1i.index, col]
        if pd.api.types.is_numeric_dtype(s1):
            diff = (s1 - s2).abs()
            n_diff = int((diff > 1e-9).sum())
        else:
            n_diff = int((s1.astype(str) != s2.astype(str)).sum())
        if n_diff:
            mismatches[col] = n_diff
    return {"n_shared_columns_checked": len(shared_cols), "n_columns_with_any_difference": len(mismatches),
            "columns_with_differences": mismatches,
            "status": "IDENTICAL" if not mismatches else "UNEXPECTED_DIFFERENCES_FOUND"}


def distribution_stats(df: pd.DataFrame, cols: list[str]) -> dict:
    out = {}
    n = len(df)
    for col in cols:
        s = df[col]
        n_missing = int(s.isna().sum())
        valid = s.dropna()
        n_zero = int((valid == 0).sum())
        desc = {
            "n_missing": n_missing, "pct_missing": round(n_missing / n * 100, 3),
            "n_zero": n_zero, "pct_zero": round(n_zero / n * 100, 3) if n else None,
        }
        if len(valid) > 1 and valid.nunique() > 1:
            desc.update({
                "min": float(valid.min()), "median": float(valid.median()), "mean": float(valid.mean()),
                "p90": float(valid.quantile(0.90)), "p99": float(valid.quantile(0.99)), "max": float(valid.max()),
                "skewness": float(scipy_stats.skew(valid.to_numpy())),
            })
        else:
            desc.update({"min": None, "median": None, "mean": None, "p90": None, "p99": None, "max": None, "skewness": None})
        out[col] = desc
    return out


def district_coverage(df: pd.DataFrame, cols: list[str]) -> dict:
    out = {}
    for col in cols:
        by_d = df.groupby("district")[col].agg(
            n_zero_or_null=lambda s: int((s.isna() | (s == 0)).sum()), n_cells="size",
            total=lambda s: float(s.fillna(0).sum()),
        )
        by_d["pct_zero_or_null"] = (by_d["n_zero_or_null"] / by_d["n_cells"] * 100).round(2)
        city_total = float(df[col].fillna(0).sum())
        by_d["pct_of_citywide_total"] = (by_d["total"] / city_total * 100).round(2) if city_total else 0.0
        fully_zero_districts = by_d[by_d["pct_zero_or_null"] >= 99.9].index.tolist()
        max_concentration = by_d["pct_of_citywide_total"].max()
        out[col] = {
            "n_districts_fully_zero_or_null": len(fully_zero_districts),
            "districts_fully_zero_or_null": fully_zero_districts,
            "max_single_district_share_of_citywide_total_pct": float(max_concentration) if pd.notna(max_concentration) else None,
            "district_with_max_share": by_d["pct_of_citywide_total"].idxmax() if city_total else None,
            "concentration_flag": "SUSPICIOUS_SINGLE_DISTRICT_DOMINANCE" if pd.notna(max_concentration) and max_concentration > 40 else "ok",
        }
    return out


def redundancy_block(df: pd.DataFrame, group_a: list[str], group_b: list[str], label: str) -> dict:
    corr = df[group_a + group_b].corr(method="spearman")
    flagged = []
    for a in group_a:
        for b in group_b:
            if a == b:
                continue
            rho = corr.loc[a, b]
            if pd.notna(rho) and abs(rho) >= REDUNDANCY_THRESHOLD:
                flagged.append({"feature_a": a, "feature_b": b, "spearman_rho": round(float(rho), 4)})
    flagged.sort(key=lambda r: -abs(r["spearman_rho"]))
    return {"label": label, "n_pairs_tested": len(group_a) * len(group_b), "n_flagged_ge_0.90": len(flagged), "flagged_pairs": flagged}


def redundancy_internal(df: pd.DataFrame, cols: list[str], label: str) -> dict:
    corr = df[cols].corr(method="spearman")
    flagged = []
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            rho = corr.loc[a, b]
            if pd.notna(rho) and abs(rho) >= REDUNDANCY_THRESHOLD:
                flagged.append({"feature_a": a, "feature_b": b, "spearman_rho": round(float(rho), 4)})
    flagged.sort(key=lambda r: -abs(r["spearman_rho"]))
    return {"label": label, "n_pairs_tested": len(cols) * (len(cols) - 1) // 2, "n_flagged_ge_0.90": len(flagged), "flagged_pairs": flagged}


def scaling_risk(df: pd.DataFrame, cols: list[str]) -> dict:
    out = {}
    for col in cols:
        s = df[col].dropna()
        if len(s) == 0:
            continue
        n = len(s)
        pct_zero = float((s == 0).mean() * 100)
        median = float(s.median())
        q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
        iqr = q3 - q1
        nonzero = s[s != 0]
        nonzero_iqr = float(nonzero.quantile(0.75) - nonzero.quantile(0.25)) if len(nonzero) > 1 else None

        if iqr > 0:
            robust_scaled = (s - median) / iqr
            max_abs_scaled = float(robust_scaled.abs().max())
        else:
            max_abs_scaled = float("inf")

        risk_flags = []
        if pct_zero >= 40:
            risk_flags.append("LARGE_EXACT_ZERO_MASS")
        if nonzero_iqr is not None and nonzero_iqr > 0 and iqr > 0 and (nonzero_iqr / iqr) < 0.05:
            risk_flags.append("TINY_NONZERO_IQR_RELATIVE_TO_FULL_IQR")
        if iqr == 0:
            risk_flags.append("ZERO_IQR_UNDEFINED_ROBUSTSCALER")
        elif max_abs_scaled > 20:
            risk_flags.append("EXTREME_ROBUSTSCALER_MAGNITUDE")
        skewness = float(scipy_stats.skew(s.to_numpy())) if s.nunique() > 1 else 0.0
        if abs(skewness) > 3:
            risk_flags.append("HIGH_SKEW")

        out[col] = {
            "n": n, "pct_zero": round(pct_zero, 2), "median": median, "iqr": iqr, "nonzero_iqr": nonzero_iqr,
            "max_abs_robustscaler_value": max_abs_scaled if max_abs_scaled != float("inf") else "inf",
            "skewness": round(skewness, 3), "risk_flags": risk_flags,
        }
    return out


def main() -> None:
    print("=" * 72)
    print("Phase 7B: V1 -> V2 impact audit")
    print("=" * 72)

    v1 = gpd.read_parquet(V1_PATH)
    v2 = gpd.read_parquet(V2_PATH)

    print("\n[1/5] Schema impact...")
    schema = schema_impact(v1, v2)
    print(f"  V1 predictors: {schema['n_v1_predictors']}  V2 predictors: {schema['n_v2_predictors']}  "
          f"added: {schema['n_added']}  resolved_from_pending: {schema['n_resolved_from_pending']}")

    print("\n[2/5] Existing-feature integrity...")
    integrity = existing_feature_integrity(v1, v2)
    print(f"  {integrity['status']}: {integrity['n_shared_columns_checked']} shared columns checked, "
          f"{integrity['n_columns_with_any_difference']} with differences")

    print("\n[3/5] New-family distributions + district coverage...")
    dist = distribution_stats(v2, ALL_NEW_COLS)
    coverage = district_coverage(v2, ALL_NEW_COLS)

    print("\n[4/5] Redundancy audit (Spearman, |rho| >= 0.90)...")
    redundancy = {
        "new_road_vs_existing_transit_urbanform_cycling": redundancy_block(
            v2, NEW_ROAD_COLS + NEW_ROAD_GRADE_COLS + NEW_CYCLING_OVERLAP_COLS, EXISTING_TRANSIT_URBANFORM_CYCLING,
            "new road-family features vs existing transit/urban-form/cycling"),
        "new_landuse_vs_existing_poi_population_building": redundancy_block(
            v2, NEW_LANDUSE_COLS, EXISTING_POI_POPULATION_BUILDING,
            "new land-use features vs existing POI/population/building"),
        "road_internal": redundancy_internal(v2, ROAD_FAMILY_INTERNAL, "road-family features internally"),
        "landuse_internal": redundancy_internal(v2, NEW_LANDUSE_COLS, "land-use features internally"),
    }
    for k, r in redundancy.items():
        print(f"  {k}: {r['n_flagged_ge_0.90']}/{r['n_pairs_tested']} pairs flagged")

    print("\n[5/5] Scaling-risk audit...")
    scaling = scaling_risk(v2, ALL_NEW_COLS)
    n_flagged = sum(1 for v in scaling.values() if v["risk_flags"])
    print(f"  {n_flagged}/{len(scaling)} new features carry at least one scaling-risk flag")

    report = {
        "schema_impact": schema,
        "existing_feature_integrity": integrity,
        "new_feature_distributions": dist,
        "new_feature_district_coverage": coverage,
        "redundancy_audit": redundancy,
        "scaling_risk_audit": scaling,
    }

    out_path = QA_DIR / "phase7b_impact_audit.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[save] {out_path}")


if __name__ == "__main__":
    main()
