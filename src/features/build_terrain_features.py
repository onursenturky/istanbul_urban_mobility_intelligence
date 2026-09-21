"""Phase 3D orchestrator: terrain, elevation and cycling-slope features.

Loads the cached Copernicus DEM tiles (fetched by src.data.fetch_dem_data)
and the cached Phase 3A OSM road network (never re-fetched), computes
elevation/slope/road-grade features per grid cell, merges them onto the
canonical Phase 2 grid, verifies Phase 3A-3C features are untouched, runs
QA, and writes:
  - data/processed/features/terrain_features.parquet
  - data/processed/features/urban_mobility_features.parquet (+ Phase 3D)
  - data/processed/features/terrain_feature_dictionary.csv
  - data/processed/features/terrain_qa_report.json
  - outputs/maps/terrain_{elevation,slope,steep_area_pct,road_grade}.png

Run from the project root:
    .venv/bin/python -m src.features.build_terrain_features
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
import pandas as pd

from src.data.fetch_dem_data import fetch_dem_tiles
from src.features import dem_source_config as dcfg
from src.features import terrain_feature_dictionary as feat_dict
from src.features.road_grade_features import compute_road_grade_features, prepare_road_edges
from src.features.terrain_features import (
    compute_slope_degrees,
    compute_terrain_features,
    load_and_reproject_dem,
    pixels_to_points,
)
from src.utils import config as cfg


def load_grid() -> gpd.GeoDataFrame:
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 514, f"expected the canonical 514-cell V1 grid, found {len(grid)}"
    assert grid["grid_id"].is_unique
    return grid


def load_existing_combined() -> gpd.GeoDataFrame:
    path = cfg.DATA_FEATURES / "urban_mobility_features.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run Phase 3A-3C first.")
    return gpd.read_parquet(path)


def _assert_all_grid_ids_present(df: pd.DataFrame, grid_ids: pd.Index, label: str) -> None:
    missing = set(grid_ids) - set(df["grid_id"])
    assert not missing, f"{label}: {len(missing)} grid cells disappeared during processing"
    assert len(df) == len(grid_ids), f"{label}: row count {len(df)} != {len(grid_ids)} grid cells"


def verify_prior_features_unchanged(existing: gpd.GeoDataFrame, combined: gpd.GeoDataFrame) -> bool:
    prior_cols = [c for c in existing.columns if c not in ("grid_id", "district", "land_area_m2", "geometry")]
    a = existing.set_index("grid_id")[prior_cols].sort_index()
    b = combined.set_index("grid_id")[prior_cols].sort_index()
    return a.equals(b)


def run_qa(terrain: pd.DataFrame, dem_diag: dict, road_diag: dict) -> dict:
    elev_cols = ["mean_elevation_m", "median_elevation_m", "min_elevation_m", "max_elevation_m", "elevation_range_m", "elevation_std_m"]
    slope_cols = ["mean_slope_deg", "median_slope_deg", "max_slope_deg", "slope_std_deg"]
    grade_cols = ["mean_absolute_road_grade_pct", "median_absolute_road_grade_pct", "pct_road_length_grade_gt_5pct", "pct_road_length_grade_gt_8pct"]

    def _desc(cols):
        d = terrain[cols].describe().T[["min", "50%", "mean", "max"]].rename(columns={"50%": "median"})
        return d.round(3).to_dict(orient="index")

    n_zero_pixel_cells = int((terrain["n_valid_dem_pixels"] == 0).sum())
    extreme_slope_cells = terrain.loc[terrain["mean_slope_deg"] > 15, ["grid_id", "mean_slope_deg", "max_slope_deg"]]

    qa = {
        "dem_source": dcfg.COPERNICUS_DEM["dataset_name"],
        "dem_resolution": dcfg.COPERNICUS_DEM["native_resolution"],
        "dem_vertical_datum": dcfg.COPERNICUS_DEM["vertical_datum"],
        "reprojected_resolution_m": dem_diag["reprojected_resolution_m"],
        "resampling_method": dem_diag["resampling_method"],
        "n_valid_dem_pixels_in_study_extent": dem_diag["n_valid_pixels"],
        "n_nodata_pixels_in_study_extent": dem_diag["n_nodata_pixels"],
        "n_cells_with_zero_valid_dem_pixels": n_zero_pixel_cells,
        "elevation_stats": _desc(elev_cols),
        "slope_stats": _desc(slope_cols),
        "n_cells_mean_slope_over_15deg": int(len(extreme_slope_cells)),
        "extreme_slope_cells": extreme_slope_cells.to_dict(orient="records"),
        "missing_values": {c: int(terrain[c].isna().sum()) for c in elev_cols + slope_cols},
        "road_grade_diagnostics": road_diag,
        "road_grade_stats": _desc(grade_cols) if road_diag["n_edges_used_for_grade"] > 0 else None,
        "n_cells_with_no_road_grade_sample": int(terrain["road_grade_sample_length_m"].eq(0).sum()),
    }
    return qa


def spatial_sanity_check(terrain_gdf: gpd.GeoDataFrame) -> dict:
    centroids_ll = terrain_gdf.geometry.centroid.to_crs(cfg.STORAGE_CRS)
    ll = terrain_gdf.copy()
    ll["lat"] = centroids_ll.y
    ll["lon"] = centroids_ll.x

    lowest = ll.nsmallest(5, "mean_elevation_m")[["grid_id", "district", "lat", "lon", "mean_elevation_m", "mean_slope_deg"]]
    highest = ll.nlargest(5, "mean_elevation_m")[["grid_id", "district", "lat", "lon", "mean_elevation_m", "mean_slope_deg"]]

    by_district = terrain_gdf.groupby("district")[["mean_elevation_m", "mean_slope_deg"]].mean().round(2)

    return {
        "lowest_elevation_cells": lowest.round(4).to_dict(orient="records"),
        "highest_elevation_cells": highest.round(4).to_dict(orient="records"),
        "mean_elevation_and_slope_by_district": by_district.to_dict(orient="index"),
        "interpretation": (
            "Lowest-elevation cells are expected along the Bosphorus/Marmara coastline (near 0m); "
            "highest-elevation cells are expected inland/north (higher terrain in northern Üsküdar). "
            "No values were manually adjusted based on this expectation — reported for plausibility "
            "review only."
        ),
    }


def save_outputs(terrain_gdf: gpd.GeoDataFrame, combined: gpd.GeoDataFrame) -> dict:
    cfg.DATA_FEATURES.mkdir(parents=True, exist_ok=True)
    paths = {
        "terrain_parquet": cfg.DATA_FEATURES / "terrain_features.parquet",
        "combined_parquet": cfg.DATA_FEATURES / "urban_mobility_features.parquet",
        "feature_dictionary": cfg.DATA_FEATURES / "terrain_feature_dictionary.csv",
    }
    terrain_gdf.to_parquet(paths["terrain_parquet"])
    combined.to_parquet(paths["combined_parquet"])
    feat_dict.as_dataframe().to_csv(paths["feature_dictionary"], index=False)
    return paths


def _map_extent(districts_gdf: gpd.GeoDataFrame):
    minx, miny, maxx, maxy = districts_gdf.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    return (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)


def make_validation_maps(combined: gpd.GeoDataFrame, has_road_grade: bool) -> dict:
    districts_gdf = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    extent = _map_extent(districts_gdf)
    cfg.OUTPUTS_MAPS.mkdir(parents=True, exist_ok=True)
    paths = {}

    def _base(ax, title):
        districts_gdf.boundary.plot(ax=ax, linewidth=1.4, color="black", zorder=3)
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        ax.set_title(title)
        ax.set_axis_off()

    specs = [
        ("mean_elevation_m", "Mean elevation (m, EGM2008 geoid)", "terrain", "terrain_elevation.png"),
        ("mean_slope_deg", "Mean terrain slope (degrees)", "YlOrRd", "terrain_slope.png"),
        ("pct_area_slope_gt_10deg", "Share of cell area with slope > 10 deg (%)", "OrRd", "terrain_steep_area_pct.png"),
    ]
    for column, title, cmap, filename in specs:
        fig, ax = plt.subplots(figsize=(10, 10))
        combined.plot(column=column, cmap=cmap, ax=ax, legend=True, edgecolor="#666666", linewidth=0.1, missing_kwds={"color": "lightgrey"})
        _base(ax, title)
        out = cfg.OUTPUTS_MAPS / filename
        fig.savefig(out, dpi=200, bbox_inches="tight")
        plt.close(fig)
        paths[column] = out

    if has_road_grade:
        fig, ax = plt.subplots(figsize=(10, 10))
        combined.plot(column="mean_absolute_road_grade_pct", cmap="PuRd", ax=ax, legend=True, edgecolor="#666666", linewidth=0.1, missing_kwds={"color": "lightgrey"})
        _base(ax, "Mean absolute road grade (%)")
        out = cfg.OUTPUTS_MAPS / "terrain_road_grade.png"
        fig.savefig(out, dpi=200, bbox_inches="tight")
        plt.close(fig)
        paths["mean_absolute_road_grade_pct"] = out

    return paths


def main() -> None:
    print("=" * 72)
    print("Istanbul Urban Mobility Intelligence — Phase 3D: Terrain, Elevation & Cycling Slope")
    print("=" * 72)

    grid = load_grid()
    existing_combined = load_existing_combined()
    study_area = gpd.read_file(cfg.DATA_PROCESSED / "study_area_metric.gpkg").geometry.iloc[0]
    grid_ids = grid["grid_id"]

    tile_paths = fetch_dem_tiles()
    elevation, transform, dem_diag = load_and_reproject_dem(tile_paths, study_area)
    slope = compute_slope_degrees(elevation, cfg.DEM_TARGET_RESOLUTION_M)
    pixels = pixels_to_points(elevation, slope, transform)

    terrain, terrain_diag = compute_terrain_features(pixels, grid)
    _assert_all_grid_ids_present(terrain, grid_ids, "terrain_features")

    road_graph_path = cfg.DATA_RAW / "osm" / "osm_road_network_raw.graphml"
    G = ox.load_graphml(road_graph_path)
    edges, road_diag = prepare_road_edges(G, elevation, transform)
    road_grade = compute_road_grade_features(edges, grid)
    _assert_all_grid_ids_present(road_grade, grid_ids, "road_grade_features")

    terrain = terrain.merge(road_grade, on="grid_id", how="left")
    _assert_all_grid_ids_present(terrain, grid_ids, "terrain+road_grade merge")
    assert terrain["grid_id"].is_unique

    qa = run_qa(terrain, dem_diag, road_diag)
    qa["n_cells_with_zero_valid_dem_pixels_pre_merge"] = terrain_diag["n_cells_with_zero_valid_dem_pixels"]

    base = grid[["grid_id", "district", "land_area_m2", "geometry"]]
    terrain_gdf = gpd.GeoDataFrame(base.merge(terrain, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)

    sanity = spatial_sanity_check(terrain_gdf)

    combined = existing_combined.merge(terrain, on="grid_id", how="left", validate="one_to_one")
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=cfg.METRIC_CRS)

    unchanged = verify_prior_features_unchanged(existing_combined, combined)
    assert unchanged, "Phase 3A-3C features changed during the Phase 3D merge — aborting."
    assert len(combined) == 514 and combined["grid_id"].is_unique
    qa["prior_features_unchanged"] = bool(unchanged)

    output_paths = save_outputs(terrain_gdf, combined)
    map_paths = make_validation_maps(combined, has_road_grade=road_diag["n_edges_used_for_grade"] > 0)

    print("\n--- DEM SOURCE ---")
    print(json.dumps({k: v for k, v in dcfg.COPERNICUS_DEM.items()}, indent=2, ensure_ascii=False))

    print("\n--- DEM PREPROCESSING ---")
    print(json.dumps(dem_diag, indent=2, default=str))

    print("\n--- ROAD GRADE FEASIBILITY ---")
    print(json.dumps(road_diag, indent=2))

    print("\n--- QA REPORT ---")
    qa_printable = {k: v for k, v in qa.items() if k not in ("elevation_stats", "slope_stats", "road_grade_stats", "extreme_slope_cells")}
    print(json.dumps(qa_printable, indent=2, default=str))
    print("\nelevation_stats:", json.dumps(qa["elevation_stats"], indent=2))
    print("\nslope_stats:", json.dumps(qa["slope_stats"], indent=2))
    if qa["road_grade_stats"]:
        print("\nroad_grade_stats:", json.dumps(qa["road_grade_stats"], indent=2))

    print("\n--- SPATIAL SANITY CHECK ---")
    print(json.dumps(sanity, indent=2, ensure_ascii=False, default=str))

    print("\n--- OUTPUT FILES ---")
    for k, v in output_paths.items():
        print(f"  {k}: {v}")
    for k, v in map_paths.items():
        print(f"  map[{k}]: {v}")

    full_report = {"dem_source": dcfg.COPERNICUS_DEM, "preprocessing": dem_diag, "qa": qa, "spatial_sanity_check": sanity}
    with open(cfg.DATA_FEATURES / "terrain_qa_report.json", "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nFull QA report saved -> {cfg.DATA_FEATURES / 'terrain_qa_report.json'}")


if __name__ == "__main__":
    main()
