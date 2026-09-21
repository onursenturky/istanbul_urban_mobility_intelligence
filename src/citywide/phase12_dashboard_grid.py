"""Phase 12, Section 5 (+ part of 23): the parsimonious dashboard-ready
grid dataset and its geometry exports. Pulls ONLY interpretable fields
from already-frozen sources -- no new computation, no recomputed
indicator, no dump of the full ~94-predictor V2 feature table.
"""

from __future__ import annotations

import json

import geopandas as gpd
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

ROOT = cfg.PROJECT_ROOT
OUT_DIR = ROOT / "analysis" / "framework_synthesis"
DASH_DIR = OUT_DIR / "dashboard"
GAP_DIR = ROOT / "analysis" / "applications" / "accessibility_gap_intelligence"
MCDA_DIR = ROOT / "analysis" / "mcda_v2" / "phase6b"
SIMPLIFY_TOLERANCE_M = 5.0  # metric CRS units (meters); grid cells are 500m squares, so this is a ~1% tolerance


def main() -> None:
    print("=" * 72)
    print("Phase 12 Section 5/23: dashboard grid data model + geometry exports")
    print("=" * 72)

    print("\n[1/4] Loading the Phase 11 synthesis table (the single richest frozen source) + geometry...")
    synth = pd.read_parquet(GAP_DIR / "accessibility_gap_grid_synthesis.parquet")
    # readiness_consensus_class / opportunity_consensus_class already joined into the Phase 11
    # synthesis table -- reused here, not re-merged.
    v2_urban = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet",
                                columns=["grid_id", "intersection_density_km2", "cycle_infrastructure_density_km_per_km2_ibb_only"])
    grid_geom = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")[["grid_id", "geometry"]]

    print("\n[2/4] Assembling the parsimonious presentation layer (grouped, not all ~94 predictors)...")
    df = synth.merge(v2_urban, on="grid_id", how="left")
    df["population_density_per_km2"] = (df["population_calibrated"] / 0.25).round(1)

    dashboard = pd.DataFrame({
        # IDENTITY
        "grid_id": df["grid_id"], "district": df["district"], "calibrated_population_2020": df["population_calibrated"],
        # URBAN CONTEXT
        "typology_cluster": df["cluster"], "population_density_per_km2": df["population_density_per_km2"],
        "intersection_density_km2": df["intersection_density_km2"],
        "cycle_infrastructure_density_km_per_km2": df["cycle_infrastructure_density_km_per_km2_ibb_only"],
        # WALKING
        "food_walk_min": df["walk_food_nearest_min"], "healthcare_walk_min": df["walk_healthcare_nearest_min"],
        "education_walk_min": df["walk_education_nearest_min"],
        "required_categories_walk_15": df["walk_required_categories_accessible_15min"],
        "complete_walk_15": df["WALKING_COMPLETE_15MIN_ACCESS"],
        # CYCLING
        "food_cycle_min": df["cycle_food_nearest_min"], "healthcare_cycle_min": df["cycle_healthcare_nearest_min"],
        "education_cycle_min": df["cycle_education_nearest_min"],
        "required_categories_cycle_15": df["cycling_required_categories_accessible_15min"],
        "complete_cycle_15": df["CYCLING_COMPLETE_15MIN_ACCESS"], "cycle_only_everyday_gain": df["CYCLE_ONLY_GAIN"],
        # TRANSIT
        "general_transit_walk_min": df["walk_general_transit_nearest_min"], "general_transit_cycle_min": df["cycle_general_transit_nearest_min"],
        "fixed_transit_walk_min": df["walk_fixed_transit_nearest_min"], "fixed_transit_cycle_min": df["cycle_fixed_transit_nearest_min"],
        "cycle_only_transit_gain": df["CYCLE_ONLY_TRANSIT_GAIN"],
        # GAPS
        "everyday_gap_type": df["everyday_gap_class"], "cycling_gap_closure": df["cycling_closure_status"],
        "transit_gap_type": df["transit_access_gap_class"], "multi_domain_pattern": df["multi_domain_class"],
        "active_mobility_intervention": df["intervention_class"],
        # E-BIKE
        "ebike_readiness": df["ebike_readiness"], "ebike_opportunity": df["ebike_opportunity"],
        "ebike_readiness_robustness": df["readiness_consensus_class"], "ebike_opportunity_robustness": df["opportunity_consensus_class"],
        # QUALITY
        "walking_quality": df["walking_quality_flag"], "cycling_quality": df["cycling_quality_flag"],
        "transit_data_quality": df["transit_data_quality_class"], "synthesis_reliable": df["strict_synthesis_reliable"],
    })
    print(f"  dashboard_grid: {len(dashboard)} rows, {len(dashboard.columns)} columns "
          f"(vs {len([c for c in df.columns])} available synthesis columns and ~94 V2 predictors -- deliberately parsimonious)")
    dashboard.to_parquet(DASH_DIR / "dashboard_grid.parquet")
    print(f"[save] {DASH_DIR / 'dashboard_grid.parquet'}")

    print("\n[3/4] Geometry export (GeoJSON, WGS84, simplified for web use -- analytical geometry untouched)...")
    geo = grid_geom.merge(dashboard, on="grid_id", how="inner").to_crs("EPSG:4326")
    geo_simplified = geo.copy()
    geo_simplified["geometry"] = geo_simplified.to_crs(cfg.METRIC_CRS).geometry.simplify(SIMPLIFY_TOLERANCE_M).to_crs("EPSG:4326")
    # datetime/object columns must be JSON-serializable; booleans/NaN are fine for GeoJSON via geopandas
    geo_path = DASH_DIR / "dashboard_grid.geojson"
    geo_simplified.to_file(geo_path, driver="GeoJSON", COORDINATE_PRECISION=6)
    size_mb = geo_path.stat().st_size / 1e6
    print(f"  geometry simplification: Douglas-Peucker tolerance={SIMPLIFY_TOLERANCE_M}m in EPSG:32635 (~1% of the 500m cell "
          f"edge) applied ONLY to this presentation export -- analytical source geometry in "
          f"data/processed/citywide/mobility_grid_500m_metric.gpkg is NEVER modified.")
    print(f"[save] {geo_path} ({size_mb:.1f} MB)")

    # Explicitly required by spec: "If GeoJSON becomes excessively large, also produce a
    # simplified visualization version while preserving the analytical grid ID."
    LITE_TOLERANCE_M = 20.0
    lite_cols = ["grid_id", "district", "calibrated_population_2020", "typology_cluster",
                 "complete_walk_15", "complete_cycle_15", "cycle_only_everyday_gain", "cycle_only_transit_gain",
                 "everyday_gap_type", "cycling_gap_closure", "transit_gap_type", "multi_domain_pattern",
                 "active_mobility_intervention", "ebike_readiness_robustness", "ebike_opportunity_robustness",
                 "walking_quality", "cycling_quality", "transit_data_quality", "synthesis_reliable", "geometry"]
    geo_lite = grid_geom.merge(dashboard, on="grid_id", how="inner").to_crs("EPSG:4326")
    geo_lite["geometry"] = geo_lite.to_crs(cfg.METRIC_CRS).geometry.simplify(LITE_TOLERANCE_M).to_crs("EPSG:4326")
    geo_lite = geo_lite[lite_cols]
    lite_path = DASH_DIR / "dashboard_grid_lite.geojson"
    geo_lite.to_file(lite_path, driver="GeoJSON", COORDINATE_PRECISION=5)
    lite_size_mb = lite_path.stat().st_size / 1e6
    print(f"  [lite export] {len(lite_cols)-1} columns (map-legend fields only), "
          f"{LITE_TOLERANCE_M}m simplification, 5-decimal coordinate precision")
    print(f"[save] {lite_path} ({lite_size_mb:.1f} MB)")

    print("\n[4/4] District summary (dashboard-ready, descriptive, NOT a ranking)...")
    district_gap_summary = pd.read_csv(GAP_DIR / "district_accessibility_gap_summary.csv")
    district_transit_quality = pd.read_csv(ROOT / "analysis" / "applications" / "first_last_mile_transit" / "transit_district_quality.csv")[
        ["district", "transit_data_quality_class"]].drop_duplicates()
    typ_composition = dashboard.groupby(["district", "typology_cluster"]).size().unstack(fill_value=0)
    typ_composition.columns = [f"n_cells_cluster_{c}" for c in typ_composition.columns]
    dist_summary = district_gap_summary.merge(typ_composition.reset_index(), on="district", how="left")
    dist_summary.to_parquet(DASH_DIR / "dashboard_district_summary.parquet")
    print(f"  {len(dist_summary)} districts summarized")
    print(f"[save] {DASH_DIR / 'dashboard_district_summary.parquet'}")

    export_diag = {
        "dashboard_grid_rows": len(dashboard), "dashboard_grid_columns": len(dashboard.columns),
        "dashboard_grid_parquet_size_mb": round((DASH_DIR / "dashboard_grid.parquet").stat().st_size / 1e6, 2),
        "dashboard_grid_geojson_size_mb": round(size_mb, 2),
        "dashboard_grid_lite_geojson_size_mb": round(lite_size_mb, 2),
        "lite_geometry_simplification_tolerance_m": LITE_TOLERANCE_M,
        "geometry_simplification_tolerance_m": SIMPLIFY_TOLERANCE_M,
        "geometry_simplification_applies_to": "Presentation GeoJSON export ONLY -- never the analytical grid geometry.",
        "district_summary_rows": len(dist_summary),
        "columns_by_group": {
            "IDENTITY": ["grid_id", "district", "calibrated_population_2020"],
            "URBAN_CONTEXT": ["typology_cluster", "population_density_per_km2", "intersection_density_km2", "cycle_infrastructure_density_km_per_km2"],
            "WALKING": ["food_walk_min", "healthcare_walk_min", "education_walk_min", "required_categories_walk_15", "complete_walk_15"],
            "CYCLING": ["food_cycle_min", "healthcare_cycle_min", "education_cycle_min", "required_categories_cycle_15", "complete_cycle_15", "cycle_only_everyday_gain"],
            "TRANSIT": ["general_transit_walk_min", "general_transit_cycle_min", "fixed_transit_walk_min", "fixed_transit_cycle_min", "cycle_only_transit_gain"],
            "GAPS": ["everyday_gap_type", "cycling_gap_closure", "transit_gap_type", "multi_domain_pattern", "active_mobility_intervention"],
            "EBIKE": ["ebike_readiness", "ebike_opportunity", "ebike_readiness_robustness", "ebike_opportunity_robustness"],
            "QUALITY": ["walking_quality", "cycling_quality", "transit_data_quality", "synthesis_reliable"],
        },
    }
    (DASH_DIR / "_dashboard_export_diagnostics.json").write_text(json.dumps(export_diag, indent=2, default=str), encoding="utf-8")
    print(f"[save] {DASH_DIR / '_dashboard_export_diagnostics.json'} (intermediate)")


if __name__ == "__main__":
    main()
