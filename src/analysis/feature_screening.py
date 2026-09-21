"""Phase 5A: feature screening for the unsupervised typology.

Candidate features are drawn broadly from every required family (activity/
POI, urban form, population, transit/accessibility, cycling, terrain), then
pruned quantitatively:
  1. Redundancy: pairwise Spearman correlation (robust to skew/nonlinearity);
     for any pair with |rho| > REDUNDANCY_THRESHOLD, the less-aggregate /
     less-interpretable member is dropped (count-vs-density pairs keep the
     density; a raw sub-category kept only if it is NOT redundant with the
     aggregate it rolls up into).
  2. Skew: any surviving feature with |skewness| > SKEW_THRESHOLD gets a
     log1p transform (ratios/percentages already bounded [0,1] are exempt —
     log1p on a bounded ratio is not a meaningful stabilizing transform).
  3. Scale: RobustScaler (median/IQR) — chosen over StandardScaler because
     several features (POI counts, cycling infrastructure density) have
     heavy-tailed distributions where a few genuinely high cells would
     otherwise dominate a mean/std-based scaling.

We deliberately exclude population_worldpop_raw / population_density_worldpop_raw_km2
from clustering: Phase 4 designated population_calibrated as primary, and
including both raw and calibrated versions would be pure redundancy by
construction (same spatial pattern, rescaled).
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import skew
from sklearn.preprocessing import RobustScaler

REDUNDANCY_THRESHOLD = 0.85
SKEW_THRESHOLD = 1.0

# Ratios/percentages/entropy are already bounded and not log-transformed.
BOUNDED_FEATURES = {
    "poi_entropy", "building_coverage_ratio", "green_area_ratio", "residential_area_ratio",
    "commercial_area_ratio", "retail_area_ratio", "industrial_area_ratio",
    "pct_road_network_with_cycle_infrastructure", "mean_slope_deg",
}

# When a redundant pair is found, prefer the LEFT member of the tuple
# (kept) over the RIGHT (candidate for dropping) — encodes "prefer the
# area-normalized / aggregate form over the raw count" as a documented rule,
# not an ad hoc per-pair judgment call.
PREFERRED_OVER = [
    ("poi_density_km2", "total_poi_count"),
    ("building_coverage_ratio", "building_count"),
    ("building_coverage_ratio", "building_footprint_area_m2"),
    ("road_density_km_per_km2", "road_length_m"),
    ("intersection_density_km2", "intersection_count"),
    ("cycle_infrastructure_density_km_per_km2", "cycle_infrastructure_length_km"),
    ("protected_cycleway_density_km_per_km2", "protected_cycleway_length_km"),
    ("population_density_calibrated_km2", "population_calibrated"),
]

CANDIDATE_FEATURES = [
    # activity / POI
    "poi_density_km2", "total_poi_count", "poi_category_count", "poi_entropy",
    "retail_count", "office_count", "restaurant_count", "cafe_count", "bar_pub_count",
    "healthcare_count", "hospital_count", "school_count", "university_count",
    "tourism_count", "leisure_count", "supermarket_count",
    # urban form / land use
    "building_count", "building_coverage_ratio", "building_footprint_area_m2", "mean_building_footprint_m2",
    "road_density_km_per_km2", "road_length_m", "intersection_density_km2", "intersection_count",
    "green_area_ratio", "residential_area_ratio", "commercial_area_ratio", "retail_area_ratio", "industrial_area_ratio",
    # population
    "population_calibrated", "population_density_calibrated_km2",
    # transit / accessibility
    "distance_to_nearest_transit_m", "transit_stops_within_500m", "number_of_transit_modes_accessible",
    "distance_to_nearest_metro_m", "distance_to_nearest_bus_stop_m", "bus_departures_per_day", "routes_serving_grid",
    # cycling
    "cycle_infrastructure_density_km_per_km2", "cycle_infrastructure_length_km",
    "protected_cycleway_density_km_per_km2", "protected_cycleway_length_km",
    "distance_to_nearest_cycle_infrastructure_m", "pct_road_network_with_cycle_infrastructure",
    "bicycle_parking_count", "distance_to_nearest_bicycle_parking_m",
    # terrain
    "mean_elevation_m", "mean_slope_deg", "pct_area_slope_gt_10deg",
]


def screen_redundancy(df: pd.DataFrame, candidates: list[str]) -> tuple[list[str], dict]:
    corr = df[candidates].corr(method="spearman").abs()
    dropped = {}
    for keep, drop in PREFERRED_OVER:
        if keep in candidates and drop in candidates and drop not in dropped:
            rho = corr.loc[keep, drop]
            if rho > REDUNDANCY_THRESHOLD:
                dropped[drop] = {"redundant_with": keep, "spearman_rho": round(float(rho), 3)}

    remaining = [c for c in candidates if c not in dropped]
    # General sweep: any remaining pair still above threshold, drop the
    # second-listed one (arbitrary but deterministic tie-break by list order).
    corr_r = df[remaining].corr(method="spearman").abs()
    for i, a in enumerate(remaining):
        for b in remaining[i + 1:]:
            if b in dropped:
                continue
            rho = corr_r.loc[a, b]
            if rho > REDUNDANCY_THRESHOLD:
                dropped[b] = {"redundant_with": a, "spearman_rho": round(float(rho), 3)}

    final = [c for c in candidates if c not in dropped]
    diagnostics = {"n_candidates": len(candidates), "n_dropped_redundant": len(dropped), "dropped_features": dropped, "n_final": len(final)}
    return final, diagnostics


def apply_transform_and_scale(df: pd.DataFrame, features: list[str]) -> tuple[pd.DataFrame, dict]:
    transformed = df[features].copy()
    log_applied = {}
    for f in features:
        if f in BOUNDED_FEATURES:
            continue
        s = float(skew(transformed[f].dropna()))
        if abs(s) > SKEW_THRESHOLD:
            transformed[f] = np.log1p(transformed[f].clip(lower=0))
            log_applied[f] = round(s, 3)

    scaler = RobustScaler()
    scaled = pd.DataFrame(scaler.fit_transform(transformed), columns=features, index=df.index)

    diagnostics = {"n_log1p_transformed": len(log_applied), "log1p_applied_to": log_applied, "skew_threshold": SKEW_THRESHOLD}
    return scaled, diagnostics


def build_clustering_matrix(features_df: gpd.GeoDataFrame) -> tuple[pd.DataFrame, list[str], dict]:
    available = [c for c in CANDIDATE_FEATURES if c in features_df.columns]
    final_features, redundancy_diag = screen_redundancy(features_df, available)
    scaled, transform_diag = apply_transform_and_scale(features_df, final_features)
    diagnostics = {"redundancy_screening": redundancy_diag, "transform_and_scale": transform_diag, "final_feature_list": final_features}
    return scaled, final_features, diagnostics
