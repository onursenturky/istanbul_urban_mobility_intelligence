"""Phase 3C population allocation: raster -> 500m grid, area-weighted.

Method (a standard areal-weighting / dasymetric-preserving interpolation):
1. Read only the raster window covering the (lightly buffered) study area —
   never load the whole-country file into memory.
2. Vectorize each valid pixel into its exact rectangular footprint polygon
   in the raster's native CRS (WGS84), carrying its population value.
3. Reproject those pixel footprints to the metric CRS (their area is then
   correct in m^2 — this is a vector reprojection, not a raster resample, so
   no population value is ever interpolated/smeared).
4. Intersect every pixel footprint with every grid cell; each intersection
   receives population * (intersection_area / pixel_area) — i.e. a pixel
   split across two cells contributes proportionally to each, and the sum
   over all cells recovers the pixel's full value. This is what preserves
   population mass.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import shapes
from rasterio.windows import from_bounds
from shapely.geometry import shape

from src.utils import config as cfg

WINDOW_BUFFER_M = 200  # margin beyond the study area so edge pixels aren't clipped before reading


def _read_pixels_as_polygons(raster_path, study_area_geom) -> gpd.GeoDataFrame:
    study_area_ll = gpd.GeoSeries([study_area_geom.buffer(WINDOW_BUFFER_M)], crs=cfg.METRIC_CRS).to_crs(
        "EPSG:4326"
    ).iloc[0]

    with rasterio.open(raster_path) as src:
        assert src.crs.to_string() == "EPSG:4326"
        window = from_bounds(*study_area_ll.bounds, transform=src.transform)
        band = src.read(1, window=window)
        window_transform = src.window_transform(window)
        nodata = src.nodata

        valid_mask = np.isfinite(band) & (band != nodata) & (band >= 0)
        n_invalid = int((~valid_mask).sum()) - int((band == nodata).sum())  # NaN/negative beyond declared nodata

        geoms_values = list(shapes(band, mask=valid_mask, transform=window_transform))

    records = [{"population": float(val), "geometry": shape(geom)} for geom, val in geoms_values]
    pixels = gpd.GeoDataFrame(records, crs="EPSG:4326")
    pixels = pixels.to_crs(cfg.METRIC_CRS)
    pixels["pixel_area_m2"] = pixels.geometry.area
    return pixels, {"n_valid_pixels": len(pixels), "n_invalid_or_negative_pixels_beyond_nodata": max(n_invalid, 0)}


def allocate_population_to_grid(
    raster_path, grid: gpd.GeoDataFrame, study_area_geom
) -> tuple[pd.DataFrame, gpd.GeoDataFrame, dict]:
    assert grid.crs.to_string() == cfg.METRIC_CRS

    pixels, read_diag = _read_pixels_as_polygons(raster_path, study_area_geom)

    overlay = gpd.overlay(
        grid[["grid_id", "geometry"]], pixels[["population", "pixel_area_m2", "geometry"]],
        how="intersection", keep_geom_type=True,
    )
    overlay["intersection_area_m2"] = overlay.geometry.area
    overlay["allocated_population"] = (
        overlay["population"] * overlay["intersection_area_m2"] / overlay["pixel_area_m2"]
    )

    per_cell = overlay.groupby("grid_id")["allocated_population"].sum().rename("population")
    result = grid[["grid_id", "land_area_m2"]].merge(per_cell, on="grid_id", how="left")
    result["population"] = result["population"].fillna(0.0)
    result["population_density_km2"] = result["population"] / (result["land_area_m2"] / 1e6)
    result = result.drop(columns=["land_area_m2"])

    # Mass-preservation check: population intersecting the true study-area
    # polygon directly (not routed through the grid) vs. what the grid
    # actually captured. These differ only by the ~0.3% of study-area land
    # the Phase 2 grid didn't retain (cells below the 10% intersection
    # threshold) plus any negligible overlay-geometry rounding.
    study_area_gdf = gpd.GeoDataFrame({"geometry": [study_area_geom]}, crs=cfg.METRIC_CRS)
    sa_overlay = gpd.overlay(
        study_area_gdf, pixels[["population", "pixel_area_m2", "geometry"]], how="intersection"
    )
    sa_overlay["intersection_area_m2"] = sa_overlay.geometry.area
    source_population_total = float(
        (sa_overlay["population"] * sa_overlay["intersection_area_m2"] / sa_overlay["pixel_area_m2"]).sum()
    )
    allocated_population_total = float(result["population"].sum())
    allocation_difference_pct = (
        (allocated_population_total - source_population_total) / source_population_total * 100
        if source_population_total else float("nan")
    )

    diagnostics = {
        **read_diag,
        "source_population_total": source_population_total,
        "allocated_population_total": allocated_population_total,
        "allocation_difference_pct": allocation_difference_pct,
    }
    return result, pixels, diagnostics
