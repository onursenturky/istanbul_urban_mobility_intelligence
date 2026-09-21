"""Phase 6B-V2: E-bike Readiness & Opportunity baseline scoring.

First application built on the CITYWIDE_V2_EIGHT_FAMILY_FEATURE_BASELINE /
CITYWIDE_V2_EIGHT_FAMILY_TYPOLOGY core data foundation. No new datasets, no
new predictors, no typology modification, no V1 modification, no MCDA
architecture expansion -- this finalizes/validates the e-bike application
using the Phase 6A-V2 decisions only.

Five conceptual dimensions (deliberately NOT the same as V1's 5 -- V1's
"Urban Form" (has_buildings/building_coverage) dimension is NOT part of
this leaner e-bike-specific model, per the explicit 5-dimension list in
the governing instruction; Urban Form data remains in the V2 feature store
for other future applications):
  A. Demand/Activity        -- unchanged from V1 (5 criteria)
  B. Transit Accessibility  -- REDUCED representation (4 criteria; the 5
                                mode-specific distances are sensitivity-only)
  C. Cycling Readiness      -- unchanged from V1 (5 criteria, İBB-only)
  D. Street Connectivity    -- NEW (3 criteria)
  E. Physical Feasibility   -- V1's 3 terrain criteria SUPPLEMENTED (not
                                replaced) by mean_absolute_road_grade_pct

Readiness = renormalized weighted mean of {B, C, D, E} (Demand excluded --
Readiness represents enabling conditions, not demand).
Opportunity = demand_potential ** alpha * cycling_gap ** (1 - alpha),
alpha = weight(Demand) / (weight(Demand) + weight(Cycling Readiness)) from
the ORIGINAL 5-dimension vector -- the same geometric, zero-forcing form
used in V1's Phase 6B, unchanged because no evidence was found to justify
changing it.

No single combined "suitability" score is ever computed. Typology cluster
membership is NEVER used as a predictor -- only in post-hoc interpretation
(see mcda_phase6b_v2_typology.py).
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import rankdata

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

FEATURES_DIR = cfg.DATA_FEATURES
MCDA_V2_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda_v2"
OUT_DIR = MCDA_V2_DIR / "phase6b"

GRADE_COMFORTABLE_PCT = 3.0
GRADE_STEEP_PCT = 10.0
GRADE_FLOOR = 0.5
SLOPE_COMFORTABLE_DEG = 3.0
SLOPE_STEEP_DEG = 10.0
SLOPE_FLOOR = 0.5

BASELINE_DIMENSION_WEIGHTS = {
    "Demand/Activity": 0.20, "Transit Accessibility": 0.20, "Cycling Readiness": 0.20,
    "Street Connectivity": 0.20, "Physical Feasibility": 0.20,
}

TERRAIN_WEIGHTS_WITH_GRADE = {"mean_slope_deg": 0.40, "mean_absolute_road_grade_pct": 0.30,
                              "pct_area_slope_6_10deg": 0.20, "pct_area_slope_3_6deg": 0.10}
TERRAIN_WEIGHTS_NO_GRADE = {"mean_slope_deg": 0.60, "pct_area_slope_6_10deg": 0.25, "pct_area_slope_3_6deg": 0.15}

REQUIRED_COLS = [
    "grid_id", "district", "geometry", "land_area_m2",
    "poi_density_km2", "poi_entropy", "retail_count", "leisure_count", "population_density_calibrated_km2",
    "distance_to_nearest_transit_m", "transit_stops_within_500m", "bus_departures_per_day",
    "fixed_guideway_stations_within_1000m",
    "distance_to_nearest_metro_m", "distance_to_nearest_tram_m", "distance_to_nearest_rail_m",
    "distance_to_nearest_ferry_m", "distance_to_nearest_metrobus_m",
    "cycle_infrastructure_density_km_per_km2_ibb_only", "protected_cycleway_density_km_per_km2_ibb_only",
    "distance_to_nearest_cycle_infrastructure_m_ibb_only", "distance_to_nearest_bicycle_parking_m",
    "distance_to_nearest_micromobility_parking_m", "pct_road_network_with_cycle_infrastructure",
    "intersection_density_km2", "local_road_length_m", "cycle_accessible_road_length_m",
    "mean_slope_deg", "pct_area_slope_3_6deg", "pct_area_slope_6_10deg",
    "mean_absolute_road_grade_pct", "pct_road_length_grade_gt_8pct",
    "road_density_km_per_km2",
]


# --------------------------------------------------------------------------
# Value-function primitives (identical semantics to V1's Phase 6B library --
# see src/citywide/mcda_phase6b_scoring.py; reproduced here rather than
# imported to keep this application module self-contained and because two
# functions have V2-specific parameters (grade thresholds)).
# --------------------------------------------------------------------------

def pct_rank(x: pd.Series) -> np.ndarray:
    """rankdata(method='min'), not 'average' -- a large tied-zero mass must
    map to percentile ~0, not an inflated tie-averaged value. Same fix
    applied throughout this project (Phase 5C building coverage, Phase 6B
    V1 criteria)."""
    return (rankdata(x, method="min") - 1) / (len(x) - 1)


def saturating_benefit(x: pd.Series) -> np.ndarray:
    return pct_rank(x) ** 0.5


def linear_benefit(x: pd.Series) -> np.ndarray:
    return pct_rank(x)


def saturating_cost(x: pd.Series) -> np.ndarray:
    return (1 - pct_rank(x)) ** 0.5


def piecewise_cost(x: np.ndarray, comfortable: float, steep: float, floor: float) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    v = np.ones_like(x)
    mid = (x > comfortable) & (x <= steep)
    v[mid] = 1.0 - (x[mid] - comfortable) / (steep - comfortable) * (1.0 - floor)
    v[x > steep] = floor
    return v


def share_cost_floor(x: pd.Series, floor: float = SLOPE_FLOOR) -> np.ndarray:
    return 1.0 - (x.to_numpy(dtype=float) / 100.0) * (1.0 - floor)


def masked_weighted_mean(value_cols: dict[str, np.ndarray], weights: dict[str, float]) -> np.ndarray:
    """Weighted mean across columns, renormalizing weights PER ROW over
    only the non-NaN columns for that row -- used for mean_absolute_road_grade_pct
    (NaN for the 12.6% of roadless cells), so a missing road-grade value
    never gets silently treated as 0 (best) or the worst case; it is simply
    excluded from that row's average and the remaining weights rescale to
    sum to 1 for that row."""
    names = list(value_cols.keys())
    mat = np.column_stack([value_cols[n] for n in names])
    w = np.array([weights[n] for n in names])
    valid = ~np.isnan(mat)
    w_row = valid * w[np.newaxis, :]
    row_sum = w_row.sum(axis=1)
    mat_filled = np.where(valid, mat, 0.0)
    return (mat_filled * w_row).sum(axis=1) / row_sum


def load_data() -> gpd.GeoDataFrame:
    df = gpd.read_parquet(FEATURES_DIR / "urban_mobility_features_citywide_v2.parquet", columns=REQUIRED_COLS)
    assert len(df) == 22322 and df["grid_id"].is_unique
    # Re-derive exactly as engineered in phase5a_v2_screening.py (not persisted
    # in the V2 master table itself, only in the Phase 5A-V2 reduced matrix).
    df["cycle_accessible_road_density_km_per_km2"] = df["cycle_accessible_road_length_m"] / 1000 / (df["land_area_m2"] / 1e6)
    return df


def compute_demand(df: pd.DataFrame) -> tuple[pd.Series, list[dict]]:
    vf_records = []
    parts = {}
    for f in ["poi_density_km2", "retail_count", "leisure_count", "population_density_calibrated_km2"]:
        parts[f] = saturating_benefit(df[f])
        vf_records.append({"feature_name": f, "dimension": "Demand/Activity", "value_function": "percentile_rank ** 0.5 (saturating benefit)", "evidence_status": "ASSUMPTION-DRIVEN (functional shape); direction evidence-backed"})
    parts["poi_entropy"] = linear_benefit(df["poi_entropy"])
    vf_records.append({"feature_name": "poi_entropy", "dimension": "Demand/Activity", "value_function": "percentile_rank (linear benefit)", "evidence_status": "ASSUMPTION-DRIVEN"})
    demand = pd.DataFrame(parts).mean(axis=1)
    return demand, vf_records


def compute_transit(df: pd.DataFrame) -> tuple[pd.Series, list[dict]]:
    vf_records = []
    parts = {"distance_to_nearest_transit_m": saturating_cost(df["distance_to_nearest_transit_m"])}
    vf_records.append({"feature_name": "distance_to_nearest_transit_m", "dimension": "Transit Accessibility", "value_function": "(1 - percentile_rank(distance)) ** 0.5 -- closer=better", "evidence_status": "ASSUMPTION-DRIVEN (functional shape)"})
    for f in ["transit_stops_within_500m", "bus_departures_per_day", "fixed_guideway_stations_within_1000m"]:
        parts[f] = saturating_benefit(df[f])
        vf_records.append({"feature_name": f, "dimension": "Transit Accessibility", "value_function": "percentile_rank ** 0.5 (saturating benefit)", "evidence_status": "ASSUMPTION-DRIVEN"})
    transit = pd.DataFrame(parts).mean(axis=1)
    return transit, vf_records


def compute_transit_expanded(df: pd.DataFrame) -> pd.Series:
    """EXPANDED_TRANSIT sensitivity variant: V1's original 9-criterion
    Transit Context (T1_integration value functions), for direct comparison
    against the reduced 4-criterion baseline."""
    parts = {}
    for f in ["distance_to_nearest_metro_m", "distance_to_nearest_tram_m", "distance_to_nearest_rail_m",
              "distance_to_nearest_ferry_m", "distance_to_nearest_metrobus_m", "distance_to_nearest_transit_m"]:
        parts[f] = saturating_cost(df[f])
    for f in ["transit_stops_within_500m", "fixed_guideway_stations_within_1000m", "bus_departures_per_day"]:
        parts[f] = saturating_benefit(df[f])
    return pd.DataFrame(parts).mean(axis=1)


def compute_cycling(df: pd.DataFrame, primary_infra_col: str) -> tuple[pd.Series, pd.Series, list[dict]]:
    """Returns (readiness, gap, records). primary_infra_col swaps between
    cycle_infrastructure_density_km_per_km2_ibb_only (baseline) and
    pct_road_network_with_cycle_infrastructure (ALTERNATIVE_CYCLING variant)."""
    vf_records = []
    parts = {}
    cyc_dist_feats = ["distance_to_nearest_cycle_infrastructure_m_ibb_only", "distance_to_nearest_bicycle_parking_m",
                       "distance_to_nearest_micromobility_parking_m"]
    for f in cyc_dist_feats:
        parts[f] = saturating_cost(df[f])
        vf_records.append({"feature_name": f, "dimension": "Cycling Readiness", "value_function": "(1 - percentile_rank(distance)) ** 0.5", "evidence_status": "ASSUMPTION-DRIVEN"})
    parts["protected_cycleway_density_km_per_km2_ibb_only"] = saturating_benefit(df["protected_cycleway_density_km_per_km2_ibb_only"])
    vf_records.append({"feature_name": "protected_cycleway_density_km_per_km2_ibb_only", "dimension": "Cycling Readiness", "value_function": "percentile_rank ** 0.5", "evidence_status": "ASSUMPTION-DRIVEN"})

    if primary_infra_col == "cycle_infrastructure_density_km_per_km2_ibb_only":
        parts[primary_infra_col] = saturating_benefit(df[primary_infra_col])
        vf_records.append({"feature_name": primary_infra_col, "dimension": "Cycling Readiness", "value_function": "percentile_rank ** 0.5 (PRIMARY infrastructure representation, per Phase 6A-V2)", "evidence_status": "ASSUMPTION-DRIVEN (shape); representation choice evidence-backed (see Phase 6A-V2 audit)"})
        valid = pd.Series(True, index=df.index)
        infra_val = parts[primary_infra_col]
    else:
        # pct_road_network_with_cycle_infrastructure: NaN for 12.6% roadless cells
        valid = df[primary_infra_col].notna()
        infra_val = np.full(len(df), np.nan)
        infra_val[valid.to_numpy()] = saturating_benefit(df.loc[valid, primary_infra_col])
        parts[primary_infra_col] = infra_val
        vf_records.append({"feature_name": primary_infra_col, "dimension": "Cycling Readiness (ALTERNATIVE_CYCLING sensitivity variant)", "value_function": "percentile_rank ** 0.5 among cells with road present; NaN (excluded from row mean) for roadless cells", "evidence_status": "ASSUMPTION-DRIVEN"})

    df_parts = pd.DataFrame(parts)
    readiness = df_parts.mean(axis=1, skipna=True)
    gap_parts = 1 - df_parts
    gap = gap_parts.mean(axis=1, skipna=True)
    return readiness, gap, vf_records


def compute_street_connectivity(df: pd.DataFrame) -> tuple[pd.Series, list[dict]]:
    vf_records = []
    parts = {
        "intersection_density_km2": saturating_benefit(df["intersection_density_km2"]),
        "local_road_length_m": saturating_benefit(df["local_road_length_m"]),
        "cycle_accessible_road_density_km_per_km2": linear_benefit(df["cycle_accessible_road_density_km_per_km2"]),
    }
    vf_records.append({"feature_name": "intersection_density_km2", "dimension": "Street Connectivity", "value_function": "percentile_rank ** 0.5 (saturating benefit)", "evidence_status": "ASSUMPTION-DRIVEN (shape); direction evidence-backed (Phase 6A-V2)"})
    vf_records.append({"feature_name": "local_road_length_m", "dimension": "Street Connectivity", "value_function": "percentile_rank ** 0.5 (saturating benefit)", "evidence_status": "ASSUMPTION-DRIVEN (shape); direction evidence-backed"})
    vf_records.append({"feature_name": "cycle_accessible_road_density_km_per_km2", "dimension": "Street Connectivity", "value_function": "percentile_rank (linear benefit, per Phase 6A-V2 'monotonic benefit' proposal)", "evidence_status": "EVIDENCE-BACKED (direct definitional relevance)"})
    street = pd.DataFrame(parts).mean(axis=1)
    return street, vf_records


def compute_terrain(df: pd.DataFrame, include_grade: bool) -> tuple[pd.Series, list[dict]]:
    vf_records = []
    slope_val = piecewise_cost(df["mean_slope_deg"].to_numpy(), SLOPE_COMFORTABLE_DEG, SLOPE_STEEP_DEG, SLOPE_FLOOR)
    band_6_10 = share_cost_floor(df["pct_area_slope_6_10deg"])
    band_3_6 = share_cost_floor(df["pct_area_slope_3_6deg"])
    vf_records.append({"feature_name": "mean_slope_deg", "dimension": "Physical Feasibility", "value_function": f"piecewise: 1.0 <={SLOPE_COMFORTABLE_DEG}deg, linear decline to floor {SLOPE_FLOOR} by {SLOPE_STEEP_DEG}deg (frozen pilot thresholds)", "evidence_status": "ASSUMPTION-DRIVEN (thresholds reused from pilot, not re-derived)"})
    vf_records.append({"feature_name": "pct_area_slope_6_10deg", "dimension": "Physical Feasibility", "value_function": "share-cost, floor 0.5 at 100% share", "evidence_status": "ASSUMPTION-DRIVEN"})
    vf_records.append({"feature_name": "pct_area_slope_3_6deg", "dimension": "Physical Feasibility", "value_function": "share-cost, floor 0.5 at 100% share", "evidence_status": "ASSUMPTION-DRIVEN"})

    if include_grade:
        grade_val = piecewise_cost(df["mean_absolute_road_grade_pct"].to_numpy(), GRADE_COMFORTABLE_PCT, GRADE_STEEP_PCT, GRADE_FLOOR)
        grade_val = np.where(df["mean_absolute_road_grade_pct"].isna(), np.nan, grade_val)
        vf_records.append({"feature_name": "mean_absolute_road_grade_pct", "dimension": "Physical Feasibility", "value_function": f"piecewise: 1.0 <={GRADE_COMFORTABLE_PCT}%, linear decline to floor {GRADE_FLOOR} by {GRADE_STEEP_PCT}% (grade thresholds reused from the pilot's raster-slope convention, NOT independently derived for road grade)", "evidence_status": "ASSUMPTION-DRIVEN (thresholds AND their reuse across two different physical quantities are both assumptions)"})
        terrain = masked_weighted_mean(
            {"mean_slope_deg": slope_val, "mean_absolute_road_grade_pct": grade_val,
             "pct_area_slope_6_10deg": band_6_10, "pct_area_slope_3_6deg": band_3_6},
            TERRAIN_WEIGHTS_WITH_GRADE)
    else:
        terrain = (TERRAIN_WEIGHTS_NO_GRADE["mean_slope_deg"] * slope_val
                   + TERRAIN_WEIGHTS_NO_GRADE["pct_area_slope_6_10deg"] * band_6_10
                   + TERRAIN_WEIGHTS_NO_GRADE["pct_area_slope_3_6deg"] * band_3_6)
    return pd.Series(terrain, index=df.index), vf_records


def compute_readiness(dims: dict[str, pd.Series], dim_weights: dict[str, float]) -> pd.Series:
    """Renormalized weighted mean of all dimensions EXCEPT Demand/Activity."""
    readiness_dims = [d for d in dim_weights if d != "Demand/Activity"]
    w_sum = sum(dim_weights[d] for d in readiness_dims)
    readiness = sum((dim_weights[d] / w_sum) * dims[d] for d in readiness_dims)
    return readiness


def compute_opportunity(demand: pd.Series, cycling_gap: pd.Series, dim_weights: dict[str, float]) -> tuple[pd.Series, float]:
    alpha = dim_weights["Demand/Activity"] / (dim_weights["Demand/Activity"] + dim_weights["Cycling Readiness"])
    opp = (demand.to_numpy() ** alpha) * (cycling_gap.to_numpy() ** (1 - alpha))
    return pd.Series(opp, index=demand.index), alpha


def main() -> None:
    print("=" * 72)
    print("Phase 6B-V2: E-bike Readiness & Opportunity baseline scoring")
    print("=" * 72)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_data()
    print(f"\nLoaded V2 master table: {len(df)} cells")

    print("\n[1/4] Computing baseline dimension scores...")
    demand, vf_demand = compute_demand(df)
    transit, vf_transit = compute_transit(df)
    cycling_readiness, cycling_gap, vf_cycling = compute_cycling(df, "cycle_infrastructure_density_km_per_km2_ibb_only")
    street, vf_street = compute_street_connectivity(df)
    terrain, vf_terrain = compute_terrain(df, include_grade=True)

    dims_baseline = {"Demand/Activity": demand, "Transit Accessibility": transit,
                      "Cycling Readiness": cycling_readiness, "Street Connectivity": street,
                      "Physical Feasibility": terrain}
    for name, s in dims_baseline.items():
        assert s.between(0, 1).all(), f"{name} out of [0,1] bounds"
    print("  all 5 baseline dimension scores verified in [0,1]")

    dim_scores_df = pd.DataFrame({"grid_id": df["grid_id"], "district": df["district"], **dims_baseline})
    dim_scores_df.to_parquet(OUT_DIR / "ebike_dimension_scores.parquet")
    print(f"  saved {OUT_DIR / 'ebike_dimension_scores.parquet'}")

    all_vf_records = vf_demand + vf_transit + vf_cycling + vf_street + vf_terrain
    pd.DataFrame(all_vf_records).to_csv(OUT_DIR / "criterion_value_functions_v2.csv", index=False)
    print(f"  saved criterion_value_functions_v2.csv ({len(all_vf_records)} rows)")

    print("\n[2/4] Baseline Readiness...")
    readiness = compute_readiness(dims_baseline, BASELINE_DIMENSION_WEIGHTS)
    assert readiness.between(0, 1).all()
    readiness_df = gpd.GeoDataFrame({"grid_id": df["grid_id"], "district": df["district"],
                                       "ebike_readiness": readiness, "geometry": df["geometry"]}, crs=cfg.METRIC_CRS)
    readiness_df.to_parquet(OUT_DIR / "ebike_readiness_baseline.parquet")
    print(f"  readiness range=[{readiness.min():.4f},{readiness.max():.4f}] mean={readiness.mean():.4f} median={readiness.median():.4f}")
    print(f"  saved {OUT_DIR / 'ebike_readiness_baseline.parquet'}")

    print("\n[3/4] Baseline Opportunity...")
    opportunity, alpha = compute_opportunity(demand, cycling_gap, BASELINE_DIMENSION_WEIGHTS)
    assert opportunity.between(0, 1).all()
    opportunity_df = gpd.GeoDataFrame({"grid_id": df["grid_id"], "district": df["district"],
                                        "ebike_opportunity": opportunity, "demand_potential": demand,
                                        "cycling_gap": cycling_gap, "geometry": df["geometry"]}, crs=cfg.METRIC_CRS)
    opportunity_df.to_parquet(OUT_DIR / "ebike_opportunity_baseline.parquet")
    print(f"  alpha (demand share of demand+cycling)={alpha:.3f}")
    print(f"  opportunity range=[{opportunity.min():.4f},{opportunity.max():.4f}] mean={opportunity.mean():.4f} median={opportunity.median():.4f}")
    print(f"  n_cells opportunity==0: {(opportunity==0).sum()} ({(opportunity==0).mean()*100:.1f}%)")
    print(f"  saved {OUT_DIR / 'ebike_opportunity_baseline.parquet'}")

    print("\n[4/4] Distribution / spatial plausibility check...")
    by_district_r = readiness_df.groupby("district")["ebike_readiness"].mean().sort_values(ascending=False)
    by_district_o = opportunity_df.groupby("district")["ebike_opportunity"].mean().sort_values(ascending=False)
    print("  top 5 districts by mean readiness:", by_district_r.head(5).round(3).to_dict())
    print("  top 5 districts by mean opportunity:", by_district_o.head(5).round(3).to_dict())

    baseline_meta = {
        "dimensions": list(BASELINE_DIMENSION_WEIGHTS.keys()),
        "dimension_weights_baseline": BASELINE_DIMENSION_WEIGHTS,
        "terrain_weights_with_grade": TERRAIN_WEIGHTS_WITH_GRADE,
        "readiness_formula": "renormalized weighted mean of {Transit Accessibility, Cycling Readiness, Street "
                             "Connectivity, Physical Feasibility}; Demand/Activity excluded (Readiness = enabling "
                             "conditions, not demand)",
        "opportunity_formula": "demand_potential ** alpha * cycling_gap ** (1 - alpha); "
                               f"alpha = {alpha:.4f} = weight(Demand)/(weight(Demand)+weight(Cycling Readiness)) "
                               "from the ORIGINAL 5-dim vector, unchanged geometric form from V1",
        "cycling_gap_definition": "mean of (1 - value) across the same 5 Cycling Readiness criteria used for "
                                  "readiness -- NOT a separately defined gap concept",
        "urban_form_dimension_excluded": "V1's Urban Form dimension (has_buildings / building_coverage_ratio) "
                                         "is NOT part of this 5-dimension e-bike model, per the explicit "
                                         "governing 5-dimension list. Retained in the V2 feature store for "
                                         "future applications; not silently dropped from the data.",
        "readiness_stats": {"min": float(readiness.min()), "max": float(readiness.max()), "mean": float(readiness.mean()), "median": float(readiness.median()), "std": float(readiness.std())},
        "opportunity_stats": {"min": float(opportunity.min()), "max": float(opportunity.max()), "mean": float(opportunity.mean()), "median": float(opportunity.median()), "std": float(opportunity.std()), "pct_zero": round(float((opportunity==0).mean()*100), 2)},
    }
    (OUT_DIR / "baseline_scoring_meta.json").write_text(json.dumps(baseline_meta, indent=2, default=str), encoding="utf-8")
    print(f"\n[save] {OUT_DIR / 'baseline_scoring_meta.json'}")


if __name__ == "__main__":
    main()
