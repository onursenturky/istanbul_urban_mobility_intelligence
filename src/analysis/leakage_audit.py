"""Phase 4 leakage audit: classify every current predictor.

Three categories:
  - safe_predictor: describes the built/natural environment, independent of
    any shared-mobility operator or user decision.
  - potential_leakage: plausibly explanatory for USAGE demand, but risks
    circularity/reverse-causality if the eventual target is operator
    DEPLOYMENT (siting) decisions, since operators explicitly consider
    existing cycling infrastructure and parking when placing stations.
  - target_derived_prohibited: computed directly from shared-mobility
    supply/usage data. NONE currently exist — Phase 3E deliberately kept
    all shared-mobility data out of the predictor table, so this category
    is empty by design, not by oversight.
"""

from __future__ import annotations

import pandas as pd

# Explicit — not inferred from name patterns, since these are exactly the
# features flagged in the phase instructions for extra scrutiny.
POTENTIAL_LEAKAGE = {
    "cycle_infrastructure_length_km": "Cycling-specific infrastructure; safe as a usage-demand explanatory variable, but an operator plausibly sites deployments where this is already high (reverse-causality risk if target = deployment).",
    "cycle_infrastructure_density_km_per_km2": "Same as cycle_infrastructure_length_km.",
    "protected_cycleway_length_km": "Same reasoning, protected-facility subset.",
    "protected_cycleway_density_km_per_km2": "Same reasoning, protected-facility subset.",
    "distance_to_nearest_cycle_infrastructure_m": "Same reasoning — proximity to infrastructure an operator also uses when siting.",
    "pct_road_network_with_cycle_infrastructure": "Same reasoning.",
    "bicycle_parking_count": "Bicycle parking can co-locate with informal shared-bike drop zones; higher leakage risk than lane infrastructure if target = deployment.",
    "distance_to_nearest_bicycle_parking_m": "Same reasoning as bicycle_parking_count.",
}

FAMILY_RATIONALE = {
    "poi": "Point-of-interest counts/density/diversity describe the built environment's activity mix — independent of any bike-share operator or user decision.",
    "building": "Building footprint/coverage describes urban form, unrelated to shared-mobility decisions.",
    "road_network": "Physical general-purpose road network (length/density/intersections/class) predates and is independent of any shared-mobility system.",
    "greenspace_landuse": "Green space and land-use composition describe environment/zoning, not mobility-operator behavior.",
    "transit": "Public-transport supply (metro/tram/rail/bus/ferry stations, distances, service intensity) is set by transit agencies independently of any bike-share operator's decisions.",
    "population": "Residential population is a demographic exposure measure, unrelated to shared-mobility supply decisions.",
    "terrain": "Elevation/slope/road-grade are physical terrain properties, fixed regardless of any mobility system.",
}


def _classify_family(feature: str) -> str:
    poi_cols = {"bar_pub_count","cafe_count","healthcare_count","hospital_count","leisure_count","office_count",
                "restaurant_count","retail_count","school_count","supermarket_count","tourism_count",
                "university_count","total_poi_count","poi_density_km2","poi_category_count","poi_entropy"}
    building_cols = {"building_count","mean_building_footprint_m2","building_footprint_area_m2","building_coverage_ratio"}
    road_cols = {"road_length_m","major_road_length_m","local_road_length_m","walkable_road_length_m",
                 "cycle_accessible_road_length_m","intersection_count","road_density_km_per_km2","intersection_density_km2"}
    green_cols = {"green_area_m2","green_area_ratio","residential_area_ratio","commercial_area_ratio",
                  "retail_area_ratio","industrial_area_ratio","landuse_data_coverage_pct"}
    transit_cols = {"metro_station_count","tram_station_count","rail_station_count","metrobus_station_count",
                    "bus_stop_count","ferry_terminal_count","total_transit_stop_count",
                    "distance_to_nearest_metro_m","distance_to_nearest_tram_m","distance_to_nearest_rail_m",
                    "distance_to_nearest_metrobus_m","distance_to_nearest_bus_stop_m","distance_to_nearest_ferry_m",
                    "distance_to_nearest_transit_m","transit_stops_within_500m","transit_stops_within_1000m",
                    "bus_stops_within_500m","fixed_guideway_stations_within_1000m","rail_stations_within_1000m",
                    "number_of_transit_modes_accessible","routes_serving_grid","unique_bus_routes",
                    "unique_rail_lines","bus_departures_per_day","bus_departures_peak_hour"}
    population_cols = {"population","population_density_km2","population_worldpop_raw",
                        "population_density_worldpop_raw_km2","population_calibrated","population_density_calibrated_km2"}
    terrain_cols = {"mean_elevation_m","median_elevation_m","min_elevation_m","max_elevation_m","elevation_std_m",
                     "elevation_range_m","mean_slope_deg","median_slope_deg","max_slope_deg","slope_std_deg",
                     "pct_area_slope_lt_3deg","pct_area_slope_3_6deg","pct_area_slope_6_10deg","pct_area_slope_gt_10deg",
                     "n_valid_dem_pixels","mean_absolute_road_grade_pct","median_absolute_road_grade_pct",
                     "pct_road_length_grade_gt_5pct","pct_road_length_grade_gt_8pct","road_grade_sample_length_m"}

    if feature in poi_cols: return "poi"
    if feature in building_cols: return "building"
    if feature in road_cols: return "road_network"
    if feature in green_cols: return "greenspace_landuse"
    if feature in transit_cols: return "transit"
    if feature in population_cols: return "population"
    if feature in terrain_cols: return "terrain"
    return "cycling_infrastructure"  # the 8 POTENTIAL_LEAKAGE features


def build_leakage_audit(feature_columns: list[str]) -> pd.DataFrame:
    rows = []
    for feature in feature_columns:
        family = _classify_family(feature)
        if feature in POTENTIAL_LEAKAGE:
            category = "potential_leakage"
            rationale = POTENTIAL_LEAKAGE[feature]
        else:
            category = "safe_predictor"
            rationale = FAMILY_RATIONALE[family]
        rows.append({
            "feature_name": feature,
            "predictor_family": family,
            "category": category,
            "rationale": rationale,
        })
    df = pd.DataFrame(rows)
    return df
