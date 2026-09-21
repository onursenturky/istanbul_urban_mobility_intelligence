"""Citywide cycling infrastructure features (Section 4, family 4 of 4 not
requiring new Overpass requests) -- İBB-ONLY, per explicit instruction.

Uses ONLY the two authoritative İBB datasets already fetched and validated
in the pilot (both are citywide publications by nature -- no re-fetch, no
Overpass, no new OSM request of any kind):
  - "İstanbul Bisiklet Yolları Verisi" (bike paths), 341 features covering
    all 39 districts, with an official PRJ_ASAMA (project stage) field --
    reused UNCHANGED via src.features.cycling_infrastructure_features.
    load_ibb_lines, which already excludes planned/under-construction/
    undetermined stages (IBB_STAGE_TO_CATEGORY maps them to None and drops
    them) -- operational-only infrastructure, exactly as the pilot defined it.
  - "Bisiklet ve Mikromobilite Park Alanları" (bicycle/micromobility
    parking), 384 points citywide, Park_Tipi field distinguishing
    "Bisiklet Park Alanı" (bicycle-specific) from "Mikromobilite Park
    Alanı" (scooter/e-bike-oriented) -- both counted here, kept separate.

What is DELIBERATELY NOT computed, and why:
  - No OSM cycling ways are loaded or deduplicated against İBB here (the
    pilot's build_combined_network merged İBB + OSM; this run uses ONLY
    load_ibb_lines, skipping load_osm_lines and both dedup passes entirely).
    Every length/density/distance feature derived from the network is
    therefore explicitly suffixed "_ibb_only" so it is never confused with
    the pilot's combined-source definition of the same-sounding column.
  - pct_road_network_with_cycle_infrastructure requires the citywide OSM
    road network (still PARTIAL, 0/39 districts) -- not computed at all;
    every cell instead carries pct_road_network_with_cycle_infrastructure_
    status = "PENDING_ROAD_NETWORK".
  - bicycle_parking_count and distance_to_nearest_bicycle_parking_m were
    ALREADY İBB-only in the pilot (OSM parking was only ever a completeness
    cross-check, never merged into the primary feature) -- these keep their
    original pilot names unchanged, since their definition has not changed.

Outputs:
  data/processed/citywide/features/cycling_features_citywide.parquet
  data/processed/citywide/qa/cycling_qa_citywide.json
  data/processed/citywide/qa/coverage_gate_cycling.json
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.coverage_gate import coverage_report, print_report
from src.features import cycling_source_config as ccfg
from src.features.cycling_infrastructure_features import (
    compute_cycling_features,
    compute_network_connectivity,
    load_ibb_lines,
)
from src.utils import config as cfg

IBB_BIKE_PATHS_PATH = cfg.DATA_RAW / "cycling" / "ibb_bisiklet_yollari.geojson"
IBB_PARKING_PATH = cfg.DATA_RAW / "cycling" / "ibb_bisiklet_parking.geojson"

# Columns whose pilot definition was computed from the İBB+OSM COMBINED
# network -- renamed here so an İBB-only value is never mistaken for the
# pilot's combined-source value of the same name.
NETWORK_DERIVED_RENAME = {
    "cycle_infrastructure_length_km": "cycle_infrastructure_length_km_ibb_only",
    "cycle_infrastructure_density_km_per_km2": "cycle_infrastructure_density_km_per_km2_ibb_only",
    "protected_cycleway_length_km": "protected_cycleway_length_km_ibb_only",
    "protected_cycleway_density_km_per_km2": "protected_cycleway_density_km_per_km2_ibb_only",
    "distance_to_nearest_cycle_infrastructure_m": "distance_to_nearest_cycle_infrastructure_m_ibb_only",
}


def load_citywide_grid() -> gpd.GeoDataFrame:
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 22322, f"expected the frozen citywide grid (22,322 cells), found {len(grid)}"
    assert grid["grid_id"].is_unique
    return grid


def load_ibb_parking_both_types(path) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    gdf = gpd.read_file(path)
    bicycle = gdf[gdf["Park_Tipi"] == "Bisiklet Park Alanı"].copy().to_crs(cfg.METRIC_CRS)
    micromobility = gdf[gdf["Park_Tipi"] == "Mikromobilite Park Alanı"].copy().to_crs(cfg.METRIC_CRS)
    return bicycle[["Park_Alani", "Ilce", "geometry"]], micromobility[["Park_Alani", "Ilce", "geometry"]]


def compute_micromobility_parking_features(micromobility: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> pd.DataFrame:
    centroids = grid.geometry.centroid
    centroid_xy = np.column_stack([centroids.x.to_numpy(), centroids.y.to_numpy()])
    if len(micromobility):
        park_xy = np.column_stack([micromobility.geometry.x.to_numpy(), micromobility.geometry.y.to_numpy()])
        dist, _ = cKDTree(park_xy).query(centroid_xy, k=1)
        joined = gpd.sjoin(micromobility[["geometry"]], grid[["grid_id", "geometry"]], predicate="intersects", how="inner")
        counts = joined.groupby("grid_id").size()
    else:
        dist = np.full(len(grid), np.nan)
        counts = pd.Series(dtype=int)
    result = grid[["grid_id"]].copy()
    result["distance_to_nearest_micromobility_parking_m"] = dist
    result = result.merge(counts.rename("micromobility_parking_count"), on="grid_id", how="left")
    result["micromobility_parking_count"] = result["micromobility_parking_count"].fillna(0).astype(int)
    return result


def check_duplicate_geometries(gdf: gpd.GeoDataFrame, label: str) -> dict:
    wkt_norm = gdf.geometry.apply(lambda g: g.wkt)
    n_exact_dup = int(wkt_norm.duplicated().sum())
    return {"n_features": len(gdf), "n_exact_duplicate_geometries": n_exact_dup}


def check_duplicate_points(gdf: gpd.GeoDataFrame, label: str, tolerance_m: float = 10.0) -> dict:
    if len(gdf) < 2:
        return {"n_points": len(gdf), "n_near_duplicate_pairs_within_10m": 0}
    xy = np.column_stack([gdf.geometry.x.to_numpy(), gdf.geometry.y.to_numpy()])
    tree = cKDTree(xy)
    pairs = tree.query_pairs(r=tolerance_m)
    return {"n_points": len(gdf), "n_near_duplicate_pairs_within_10m": len(pairs)}


def pilot_regression_check(features_gdf: gpd.GeoDataFrame) -> dict:
    pilot_path = cfg.PROJECT_ROOT / "data" / "processed" / "features" / "cycling_infrastructure_features.parquet"
    if not pilot_path.exists():
        return {"status": "SKIPPED", "reason": f"{pilot_path} not found"}
    pilot = gpd.read_parquet(pilot_path)

    comparison = {}
    for district in ["Kadıköy", "Üsküdar", "Maltepe"]:
        if "district" not in pilot.columns or district not in pilot["district"].values:
            comparison[district] = {"status": "not found in pilot output"}
            continue
        p = pilot[pilot["district"] == district]
        c = features_gdf[features_gdf["district"] == district]
        comparison[district] = {
            "pilot_combined_ibb_osm_infra_length_km": round(float(p["cycle_infrastructure_length_km"].sum()), 3) if "cycle_infrastructure_length_km" in p.columns else None,
            "citywide_ibb_only_infra_length_km": round(float(c["cycle_infrastructure_length_km_ibb_only"].sum()), 3),
            "pilot_bicycle_parking_count": int(p["bicycle_parking_count"].sum()) if "bicycle_parking_count" in p.columns else None,
            "citywide_bicycle_parking_count": int(c["bicycle_parking_count"].sum()),
        }
    return {
        "status": "COMPARED",
        "caveat": "Pilot combined İBB+OSM (OSM contributing only non-overlapping complementary segments after "
        "dedup); this citywide run is İBB-only. A citywide_ibb_only length AT OR BELOW the pilot combined length "
        "is EXPECTED, not a regression -- it reflects the removed OSM complement, not a data-quality loss. "
        "bicycle_parking_count was İBB-only in both runs and should match closely (small differences only from "
        "the independent citywide grid rebuild's boundary cells).",
        "comparison": comparison,
    }


def main() -> None:
    print("=" * 72)
    print("Citywide cycling infrastructure features (İBB-only, 39 districts, 22,322 cells)")
    print("=" * 72)

    grid = load_citywide_grid()

    print("\n[1/4] Loading İBB bike paths (İBB-only, no OSM)...")
    ibb_network, ibb_diag = load_ibb_lines(IBB_BIKE_PATHS_PATH)
    ibb_network["length_m"] = ibb_network.geometry.length
    ibb_network = ibb_network[ibb_network["length_m"] > 0].copy()
    print(f"  {ibb_diag}")
    dup_lines = check_duplicate_geometries(ibb_network, "ibb_bike_paths")
    print(f"  duplicate geometry check: {dup_lines}")

    connectivity = compute_network_connectivity(ibb_network)
    print(f"  network connectivity (İBB-only, study-area-wide): {connectivity}")

    print("\n[2/4] Loading İBB parking (bicycle + micromobility, kept separate)...")
    bicycle_parking, micromobility_parking = load_ibb_parking_both_types(IBB_PARKING_PATH)
    print(f"  bicycle parking: {len(bicycle_parking)}, micromobility parking: {len(micromobility_parking)}")
    dup_bike_park = check_duplicate_points(bicycle_parking, "bicycle_parking")
    dup_micro_park = check_duplicate_points(micromobility_parking, "micromobility_parking")
    print(f"  duplicate point checks: bicycle={dup_bike_park}, micromobility={dup_micro_park}")

    print("\n[3/4] Computing per-cell features...")
    features, feat_diag = compute_cycling_features(ibb_network, bicycle_parking, grid)
    features = features.rename(columns=NETWORK_DERIVED_RENAME)

    micro_features = compute_micromobility_parking_features(micromobility_parking, grid)
    features = features.merge(micro_features, on="grid_id", how="left")
    features["pct_road_network_with_cycle_infrastructure_status"] = "PENDING_ROAD_NETWORK"

    missing = set(grid["grid_id"]) - set(features["grid_id"])
    assert not missing, f"{len(missing)} grid cells disappeared during cycling feature processing"
    assert len(features) == 22322 and features["grid_id"].is_unique

    base = grid[["grid_id", "district", "land_area_m2", "geometry"]]
    features_gdf = gpd.GeoDataFrame(base.merge(features, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)

    print("\n[4/4] QA...")
    numeric_cols = [
        "cycle_infrastructure_length_km_ibb_only", "cycle_infrastructure_density_km_per_km2_ibb_only",
        "protected_cycleway_length_km_ibb_only", "protected_cycleway_density_km_per_km2_ibb_only",
        "distance_to_nearest_cycle_infrastructure_m_ibb_only", "distance_to_nearest_bicycle_parking_m",
        "bicycle_parking_count", "distance_to_nearest_micromobility_parking_m", "micromobility_parking_count",
    ]
    desc = features_gdf[numeric_cols].describe().T[["min", "50%", "mean", "max"]].rename(columns={"50%": "median"}).round(4).to_dict(orient="index")

    n_zero_infra = int((features_gdf["cycle_infrastructure_length_km_ibb_only"] == 0).sum())
    n_zero_bike_parking = int((features_gdf["bicycle_parking_count"] == 0).sum())
    n_zero_micro_parking = int((features_gdf["micromobility_parking_count"] == 0).sum())

    districts_gdf = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    infra_by_district_m2 = features_gdf.groupby("district")["cycle_infrastructure_length_km_ibb_only"].sum()
    districts_zero_infra = [d for d in districts_gdf["district"] if infra_by_district_m2.get(d, 0) == 0]
    bike_parking_by_district = features_gdf.groupby("district")["bicycle_parking_count"].sum()
    districts_zero_bike_parking = [d for d in districts_gdf["district"] if bike_parking_by_district.get(d, 0) == 0]

    total_len = features_gdf["cycle_infrastructure_length_km_ibb_only"].sum()
    concentration_flags = {}
    if total_len > 0:
        max_cell = features_gdf["cycle_infrastructure_length_km_ibb_only"].max()
        share = max_cell / total_len * 100
        if share > 15:
            concentration_flags["cycle_infrastructure_length"] = {"max_single_cell_km": round(float(max_cell), 3), "pct_of_citywide_total": round(float(share), 1)}

    total_bike_parking = features_gdf["bicycle_parking_count"].sum()
    max_bike_parking_cell = features_gdf["bicycle_parking_count"].max()
    if total_bike_parking > 0 and max_bike_parking_cell / total_bike_parking > 0.15:
        concentration_flags["bicycle_parking_count"] = {"max_single_cell": int(max_bike_parking_cell), "pct_of_citywide_total": round(float(max_bike_parking_cell / total_bike_parking * 100), 1)}

    invalid_ibb = int((~ibb_network.geometry.is_valid).sum())
    invalid_bike_parking = int((~bicycle_parking.geometry.is_valid).sum())
    invalid_micro_parking = int((~micromobility_parking.geometry.is_valid).sum())

    regression = pilot_regression_check(features_gdf)

    ibb_meta = json.loads((cfg.DATA_RAW / "cycling" / "ibb_bisiklet_yollari.meta.json").read_text(encoding="utf-8"))
    parking_meta = json.loads((cfg.DATA_RAW / "cycling" / "ibb_bisiklet_parking.meta.json").read_text(encoding="utf-8"))

    qa = {
        "sources": {
            "bike_paths": {"dataset_name": ibb_meta.get("dataset_name"), "last_modified": ibb_meta.get("last_modified"), "n_raw_features": ibb_diag["n_raw"]},
            "parking": {"dataset_name": parking_meta.get("dataset_name"), "last_modified": parking_meta.get("last_modified"), "n_bicycle": len(bicycle_parking), "n_micromobility": len(micromobility_parking)},
            "excluded_non_operational_stages": ibb_diag["n_excluded_not_existing"],
        },
        "geographic_coverage_note": ibb_meta.get("coverage"),
        "n_grid_cells": len(features_gdf),
        "n_districts_present": features_gdf["district"].nunique(),
        "network_ibb_only": {
            "n_geometries_used": ibb_diag["n_used"],
            "n_invalid_geometries": invalid_ibb,
            "total_length_km_ibb_only_citywide": round(float(ibb_network["length_m"].sum() / 1000), 3) if "length_m" in ibb_network.columns else None,
            "length_km_by_category": (ibb_network.assign(length_m=ibb_network.geometry.length).groupby("category")["length_m"].sum() / 1000).round(3).to_dict(),
            "categories_structurally_unavailable_ibb_only": ["dedicated_lane", "painted_on_road"],
            "categories_unavailable_note": "These two categories are defined only via OSM cycleway=lane/shared_lane/"
            "opposite_lane tags in the pilot's category scheme; with OSM excluded they are structurally absent "
            "(not a data gap) from this İBB-only run.",
            "duplicate_geometry_check": dup_lines,
            "connectivity_ibb_only": connectivity,
        },
        "parking": {
            "duplicate_point_check_bicycle": dup_bike_park,
            "duplicate_point_check_micromobility": dup_micro_park,
            "n_invalid_geometries_bicycle": invalid_bike_parking,
            "n_invalid_geometries_micromobility": invalid_micro_parking,
        },
        "district_coverage": {
            "n_districts_zero_infrastructure": len(districts_zero_infra),
            "districts_zero_infrastructure": districts_zero_infra,
            "n_districts_zero_bicycle_parking": len(districts_zero_bike_parking),
            "districts_zero_bicycle_parking": districts_zero_bike_parking,
        },
        "n_cells_zero_infrastructure": n_zero_infra,
        "pct_cells_zero_infrastructure": round(n_zero_infra / len(features_gdf) * 100, 2),
        "n_cells_zero_bicycle_parking": n_zero_bike_parking,
        "pct_cells_zero_bicycle_parking": round(n_zero_bike_parking / len(features_gdf) * 100, 2),
        "n_cells_zero_micromobility_parking": n_zero_micro_parking,
        "zero_value_interpretation_note": "A cell with zero cycle-infrastructure length or zero parking here "
        "means no İBB-recorded facility was found in or near that cell -- a genuine absence per this source, "
        "NOT a missing-data placeholder. This is expected to be common: only 341 line features and 384 points "
        "exist citywide against 22,322 cells.",
        "implausible_concentration_flags": concentration_flags,
        "descriptive_stats": desc,
        "missing_values": {c: int(features_gdf[c].isna().sum()) for c in numeric_cols},
        "pct_road_network_with_cycle_infrastructure": "PENDING_ROAD_NETWORK (citywide OSM road network is PARTIAL, 0/39 districts)",
        "pilot_3_district_regression_check": regression,
        "completeness_status": "İBB_ONLY_COMPLETE; OSM_COMPLEMENT_NOT_INCLUDED; PCT_ROAD_WITH_CYCLE_INFRA_PENDING_ROAD_NETWORK",
    }

    out_dir = cfg.DATA_FEATURES
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cycling_features_citywide.parquet"
    features_gdf.to_parquet(out_path)
    print(f"\n[save] {out_path}")

    qa_dir = cfg.DATA_PROCESSED / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_path = qa_dir / "cycling_qa_citywide.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {qa_path}")

    value_cols = ["cycle_infrastructure_length_km_ibb_only", "bicycle_parking_count", "micromobility_parking_count"]
    report = coverage_report(features_gdf, value_cols)
    print_report(report, "cycling")
    gate_path = qa_dir / "coverage_gate_cycling.json"
    gate_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[save] {gate_path}")

    print("\n--- SUMMARY ---")
    print(f"Districts present: {qa['n_districts_present']}/39")
    print(f"Total İBB-only cycling infra length citywide: {qa['network_ibb_only']['total_length_km_ibb_only_citywide']} km")
    print(f"Districts with zero infra: {qa['district_coverage']['n_districts_zero_infrastructure']}")
    print(f"Cells with zero infra: {qa['pct_cells_zero_infrastructure']}%")
    print(f"Concentration flags: {concentration_flags if concentration_flags else 'none'}")
    print(f"Regression check: {regression['status']}")
    if regression["status"] == "COMPARED":
        print(json.dumps(regression["comparison"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
