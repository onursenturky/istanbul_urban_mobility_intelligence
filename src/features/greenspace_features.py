"""Phase 3A green-space and land-use feature engineering.

Green space is pooled across leisure/landuse/natural tags and dissolved
(union_all) into one layer before intersecting with grid cells, so ground
double-mapped under two tagging schemes is not counted twice. Each land-use
composition category is dissolved separately for the same reason. Land-use
coverage (the share of a cell's land area actually classified by any of
these polygons) is reported explicitly rather than assuming full coverage.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from src.features import osm_tag_config as tags
from src.utils import config as cfg


def _select_green(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    mask = pd.Series(False, index=gdf.index)
    if "leisure" in gdf.columns:
        mask |= gdf["leisure"].isin(tags.GREEN_LEISURE_VALUES)
    if "landuse" in gdf.columns:
        mask |= gdf["landuse"].isin(tags.GREEN_LANDUSE_VALUES)
    if "natural" in gdf.columns:
        mask |= gdf["natural"].isin(tags.GREEN_NATURAL_VALUES)
    return gdf[mask]


def _area_per_cell(grid_geom: gpd.GeoSeries, layer_union) -> pd.Series:
    if layer_union is None or layer_union.is_empty:
        return pd.Series(0.0, index=grid_geom.index)
    return grid_geom.intersection(layer_union).area


def compute_greenspace_features(
    landuse_raw: gpd.GeoDataFrame, grid_gdf: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, dict]:
    assert grid_gdf.crs.to_string() == cfg.METRIC_CRS, "grid must already be in the metric CRS"

    gdf = landuse_raw.to_crs(cfg.METRIC_CRS).copy()
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    invalid_before = int((~gdf.geometry.is_valid).sum())
    if invalid_before:
        gdf["geometry"] = gdf.geometry.make_valid()
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"]) & ~gdf.geometry.is_empty]

    green = _select_green(gdf)
    green_union = green.union_all() if len(green) else None

    landuse_layers = {}
    covered_parts = []
    for out_col, value in tags.LANDUSE_COMPOSITION_VALUES.items():
        subset = gdf[gdf["landuse"] == value] if "landuse" in gdf.columns else gdf.iloc[0:0]
        layer_union = subset.union_all() if len(subset) else None
        landuse_layers[out_col] = layer_union
        if layer_union is not None and not layer_union.is_empty:
            covered_parts.append(layer_union)
    any_landuse_union = (
        gpd.GeoSeries(covered_parts, crs=cfg.METRIC_CRS).union_all() if covered_parts else None
    )

    result = grid_gdf[["grid_id", "land_area_m2"]].copy()
    result["green_area_m2"] = _area_per_cell(grid_gdf.geometry, green_union)
    result["green_area_ratio"] = result["green_area_m2"] / result["land_area_m2"]

    for out_col, layer_union in landuse_layers.items():
        result[out_col] = _area_per_cell(grid_gdf.geometry, layer_union) / result["land_area_m2"]

    result["landuse_data_coverage_pct"] = (
        _area_per_cell(grid_gdf.geometry, any_landuse_union) / result["land_area_m2"] * 100
    )

    mean_coverage = float(result["landuse_data_coverage_pct"].mean())
    entropy_computed = mean_coverage >= cfg.LANDUSE_ENTROPY_MIN_MEAN_COVERAGE_PCT
    if entropy_computed:
        import numpy as np

        ratio_cols = list(tags.LANDUSE_COMPOSITION_VALUES.keys())

        def _entropy(row):
            vals = row[ratio_cols].to_numpy(dtype=float)
            total = vals.sum()
            if total == 0:
                return 0.0
            p = vals[vals > 0] / total
            return float(-(p * np.log2(p)).sum())

        result["landuse_entropy"] = result.apply(_entropy, axis=1)

    result = result.drop(columns=["land_area_m2"])

    diagnostics = {
        "invalid_landuse_geometries_repaired": invalid_before,
        "n_green_polygons": int(len(green)),
        "mean_landuse_data_coverage_pct": mean_coverage,
        "landuse_entropy_computed": entropy_computed,
        "landuse_entropy_min_coverage_threshold_pct": cfg.LANDUSE_ENTROPY_MIN_MEAN_COVERAGE_PCT,
    }
    return result, diagnostics
