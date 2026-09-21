"""Phase 3A building-footprint feature engineering.

building_count / mean_building_footprint_m2 assign each building to exactly
one grid cell via its representative point (a building never counted in two
cells). building_footprint_area_m2 instead uses each building's true clipped
intersection with a cell, so a building straddling a boundary contributes
only its actual in-cell portion to each side, never its full area to both.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from src.utils import config as cfg


def compute_building_features(
    buildings_raw: gpd.GeoDataFrame, grid_gdf: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, dict]:
    assert grid_gdf.crs.to_string() == cfg.METRIC_CRS, "grid must already be in the metric CRS"

    gdf = buildings_raw.to_crs(cfg.METRIC_CRS).copy()
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]

    invalid_before = int((~gdf.geometry.is_valid).sum())
    if invalid_before:
        gdf["geometry"] = gdf.geometry.make_valid()
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"]) & ~gdf.geometry.is_empty]

    gdf["building_area_m2"] = gdf.geometry.area

    rep_points = gdf.copy()
    rep_points["geometry"] = rep_points.geometry.representative_point()
    joined = gpd.sjoin(
        rep_points[["building_area_m2", "geometry"]],
        grid_gdf[["grid_id", "geometry"]],
        predicate="intersects",
        how="inner",
    )
    count_stats = joined.groupby("grid_id").agg(
        building_count=("building_area_m2", "size"),
        mean_building_footprint_m2=("building_area_m2", "mean"),
    )

    # Vectorized clip via gpd.overlay (spatial-indexed internally) instead
    # of a per-cell Python loop — identical semantics (each building's true
    # clipped in-cell area, summed per cell). See
    # data/processed/citywide/pipeline_optimization_validation.json for the
    # old-vs-new equivalence check on the pilot grid.
    overlay = gpd.overlay(
        grid_gdf[["grid_id", "geometry"]], gdf[["geometry"]], how="intersection", keep_geom_type=True
    )
    overlay["area_m2"] = overlay.geometry.area
    area_df = overlay.groupby("grid_id")["area_m2"].sum().rename("building_footprint_area_m2").reset_index()

    result = grid_gdf[["grid_id", "land_area_m2"]].merge(count_stats, on="grid_id", how="left")
    result = result.merge(area_df, on="grid_id", how="left")
    result["building_count"] = result["building_count"].fillna(0).astype(int)
    result["mean_building_footprint_m2"] = result["mean_building_footprint_m2"].fillna(0.0)
    result["building_footprint_area_m2"] = result["building_footprint_area_m2"].fillna(0.0)
    result["building_coverage_ratio"] = result["building_footprint_area_m2"] / result["land_area_m2"]

    n_over_coverage = int((result["building_coverage_ratio"] > 1.0).sum())
    result = result.drop(columns=["land_area_m2"])

    diagnostics = {
        "n_buildings_raw": int(len(buildings_raw)),
        "invalid_geometries_repaired": invalid_before,
        "n_buildings_used": int(len(gdf)),
        # coverage_ratio > 100% is only geometrically possible from
        # overlapping/duplicate building footprints in the source data.
        "n_cells_with_coverage_ratio_over_100pct": n_over_coverage,
    }
    return result, diagnostics
