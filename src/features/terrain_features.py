"""Phase 3D terrain preprocessing and elevation/slope feature engineering.

Preprocessing: mosaic the two Copernicus DEM tiles, clip to the buffered
study area, reproject to EPSG:32635 with bilinear resampling (the standard
choice for continuous fields like elevation — nearest-neighbor would
introduce blocky artifacts that corrupt the slope calculation done
afterward). Slope is then computed on the metric-CRS grid via Horn's method
(the standard 3x3-kernel algorithm used by GDAL/QGIS/ArcGIS), so cellsize is
a true, uniform distance in meters rather than degrees.

Per-cell statistics use PIXEL-CENTER zonal membership (each DEM pixel's
center point is spatially joined to the one grid cell containing it), not
area-weighting. This is the standard, defensible convention for continuous
field statistics (mean/median/min/max/std) — unlike population, elevation is
not an additively-conserved quantity, so there is no "mass" to preserve
through area-weighting. Because grid cells are already clipped to land
(Phase 2), any DEM pixel center that falls over water simply does not join
to any cell — coastal cells are unaffected by sea pixels by construction.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry import Point

from src.utils import config as cfg


def load_and_reproject_dem(tile_paths: list, study_area_geom) -> tuple[np.ndarray, "rasterio.Affine", dict]:
    srcs = [rasterio.open(p) for p in tile_paths]
    mosaic, mosaic_transform = merge(srcs)
    mosaic_crs = srcs[0].crs
    for s in srcs:
        s.close()
    mosaic = mosaic[0]  # single band

    dst_crs = cfg.METRIC_CRS
    bounds_ll = gpd.GeoSeries([study_area_geom.buffer(cfg.DEM_BUFFER_M)], crs=cfg.METRIC_CRS).to_crs(
        mosaic_crs
    ).iloc[0].bounds

    # Restrict the reprojection to a window around the study area rather
    # than warping the full two-tile mosaic (a ~7200x3600 px array).
    from rasterio.windows import from_bounds

    window = from_bounds(*bounds_ll, transform=mosaic_transform)
    window = window.round_lengths(pixel_precision=0).round_offsets(pixel_precision=0)
    row_off, col_off = int(window.row_off), int(window.col_off)
    row_end, col_end = row_off + int(window.height), col_off + int(window.width)
    sub = mosaic[max(row_off, 0): row_end, max(col_off, 0): col_end]
    sub_transform = rasterio.windows.transform(window, mosaic_transform)

    dst_transform, width, height = calculate_default_transform(
        mosaic_crs, dst_crs, sub.shape[1], sub.shape[0],
        *rasterio.transform.array_bounds(sub.shape[0], sub.shape[1], sub_transform),
        resolution=cfg.DEM_TARGET_RESOLUTION_M,
    )
    dst = np.full((height, width), np.nan, dtype=np.float32)
    reproject(
        source=sub,
        destination=dst,
        src_transform=sub_transform,
        src_crs=mosaic_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.bilinear,
        src_nodata=None,
        dst_nodata=np.nan,
    )

    diagnostics = {
        "mosaic_shape": mosaic.shape,
        "reprojected_shape": dst.shape,
        "reprojected_resolution_m": cfg.DEM_TARGET_RESOLUTION_M,
        "resampling_method": "bilinear",
        "n_valid_pixels": int(np.isfinite(dst).sum()),
        "n_nodata_pixels": int((~np.isfinite(dst)).sum()),
    }
    return dst, dst_transform, diagnostics


def compute_slope_degrees(elevation: np.ndarray, cellsize_m: float) -> np.ndarray:
    """Horn's method (GDAL/QGIS/ArcGIS default 3x3-kernel slope algorithm)."""
    z = elevation.astype(np.float64)
    valid = np.isfinite(z)
    z_filled = np.where(valid, z, 0.0)
    # Edge-pad by replication so the 3x3 kernel is defined at the array border
    # (the DEM_BUFFER_M margin means the actual study area is never at this
    # padded edge, so this padding never affects a real grid cell).
    zp = np.pad(z_filled, 1, mode="edge")
    vp = np.pad(valid, 1, mode="edge")

    a, b, c = zp[:-2, :-2], zp[:-2, 1:-1], zp[:-2, 2:]
    d, f = zp[1:-1, :-2], zp[1:-1, 2:]
    g, h, i = zp[2:, :-2], zp[2:, 1:-1], zp[2:, 2:]

    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * cellsize_m)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * cellsize_m)
    slope_deg = np.degrees(np.arctan(np.sqrt(dzdx**2 + dzdy**2)))

    # A pixel's slope is invalid if it or any of its 8 neighbors was nodata.
    neighbor_valid = np.ones_like(valid)
    vpad = vp.astype(np.float64)
    window_sum = (
        vpad[:-2, :-2] + vpad[:-2, 1:-1] + vpad[:-2, 2:]
        + vpad[1:-1, :-2] + vpad[1:-1, 1:-1] + vpad[1:-1, 2:]
        + vpad[2:, :-2] + vpad[2:, 1:-1] + vpad[2:, 2:]
    )
    neighbor_valid = window_sum == 9
    slope_deg = np.where(neighbor_valid, slope_deg, np.nan)
    return slope_deg.astype(np.float32)


