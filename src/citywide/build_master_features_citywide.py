"""Citywide master feature table -- merges the six COMPLETED feature
families (buildings, POIs, population, terrain elevation/slope, transit,
cycling İBB-only) onto the canonical 22,322-cell / 39-district grid.

Deliberately EXCLUDED (still incomplete): land-use/green (PARTIAL, 22/39
districts), the full OSM road network (PARTIAL, 0/39 districts), any
road-grade feature (depends on the road network), and
pct_road_network_with_cycle_infrastructure (same dependency). Where a
family carries an explicit pending-status column for one of these
(road_grade_status, pct_road_network_with_cycle_infrastructure_status),
that STATUS column is preserved in the master table -- it documents the
dependency, it is not itself a numeric predictor.

Join discipline: the canonical grid is the LEFT table; every family joins
by grid_id only, and every join is verified not to change the row count
(a family's per-cell coverage gaps show up as NaN in that family's own
columns, never as a dropped or duplicated grid row).

No normalization, weighting, ranking, clustering, PCA, or composite index
is computed here -- this is strictly a clean, documented, QA'd predictor
table.

Outputs:
  data/processed/citywide/features/urban_mobility_features_citywide.parquet
  data/processed/citywide/qa/master_feature_qa.json
  data/processed/citywide/metadata/feature_dictionary_citywide.csv
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

FEATURES_DIR = cfg.DATA_PROCESSED / "features"
QA_DIR = cfg.DATA_PROCESSED / "qa"
META_DIR = cfg.DATA_PROCESSED / "metadata"

N_EXPECTED_CELLS = 22322
N_EXPECTED_DISTRICTS = 39

METADATA_COLS = ["grid_id", "district", "cell_area_m2", "land_area_m2"]

# --------------------------------------------------------------------------
# Per-family predictor column lists (explicit -- never "everything except
# grid_id/district/geometry", so a stray/duplicate column can never sneak
# into the master table unnoticed).
# --------------------------------------------------------------------------

BUILDING_COLS = ["building_count", "mean_building_footprint_m2", "building_footprint_area_m2", "building_coverage_ratio"]

POI_COLS = [
    "hospital_count", "university_count", "school_count", "healthcare_count", "cafe_count",
    "restaurant_count", "bar_pub_count", "supermarket_count", "retail_count", "office_count",
    "tourism_count", "leisure_count", "total_poi_count", "poi_density_km2", "poi_category_count", "poi_entropy",
]

# "population" / "population_density_km2" are exact duplicates of
# population_worldpop_raw / population_density_worldpop_raw_km2 (the
# calibration step's rename-alias pattern) -- excluded here to avoid a
# duplicate-column pair in the master table.
POPULATION_COLS = [
    "population_worldpop_raw", "population_density_worldpop_raw_km2",
    "population_calibrated", "population_density_calibrated_km2",
]

TERRAIN_COLS = [
    "mean_elevation_m", "median_elevation_m", "min_elevation_m", "max_elevation_m",
    "elevation_std_m", "elevation_range_m", "mean_slope_deg", "median_slope_deg",
    "max_slope_deg", "slope_std_deg", "pct_area_slope_lt_3deg", "pct_area_slope_3_6deg",
    "pct_area_slope_6_10deg", "pct_area_slope_gt_10deg", "n_valid_dem_pixels", "road_grade_status",
]

TRANSIT_COLS = [
    "metro_station_count", "tram_station_count", "rail_station_count", "metrobus_station_count",
    "bus_stop_count", "ferry_terminal_count", "total_transit_stop_count",
    "distance_to_nearest_metro_m", "distance_to_nearest_tram_m", "distance_to_nearest_rail_m",
    "distance_to_nearest_metrobus_m", "distance_to_nearest_bus_stop_m", "distance_to_nearest_ferry_m",
    "distance_to_nearest_transit_m", "transit_stops_within_500m", "transit_stops_within_1000m",
    "bus_stops_within_500m", "fixed_guideway_stations_within_1000m", "rail_stations_within_1000m",
    "number_of_transit_modes_accessible", "routes_serving_grid", "unique_bus_routes", "unique_rail_lines",
    "bus_departures_per_day", "bus_departures_peak_hour",
]

CYCLING_COLS = [
    "cycle_infrastructure_length_km_ibb_only", "cycle_infrastructure_density_km_per_km2_ibb_only",
    "protected_cycleway_length_km_ibb_only", "protected_cycleway_density_km_per_km2_ibb_only",
    "distance_to_nearest_cycle_infrastructure_m_ibb_only", "distance_to_nearest_bicycle_parking_m",
    "bicycle_parking_count", "distance_to_nearest_micromobility_parking_m", "micromobility_parking_count",
    "pct_road_network_with_cycle_infrastructure_status",
]

FAMILIES = {
    "buildings": {"path": FEATURES_DIR / "building_features_citywide.geojson", "cols": BUILDING_COLS},
    "poi": {"path": FEATURES_DIR / "poi_features_citywide.parquet", "cols": POI_COLS},
    "population": {"path": FEATURES_DIR / "population_features_citywide.parquet", "cols": POPULATION_COLS},
    "terrain": {"path": FEATURES_DIR / "terrain_features_citywide.parquet", "cols": TERRAIN_COLS},
    "transit": {"path": FEATURES_DIR / "transit_features_citywide.parquet", "cols": TRANSIT_COLS},
    "cycling": {"path": FEATURES_DIR / "cycling_features_citywide.parquet", "cols": CYCLING_COLS},
}

STATUS_COLS = {"road_grade_status", "pct_road_network_with_cycle_infrastructure_status"}


def load_family(path) -> gpd.GeoDataFrame:
    return gpd.read_file(path) if str(path).endswith(".geojson") else gpd.read_parquet(path)


def main() -> None:
    print("=" * 72)
    print("Citywide master feature table (6 completed families)")
    print("=" * 72)

    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == N_EXPECTED_CELLS
    assert grid["grid_id"].is_unique
    assert grid["district"].nunique() == N_EXPECTED_DISTRICTS

    master = grid[METADATA_COLS + ["geometry"]].copy()
    join_coverage = {}
    district_coverage = {}

    for name, spec in FAMILIES.items():
        print(f"\n[join] {name}: {spec['path'].name}")
        fam = load_family(spec["path"])
        assert len(fam) == N_EXPECTED_CELLS, f"{name}: expected {N_EXPECTED_CELLS} rows, got {len(fam)}"
        assert fam["grid_id"].is_unique, f"{name}: grid_id not unique"
        missing_from_fam = set(grid["grid_id"]) - set(fam["grid_id"])
        assert not missing_from_fam, f"{name}: missing {len(missing_from_fam)} grid_ids present in canonical grid"
        assert fam["district"].nunique() == N_EXPECTED_DISTRICTS, f"{name}: does not cover 39 districts"

        missing_cols = [c for c in spec["cols"] if c not in fam.columns]
        assert not missing_cols, f"{name}: expected columns not found: {missing_cols}"

        n_before = len(master)
        master = master.merge(fam[["grid_id"] + spec["cols"]], on="grid_id", how="left", validate="one_to_one")
        assert len(master) == n_before, f"{name}: row count changed after join ({n_before} -> {len(master)})"
        assert master["grid_id"].is_unique

        numeric_cols_in_family = [c for c in spec["cols"] if c not in STATUS_COLS]
        n_matched = int(master[numeric_cols_in_family[0]].notna().sum()) if numeric_cols_in_family else len(master)
        join_coverage[name] = {"n_cells_matched": n_matched, "pct_matched": round(n_matched / N_EXPECTED_CELLS * 100, 2)}
        district_coverage[name] = int(fam["district"].nunique())
        print(f"  joined {len(spec['cols'])} columns, {n_matched}/{N_EXPECTED_CELLS} cells matched ({join_coverage[name]['pct_matched']}%)")

    assert len(master) == N_EXPECTED_CELLS
    assert master["grid_id"].is_unique
    assert master["district"].nunique() == N_EXPECTED_DISTRICTS
    assert not master.columns.duplicated().any(), "duplicate column names in master table"

    print(f"\nMaster table: {len(master)} rows x {len(master.columns)} columns")

    # --------------------------------------------------------------------
    # Master QA
    # --------------------------------------------------------------------
    predictor_cols = [c for c in master.columns if c not in METADATA_COLS + ["geometry"]]
    numeric_predictor_cols = [c for c in predictor_cols if pd.api.types.is_numeric_dtype(master[c])]
    status_predictor_cols = [c for c in predictor_cols if c in STATUS_COLS]

    null_counts = {c: int(master[c].isna().sum()) for c in predictor_cols}
    inf_counts = {c: int(np.isinf(master[c]).sum()) for c in numeric_predictor_cols}
    n_with_inf = {c: n for c, n in inf_counts.items() if n > 0}

    constant_cols = [c for c in numeric_predictor_cols if master[c].nunique(dropna=True) <= 1]

    zero_prevalence = {
        c: round(float((master[c] == 0).mean() * 100), 2)
        for c in numeric_predictor_cols
    }
    high_zero_prevalence = {c: v for c, v in zero_prevalence.items() if v > 90}

    outlier_ranges = {}
    for c in numeric_predictor_cols:
        vals = master[c].replace([np.inf, -np.inf], np.nan).dropna()
        if len(vals) == 0:
            continue
        outlier_ranges[c] = {"min": round(float(vals.min()), 4), "max": round(float(vals.max()), 4), "mean": round(float(vals.mean()), 4)}

    n_duplicate_ids = int(master["grid_id"].duplicated().sum())
    n_duplicate_columns = int(master.columns.duplicated().sum())

    qa = {
        "n_rows": len(master),
        "n_rows_expected": N_EXPECTED_CELLS,
        "row_count_correct": len(master) == N_EXPECTED_CELLS,
        "n_unique_grid_ids": int(master["grid_id"].nunique()),
        "grid_id_uniqueness_correct": int(master["grid_id"].nunique()) == N_EXPECTED_CELLS,
        "n_districts": int(master["district"].nunique()),
        "district_count_correct": int(master["district"].nunique()) == N_EXPECTED_DISTRICTS,
        "n_duplicate_ids": n_duplicate_ids,
        "n_duplicate_columns": n_duplicate_columns,
        "n_predictor_columns": len(predictor_cols),
        "n_numeric_predictor_columns": len(numeric_predictor_cols),
        "n_status_columns": len(status_predictor_cols),
        "status_columns": status_predictor_cols,
        "null_counts_by_feature": {c: n for c, n in null_counts.items() if n > 0},
        "n_features_with_any_null": int(sum(1 for n in null_counts.values() if n > 0)),
        "infinite_value_counts_by_feature": n_with_inf,
        "constant_columns": constant_cols,
        "zero_prevalence_pct_by_feature": zero_prevalence,
        "features_over_90pct_zero": high_zero_prevalence,
        "outlier_ranges_by_feature": outlier_ranges,
        "join_coverage_by_family": join_coverage,
        "district_coverage_by_family": district_coverage,
        "n_columns_total": len(master.columns),
    }

    out_dir = FEATURES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "urban_mobility_features_citywide.parquet"
    master.to_parquet(out_path)
    print(f"\n[save] {out_path}")

    QA_DIR.mkdir(parents=True, exist_ok=True)
    qa_path = QA_DIR / "master_feature_qa.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {qa_path}")

    build_feature_dictionary(predictor_cols)

    print("\n--- SUMMARY ---")
    print(f"Rows: {qa['n_rows']} (expected {N_EXPECTED_CELLS}) -- {'OK' if qa['row_count_correct'] else 'MISMATCH'}")
    print(f"Unique grid_ids: {qa['n_unique_grid_ids']} -- {'OK' if qa['grid_id_uniqueness_correct'] else 'MISMATCH'}")
    print(f"Districts: {qa['n_districts']} -- {'OK' if qa['district_count_correct'] else 'MISMATCH'}")
    print(f"Predictor columns: {qa['n_predictor_columns']} ({qa['n_numeric_predictor_columns']} numeric, {qa['n_status_columns']} status)")
    print(f"Duplicate columns: {n_duplicate_columns}, duplicate IDs: {n_duplicate_ids}")
    print(f"Features with any null: {qa['n_features_with_any_null']}")
    print(f"Features with infinite values: {len(n_with_inf)}")
    print(f"Constant columns: {constant_cols}")
    print(f"Features >90% zero: {list(high_zero_prevalence.keys())}")
    print(f"Join coverage by family: {join_coverage}")
    print(f"District coverage by family: {district_coverage}")


# --------------------------------------------------------------------------
# Feature dictionary
# --------------------------------------------------------------------------

def build_feature_dictionary(predictor_cols: list[str]) -> None:
    rows = []

    def add(name, family, definition, unit, source, ref_year, completeness, zero_meaningful, limitation, classification):
        rows.append({
            "feature_name": name, "feature_family": family, "definition": definition, "unit": unit,
            "source": source, "source_reference_year": ref_year, "completeness_status": completeness,
            "zero_is_meaningful": zero_meaningful, "known_limitation": limitation, "classification": classification,
        })

    # --- Buildings ---
    add("building_count", "buildings", "Number of OSM building footprints assigned to this cell (representative-point membership)", "count", "OpenStreetMap (2026-09-18)", 2026, "COMPLETE", True, "OSM building completeness varies by area; not independently verified against a cadastral source", "READY")
    add("mean_building_footprint_m2", "buildings", "Mean footprint area of buildings assigned to this cell", "m^2", "OpenStreetMap (2026-09-18)", 2026, "COMPLETE", False, "0 for a zero-building cell is a FILLED PLACEHOLDER for a mathematically undefined mean (empty set), not a real building of zero size -- always check building_count before interpreting this value as a real average", "READY_WITH_LIMITATION")
    add("building_footprint_area_m2", "buildings", "Total building footprint area clipped to this cell (true intersection, not representative-point)", "m^2", "OpenStreetMap (2026-09-18)", 2026, "COMPLETE", True, "Same OSM completeness caveat as building_count", "READY")
    add("building_coverage_ratio", "buildings", "building_footprint_area_m2 / cell land area", "ratio", "OpenStreetMap (2026-09-18)", 2026, "COMPLETE", True, "Values >1.0 possible only from overlapping/duplicate source footprints; 0 confirmed in citywide QA", "READY")

    # --- POI ---
    poi_defs = {
        "hospital_count": "amenity=hospital or healthcare=hospital", "university_count": "amenity=university",
        "school_count": "amenity=school", "healthcare_count": "outpatient/primary care (clinic, doctors, dentist, pharmacy), excludes hospital",
        "cafe_count": "amenity=cafe", "restaurant_count": "amenity=restaurant or fast_food",
        "bar_pub_count": "amenity in (bar, pub, biergarten)", "supermarket_count": "shop=supermarket",
        "retail_count": "any other shop=* value", "office_count": "office=*", "tourism_count": "tourism=*", "leisure_count": "leisure=*",
    }
    for col, defn in poi_defs.items():
        add(col, "poi", f"Count of POIs matching: {defn} (12-category mutually exclusive classification)", "count", "OpenStreetMap (2026-09-18)", 2026, "COMPLETE", True, "OSM POI tagging completeness varies by area; 25,479 raw POIs did not match any of the 12 categories and were dropped by design", "READY")
    add("total_poi_count", "poi", "Sum of all 12 POI category counts", "count", "OpenStreetMap (2026-09-18)", 2026, "COMPLETE", True, "Sum of the above categories only, not a raw OSM POI count", "READY")
    add("poi_density_km2", "poi", "total_poi_count / cell land area", "count/km^2", "OpenStreetMap (2026-09-18)", 2026, "COMPLETE", True, None, "READY")
    add("poi_category_count", "poi", "Number of distinct POI categories (of 12) present in this cell", "count (0-12)", "OpenStreetMap (2026-09-18)", 2026, "COMPLETE", True, None, "READY")
    add("poi_entropy", "poi", "Shannon entropy (bits) of the POI category distribution within this cell", "bits", "OpenStreetMap (2026-09-18)", 2026, "COMPLETE", True, "0 for a cell with a single category or zero POIs -- not distinguishable from each other by this value alone", "READY")

    # --- Population ---
    add("population_worldpop_raw", "population", "Raw WorldPop-allocated population (area-weighted pixel-to-grid, no calibration)", "people", "WorldPop constrained UN-adjusted 2020", 2020, "COMPLETE", True, "Reference year 2020, 5-6 years older than OSM/GTFS sources; residential population only", "READY_WITH_LIMITATION")
    add("population_density_worldpop_raw_km2", "population", "population_worldpop_raw / cell land area", "people/km^2", "WorldPop constrained UN-adjusted 2020", 2020, "COMPLETE", True, "Same as population_worldpop_raw", "READY_WITH_LIMITATION")
    add("population_calibrated", "population", "population_worldpop_raw rescaled per district via official 2020 TÜİK ADNKS totals (three-way pixel x grid x district overlay)", "people", "WorldPop 2020 + TÜİK ADNKS 2020 (via İBB Nüfus Bilgileri)", 2020, "COMPLETE (all 39 districts calibrated)", True, "Calibration corrects district totals only; within-district spatial pattern still follows WorldPop's dasymetric model, which may itself be imperfect", "READY_WITH_LIMITATION")
    add("population_density_calibrated_km2", "population", "population_calibrated / cell land area", "people/km^2", "WorldPop 2020 + TÜİK ADNKS 2020", 2020, "COMPLETE", True, "Same as population_calibrated", "READY_WITH_LIMITATION")

    # --- Terrain ---
    elev_defs = {
        "mean_elevation_m": "mean", "median_elevation_m": "median", "min_elevation_m": "minimum",
        "max_elevation_m": "maximum", "elevation_std_m": "standard deviation", "elevation_range_m": "max - min",
    }
    for col, stat in elev_defs.items():
        add(col, "terrain", f"{stat.capitalize()} elevation across valid DEM pixel centers falling in this cell", "m (EGM2008 geoid)", "Copernicus DEM GLO-30", "2011-2015 (release 2019-2021)", "COMPLETE", False if col != "elevation_std_m" else "N/A", "TanDEM-X SAR-derived, <4m LE90 vertical accuracy; small negative values near water are a known SAR-DEM artifact, not an error", "READY")
    slope_defs = {"mean_slope_deg": "mean", "median_slope_deg": "median", "max_slope_deg": "maximum", "slope_std_deg": "standard deviation"}
    for col, stat in slope_defs.items():
        add(col, "terrain", f"{stat.capitalize()} Horn's-method slope across valid DEM pixels in this cell", "degrees", "Copernicus DEM GLO-30", "2011-2015", "COMPLETE", True, "Terrain slope, distinct from road-grade (segment-level) or e-bike-adjusted slope suitability (both defined in Phase 4/5 methodology, not here)", "READY")
    for col, rng in [("pct_area_slope_lt_3deg", "<3 deg"), ("pct_area_slope_3_6deg", "3-6 deg"), ("pct_area_slope_6_10deg", "6-10 deg"), ("pct_area_slope_gt_10deg", ">10 deg")]:
        add(col, "terrain", f"Share of this cell's valid DEM pixels with slope {rng}", "%", "Copernicus DEM GLO-30", "2011-2015", "COMPLETE", True, None, "READY")
    add("n_valid_dem_pixels", "terrain", "Count of valid (non-nodata) DEM pixel centers falling in this cell -- a coverage diagnostic, not a suitability input", "count", "Copernicus DEM GLO-30", "2011-2015", "COMPLETE", "N/A (0 would mean no DEM data, none occur citywide)", "Diagnostic column; not intended as a model predictor", "EXCLUDE_FROM_MODEL")
    add("road_grade_status", "terrain", "Explicit status sentinel: road-grade features are not yet computed because the citywide road network is PARTIAL", "categorical (constant)", "N/A", None, "PENDING", "N/A", "Every cell currently reads PENDING_ROAD_NETWORK", "PENDING_DEPENDENCY")

    # --- Transit ---
    for mode, col_c, col_d in [("metro", "metro_station_count", "distance_to_nearest_metro_m"), ("tram", "tram_station_count", "distance_to_nearest_tram_m"), ("rail", "rail_station_count", "distance_to_nearest_rail_m"), ("ferry", "ferry_terminal_count", "distance_to_nearest_ferry_m")]:
        add(col_c, "transit", f"Count of {mode} stations/stops whose point geometry falls within this cell (main_gtfs)", "count", "İBB Toplu Ulaşım GTFS (main_gtfs)", "2023-2024 (infrastructure snapshot; calendar expired)", "COMPLETE", True, "main_gtfs infrastructure last modified 2023-2024, used for station location/topology only, not frequency", "READY_WITH_LIMITATION")
        add(col_d, "transit", f"Distance from cell centroid to the nearest {mode} station (citywide stop set, not clipped)", "m", "İBB Toplu Ulaşım GTFS (main_gtfs)", "2023-2024", "COMPLETE", False, "Same main_gtfs staleness caveat", "READY_WITH_LIMITATION")
    add("metrobus_station_count", "transit", "Count of metrobüs (BRT) stops falling within this cell (iett_gtfs)", "count", "İETT GTFS", "2026-03-17 (current)", "COMPLETE", True, None, "READY")
    add("bus_stop_count", "transit", "Count of regular bus stops falling within this cell (iett_gtfs)", "count", "İETT GTFS", "2026-03-17", "COMPLETE", True, None, "READY")
    add("distance_to_nearest_metrobus_m", "transit", "Distance from cell centroid to nearest metrobüs stop", "m", "İETT GTFS", "2026-03-17", "COMPLETE", False, None, "READY")
    add("distance_to_nearest_bus_stop_m", "transit", "Distance from cell centroid to nearest bus stop", "m", "İETT GTFS", "2026-03-17", "COMPLETE", False, None, "READY")
    add("total_transit_stop_count", "transit", "Sum of all 6 mode station/stop counts (area-based membership)", "count", "İBB main_gtfs + İETT GTFS", "2023-2026 (mixed, see per-mode)", "COMPLETE", True, "Mixes a stale (main_gtfs) and current (iett_gtfs) snapshot in one sum", "READY_WITH_LIMITATION")
    add("distance_to_nearest_transit_m", "transit", "Distance from cell centroid to the nearest transit stop of ANY mode", "m", "İBB main_gtfs + İETT GTFS", "2023-2026", "COMPLETE", False, "Same mixed-currency caveat", "READY_WITH_LIMITATION")
    add("transit_stops_within_500m", "transit", "Count of any-mode transit stops within 500m of cell centroid", "count", "İBB main_gtfs + İETT GTFS", "2023-2026", "COMPLETE", True, None, "READY_WITH_LIMITATION")
    add("transit_stops_within_1000m", "transit", "Count of any-mode transit stops within 1000m of cell centroid", "count", "İBB main_gtfs + İETT GTFS", "2023-2026", "COMPLETE", True, None, "READY_WITH_LIMITATION")
    add("bus_stops_within_500m", "transit", "Count of bus stops (iett_gtfs) within 500m of cell centroid", "count", "İETT GTFS", "2026-03-17", "COMPLETE", True, None, "READY")
    add("fixed_guideway_stations_within_1000m", "transit", "Count of metro+tram+rail stations within 1000m of cell centroid", "count", "İBB main_gtfs", "2023-2024", "COMPLETE", True, "main_gtfs staleness caveat", "READY_WITH_LIMITATION")
    add("rail_stations_within_1000m", "transit", "Deprecated alias, identical values to fixed_guideway_stations_within_1000m", "count", "İBB main_gtfs", "2023-2024", "COMPLETE", True, "Exact duplicate of fixed_guideway_stations_within_1000m; kept only for naming backward-compatibility", "EXCLUDE_FROM_MODEL")
    add("number_of_transit_modes_accessible", "transit", "Count of the 6 modes with at least one stop within TRANSIT_ACCESSIBILITY_RADIUS_M of cell centroid", "count (0-6)", "İBB main_gtfs + İETT GTFS", "2023-2026", "COMPLETE", True, None, "READY_WITH_LIMITATION")
    add("routes_serving_grid", "transit", "Count of unique routes (any mode) with a stop intersecting this cell", "count", "İBB main_gtfs + İETT GTFS", "2023-2026", "COMPLETE", True, "Route topology is robust to a stale snapshot; new post-2024 lines would be missing", "READY_WITH_LIMITATION")
    add("unique_bus_routes", "transit", "Count of unique bus routes with a stop intersecting this cell", "count", "İETT GTFS", "2026-03-17", "COMPLETE", True, None, "READY")
    add("unique_rail_lines", "transit", "Count of unique metro/tram/rail lines with a stop intersecting this cell", "count", "İBB main_gtfs", "2023-2024", "COMPLETE", True, "main_gtfs staleness caveat", "READY_WITH_LIMITATION")
    add("bus_departures_per_day", "transit", "Scheduled weekday bus+metrobüs departures summed across stops in this cell", "departures/day", "İETT GTFS (weekday service_id=0)", "2026-03-17 (current)", "COMPLETE", True, "Scheduled, not observed/real-time departures; bus/metrobüs only, no rail/tram/ferry frequency exists in any feed", "READY")
    add("bus_departures_peak_hour", "transit", "Scheduled weekday departures during the configured peak-hour window", "departures/hour", "İETT GTFS", "2026-03-17", "COMPLETE", True, "Same as bus_departures_per_day", "READY")

    # --- Cycling ---
    add("cycle_infrastructure_length_km_ibb_only", "cycling", "Total İBB-recorded operational cycling infrastructure length clipped to this cell (OSM complement excluded)", "km", "İBB İstanbul Bisiklet Yolları Verisi", "2025-06-05", "COMPLETE (İBB-only)", True, "Definition differs from the pilot's İBB+OSM combined feature of a similar name; not directly comparable to pilot cycle_infrastructure_length_km", "READY_WITH_LIMITATION")
    add("cycle_infrastructure_density_km_per_km2_ibb_only", "cycling", "cycle_infrastructure_length_km_ibb_only / cell land area", "km/km^2", "İBB İstanbul Bisiklet Yolları Verisi", "2025-06-05", "COMPLETE (İBB-only)", True, "Same İBB-only caveat", "READY_WITH_LIMITATION")
    add("protected_cycleway_length_km_ibb_only", "cycling", "Length of the 'protected_separated' (İBB 'Mevcut Ayrılmış') category only, clipped to this cell", "km", "İBB İstanbul Bisiklet Yolları Verisi", "2025-06-05", "COMPLETE (İBB-only)", True, "Same İBB-only caveat", "READY_WITH_LIMITATION")
    add("protected_cycleway_density_km_per_km2_ibb_only", "cycling", "protected_cycleway_length_km_ibb_only / cell land area", "km/km^2", "İBB İstanbul Bisiklet Yolları Verisi", "2025-06-05", "COMPLETE (İBB-only)", True, "Same İBB-only caveat", "READY_WITH_LIMITATION")
    add("distance_to_nearest_cycle_infrastructure_m_ibb_only", "cycling", "Distance from cell centroid to the nearest İBB-recorded cycling infrastructure geometry (OSM complement excluded)", "m", "İBB İstanbul Bisiklet Yolları Verisi", "2025-06-05", "COMPLETE (İBB-only)", False, "İBB-only definition; will read as farther than the pilot's combined-source distance in areas where OSM added complementary segments", "READY_WITH_LIMITATION")
    add("distance_to_nearest_bicycle_parking_m", "cycling", "Distance from cell centroid to nearest İBB bicycle-specific parking point", "m", "İBB Bisiklet ve Mikromobilite Park Alanları", "2025-06-05", "COMPLETE", False, "Same definition as the pilot (already İBB-only there too)", "READY")
    add("bicycle_parking_count", "cycling", "Count of İBB bicycle-specific ('Bisiklet Park Alanı') parking points intersecting this cell", "count", "İBB Bisiklet ve Mikromobilite Park Alanları", "2025-06-05", "COMPLETE", True, "Same definition as the pilot", "READY")
    add("distance_to_nearest_micromobility_parking_m", "cycling", "Distance from cell centroid to nearest İBB micromobility ('Mikromobilite Park Alanı') parking point", "m", "İBB Bisiklet ve Mikromobilite Park Alanları", "2025-06-05", "COMPLETE", False, "New citywide feature, not present in the pilot table", "READY")
    add("micromobility_parking_count", "cycling", "Count of İBB micromobility parking points intersecting this cell", "count", "İBB Bisiklet ve Mikromobilite Park Alanları", "2025-06-05", "COMPLETE", True, "New citywide feature, not present in the pilot table", "READY")
    add("pct_road_network_with_cycle_infrastructure_status", "cycling", "Explicit status sentinel: this feature requires the citywide OSM road network, which is PARTIAL", "categorical (constant)", "N/A", None, "PENDING", "N/A", "Every cell currently reads PENDING_ROAD_NETWORK", "PENDING_DEPENDENCY")

    df = pd.DataFrame(rows)
    missing_from_dict = set(predictor_cols) - set(df["feature_name"])
    extra_in_dict = set(df["feature_name"]) - set(predictor_cols)
    if missing_from_dict:
        print(f"[WARNING] feature dictionary missing entries for: {missing_from_dict}")
    if extra_in_dict:
        print(f"[WARNING] feature dictionary has entries not in the master table: {extra_in_dict}")

    META_DIR.mkdir(parents=True, exist_ok=True)
    out_path = META_DIR / "feature_dictionary_citywide.csv"
    df.to_csv(out_path, index=False)
    print(f"[save] {out_path} ({len(df)} predictor entries)")

    print("\nClassification counts:")
    print(df["classification"].value_counts().to_dict())


if __name__ == "__main__":
    main()
