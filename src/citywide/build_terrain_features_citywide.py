"""Citywide terrain features (Section 4, family 2 of 4 not requiring new
Overpass requests).

Reuses the pilot's Copernicus DEM GLO-30 methodology UNCHANGED:
src.features.terrain_features.{load_and_reproject_dem, compute_slope_degrees,
pixels_to_points, compute_terrain_features} -- same mosaic -> clip -> bilinear
reproject to EPSG:32635 -> Horn's-method slope -> pixel-center zonal stats
pipeline, just over the citywide grid/study area instead of the pilot's.

DEM tiles: the citywide study area's WGS84 bounding box
(27.97-29.96 E, 40.80-41.58 N) needs six 1x1-degree Copernicus DSM tiles
(N40/N41 x E027/E028/E029), all of which are ALREADY cached under
data/raw/dem/ from prior work -- confirmed present before running this
script, so no network fetch happens at all here.

Road-grade features are explicitly NOT computed in this run (the citywide
road network is still PARTIAL, 0/39 districts -- see
fetch_osm_data_citywide_chunked.py). Rather than filling road-grade columns
with NaN (ambiguous with a genuine DEM-coverage gap) or 0 (which would read
as "flat/no grade" and get silently averaged into any downstream index),
every cell gets a single explicit status column, road_grade_status =
"PENDING_ROAD_NETWORK", and no road_grade_* numeric columns are written at
all yet.

Outputs:
  data/processed/citywide/features/terrain_features_citywide.parquet
  data/processed/citywide/qa/terrain_qa_citywide.json
  data/processed/citywide/qa/coverage_gate_terrain.json
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.coverage_gate import coverage_report, print_report
from src.features import dem_source_config as dcfg
from src.features.terrain_features import (
    compute_slope_degrees,
    compute_terrain_features,
    load_and_reproject_dem,
    pixels_to_points,
)
from src.utils import config as cfg

DEM_BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"


def citywide_tiles_needed(study_area_geom) -> list[str]:
    bounds = gpd.GeoSeries([study_area_geom], crs=cfg.METRIC_CRS).to_crs("EPSG:4326").total_bounds
    minlon, minlat, maxlon, maxlat = bounds
    lats = range(int(np.floor(minlat)), int(np.floor(maxlat)) + 1)
    lons = range(int(np.floor(minlon)), int(np.floor(maxlon)) + 1)
    return [f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM" for lat in lats for lon in lons]


def fetch_citywide_dem_tiles(study_area_geom) -> list:
    tiles = citywide_tiles_needed(study_area_geom)
    out_dir = cfg.DATA_RAW_DEM
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for tile in tiles:
        out_path = out_dir / f"{tile}.tif"
        meta_path = out_dir / f"{tile}.meta.json"
        if out_path.exists():
            print(f"[cache] {tile} already cached (not re-fetched)")
            paths.append(out_path)
            continue
        url = f"{DEM_BASE_URL}/{tile}/{tile}.tif"
        print(f"[fetch] downloading {url} ...")
        resp = requests.get(url, timeout=180, headers={"User-Agent": "istanbul-mobility-research/0.1"})
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        meta = {**dcfg.COPERNICUS_DEM, "tile": tile, "source_url": url, "retrieval_date": cfg.DEM_RETRIEVAL_DATE, "file_size_bytes": len(resp.content)}
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[cache] wrote {tile} ({len(resp.content) / 1e6:.1f} MB) -> {out_path}")
        paths.append(out_path)
    return paths


def load_citywide_grid() -> gpd.GeoDataFrame:
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 22322, f"expected the frozen citywide grid (22,322 cells), found {len(grid)}"
    assert grid["grid_id"].is_unique
    return grid


def pilot_regression_check(terrain_gdf: gpd.GeoDataFrame) -> dict:
    """Compares the 3 original pilot districts' citywide-run terrain stats
    against the previously published pilot terrain_qa_report.json, as a
    regression check -- same DEM, same method, should be very close (small
    differences are possible from a larger reprojection window and a
    39-vs-3-district grid rebuild, but should NOT be large)."""
    pilot_qa_path = cfg.PROJECT_ROOT / "data" / "processed" / "features" / "terrain_qa_report.json"
    if not pilot_qa_path.exists():
        return {"status": "SKIPPED", "reason": f"{pilot_qa_path} not found"}

    pilot_qa = json.loads(pilot_qa_path.read_text(encoding="utf-8"))
    pilot_by_district = pilot_qa.get("spatial_sanity_check", {}).get("mean_elevation_and_slope_by_district", {})

    citywide_by_district = terrain_gdf.groupby("district")[["mean_elevation_m", "mean_slope_deg"]].mean().round(2)

    comparison = {}
    for district in ["Kadıköy", "Üsküdar", "Maltepe"]:
        if district not in pilot_by_district:
            comparison[district] = {"status": "pilot value not found"}
            continue
        pilot_elev = pilot_by_district[district]["mean_elevation_m"]
        pilot_slope = pilot_by_district[district]["mean_slope_deg"]
        cw_elev = float(citywide_by_district.loc[district, "mean_elevation_m"])
        cw_slope = float(citywide_by_district.loc[district, "mean_slope_deg"])
        comparison[district] = {
            "pilot_mean_elevation_m": pilot_elev, "citywide_mean_elevation_m": cw_elev,
            "elevation_diff_m": round(cw_elev - pilot_elev, 3),
            "pilot_mean_slope_deg": pilot_slope, "citywide_mean_slope_deg": cw_slope,
            "slope_diff_deg": round(cw_slope - pilot_slope, 3),
        }
    return {"status": "COMPARED", "note": "small differences expected (different grid build, larger reprojection window); large differences would indicate a regression", "comparison": comparison}


def main() -> None:
    print("=" * 72)
    print("Citywide terrain features (39 districts, 22,322-cell grid)")
    print("=" * 72)

    grid = load_citywide_grid()
    study_area = gpd.read_file(cfg.DATA_PROCESSED / "study_area_metric.gpkg").geometry.iloc[0]

    tiles_needed = citywide_tiles_needed(study_area)
    print(f"Citywide extent requires {len(tiles_needed)} DEM tiles: {tiles_needed}")
    tile_paths = fetch_citywide_dem_tiles(study_area)

    print("\n[1/3] DEM mosaic, clip, reproject to EPSG:32635 (bilinear)...")
    elevation, transform, dem_diag = load_and_reproject_dem(tile_paths, study_area)
    print(f"  reprojected shape: {dem_diag['reprojected_shape']}, "
          f"valid pixels: {dem_diag['n_valid_pixels']:,}, nodata: {dem_diag['n_nodata_pixels']:,}")

    print("\n[2/3] Slope (Horn's method) + per-cell zonal stats...")
    slope = compute_slope_degrees(elevation, cfg.DEM_TARGET_RESOLUTION_M)
    pixels = pixels_to_points(elevation, slope, transform)
    terrain, terrain_diag = compute_terrain_features(pixels, grid)
    terrain["road_grade_status"] = "PENDING_ROAD_NETWORK"

    missing = set(grid["grid_id"]) - set(terrain["grid_id"])
    assert not missing, f"{len(missing)} grid cells disappeared during terrain processing"
    assert len(terrain) == 22322 and terrain["grid_id"].is_unique

    print("\n[3/3] QA...")
    base = grid[["grid_id", "district", "geometry"]]
    terrain_gdf = gpd.GeoDataFrame(base.merge(terrain, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)

    elev_cols = ["mean_elevation_m", "median_elevation_m", "min_elevation_m", "max_elevation_m", "elevation_range_m", "elevation_std_m"]
    slope_cols = ["mean_slope_deg", "median_slope_deg", "max_slope_deg", "slope_std_deg"]

    desc = terrain_gdf[elev_cols + slope_cols].describe().T[["min", "50%", "mean", "max"]].rename(columns={"50%": "median"}).round(3).to_dict(orient="index")

    n_zero_pixel_cells = int((terrain_gdf["n_valid_dem_pixels"] == 0).sum())
    by_district_zero = terrain_gdf[terrain_gdf["n_valid_dem_pixels"] == 0]["district"].value_counts().to_dict()
    extreme_slope_cells = terrain_gdf.loc[terrain_gdf["mean_slope_deg"] > 15, ["grid_id", "district", "mean_slope_deg", "max_slope_deg"]]

    centroids_ll = terrain_gdf.geometry.centroid.to_crs(cfg.STORAGE_CRS)
    ll = terrain_gdf.assign(lat=centroids_ll.y, lon=centroids_ll.x)
    lowest = ll.nsmallest(5, "mean_elevation_m")[["grid_id", "district", "lat", "lon", "mean_elevation_m", "mean_slope_deg"]]
    highest = ll.nlargest(5, "mean_elevation_m")[["grid_id", "district", "lat", "lon", "mean_elevation_m", "mean_slope_deg"]]
    by_district_stats = terrain_gdf.groupby("district")[["mean_elevation_m", "mean_slope_deg"]].mean().round(2)

    regression = pilot_regression_check(terrain_gdf)

    n_districts_present = terrain_gdf["district"].nunique()
    edge_cells = terrain_gdf[terrain_gdf["n_valid_dem_pixels"].between(1, 3, inclusive="both")]

    qa = {
        "dem_source": dcfg.COPERNICUS_DEM["dataset_name"],
        "dem_resolution": dcfg.COPERNICUS_DEM["native_resolution"],
        "dem_vertical_datum": dcfg.COPERNICUS_DEM["vertical_datum"],
        "tiles_used_citywide": tiles_needed,
        "tiles_reused_from_cache": True,
        "reprojected_resolution_m": dem_diag["reprojected_resolution_m"],
        "resampling_method": dem_diag["resampling_method"],
        "reprojected_shape": dem_diag["reprojected_shape"],
        "n_valid_dem_pixels_in_study_extent": dem_diag["n_valid_pixels"],
        "n_nodata_pixels_in_study_extent": dem_diag["n_nodata_pixels"],
        "n_grid_cells": len(terrain_gdf),
        "n_districts_present": n_districts_present,
        "n_cells_with_zero_valid_dem_pixels": n_zero_pixel_cells,
        "pct_cells_with_zero_valid_dem_pixels": round(n_zero_pixel_cells / len(terrain_gdf) * 100, 3),
        "zero_dem_pixel_cells_by_district": by_district_zero,
        "n_edge_cells_1_to_3_valid_pixels": len(edge_cells),
        "elevation_stats": desc,
        "n_cells_mean_slope_over_15deg": int(len(extreme_slope_cells)),
        "extreme_slope_cells": extreme_slope_cells.to_dict(orient="records"),
        "missing_values": {c: int(terrain_gdf[c].isna().sum()) for c in elev_cols + slope_cols},
        "road_grade_status": "PENDING_ROAD_NETWORK",
        "road_grade_note": "Citywide road network is PARTIAL (0/39 districts cached); road-grade features "
        "will be computed once the road network layer is complete. No road-grade columns are populated in "
        "this output; every cell carries road_grade_status='PENDING_ROAD_NETWORK' instead.",
        "lowest_elevation_cells": lowest.round(4).to_dict(orient="records"),
        "highest_elevation_cells": highest.round(4).to_dict(orient="records"),
        "mean_elevation_and_slope_by_district": by_district_stats.to_dict(orient="index"),
        "pilot_3_district_regression_check": regression,
        "completeness_status": "ELEVATION_SLOPE_COMPLETE; ROAD_GRADE_PENDING_ROAD_NETWORK",
    }

    out_dir = cfg.DATA_FEATURES
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "terrain_features_citywide.parquet"
    terrain_gdf.to_parquet(out_path)
    print(f"\n[save] {out_path}")

    qa_dir = cfg.DATA_PROCESSED / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_path = qa_dir / "terrain_qa_citywide.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {qa_path}")

    value_cols = ["mean_elevation_m", "mean_slope_deg"]
    report = coverage_report(terrain_gdf, value_cols)
    print_report(report, "terrain")
    gate_path = qa_dir / "coverage_gate_terrain.json"
    gate_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[save] {gate_path}")

    print("\n--- SUMMARY ---")
    print(f"Districts present: {n_districts_present}/39")
    print(f"Cells with zero valid DEM pixels: {n_zero_pixel_cells} ({qa['pct_cells_with_zero_valid_dem_pixels']}%)")
    print(f"Elevation range (citywide): {terrain_gdf['mean_elevation_m'].min():.1f}m to {terrain_gdf['mean_elevation_m'].max():.1f}m")
    print(f"Slope range (citywide mean_slope_deg): {terrain_gdf['mean_slope_deg'].min():.2f} to {terrain_gdf['mean_slope_deg'].max():.2f} deg")
    print(f"Pilot 3-district regression check: {regression['status']}")
    if regression["status"] == "COMPARED":
        print(json.dumps(regression["comparison"], indent=2))


if __name__ == "__main__":
    main()