def pixels_to_points(elevation: np.ndarray, slope: np.ndarray, transform) -> gpd.GeoDataFrame:
    rows, cols = np.where(np.isfinite(elevation) & np.isfinite(slope))
    xs, ys = rasterio.transform.xy(transform, rows, cols)
    return gpd.GeoDataFrame(
        {"elevation_m": elevation[rows, cols], "slope_deg": slope[rows, cols]},
        geometry=[Point(x, y) for x, y in zip(xs, ys)],
        crs=cfg.METRIC_CRS,
    )


def compute_terrain_features(pixels: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> tuple[pd.DataFrame, dict]:
    assert grid.crs.to_string() == cfg.METRIC_CRS

    joined = gpd.sjoin(pixels, grid[["grid_id", "geometry"]], predicate="intersects", how="inner")

    elev_stats = joined.groupby("grid_id")["elevation_m"].agg(
        mean_elevation_m="mean", median_elevation_m="median", min_elevation_m="min",
        max_elevation_m="max", elevation_std_m="std",
    )
    elev_stats["elevation_range_m"] = elev_stats["max_elevation_m"] - elev_stats["min_elevation_m"]

    slope_stats = joined.groupby("grid_id")["slope_deg"].agg(
        mean_slope_deg="mean", median_slope_deg="median", max_slope_deg="max", slope_std_deg="std",
    )

    bins, labels = cfg.SLOPE_BINS_DEG, cfg.SLOPE_BIN_LABELS
    joined["slope_bin"] = pd.cut(joined["slope_deg"], bins=bins, labels=labels, right=False)
    bin_counts = joined.groupby(["grid_id", "slope_bin"], observed=False).size().unstack(fill_value=0)
    bin_pct = bin_counts.div(bin_counts.sum(axis=1), axis=0) * 100
    bin_pct = bin_pct.reindex(columns=labels, fill_value=0.0)

    n_valid_pixels = joined.groupby("grid_id").size().rename("n_valid_dem_pixels")

    result = grid[["grid_id"]].merge(elev_stats, on="grid_id", how="left")
    result = result.merge(slope_stats, on="grid_id", how="left")
    result = result.merge(bin_pct, on="grid_id", how="left")
    result = result.merge(n_valid_pixels, on="grid_id", how="left")
    result["n_valid_dem_pixels"] = result["n_valid_dem_pixels"].fillna(0).astype(int)

    # Cells with zero valid DEM pixels keep NaN across all stat columns
    # rather than a fabricated 0 (which would misread as "sea level" /
    # "flat") — reported explicitly in QA and handled by the orchestrator.
    n_cells_no_valid_pixels = int((result["n_valid_dem_pixels"] == 0).sum())

    diagnostics = {
        "n_cells_with_zero_valid_dem_pixels": n_cells_no_valid_pixels,
        "n_pixel_points_total": len(pixels),
    }
    return result, diagnostics
