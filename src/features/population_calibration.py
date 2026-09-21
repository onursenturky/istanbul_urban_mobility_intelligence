"""Population audit: district-constrained calibration of the WorldPop grid.

Rationale (see the audit report for full evidence): the raster identity,
the area-weighted allocation pipeline, and the OSM district boundary areas
were all independently verified correct. The remaining district-level gap
against official TÜİK/İBB ADNKS 2020 totals therefore reflects genuine
divergence between WorldPop's dasymetric model and registered population,
concentrated in specific high-rise residential clusters (e.g. Kirazlıtepe,
Üsküdar) — not a processing error. A district-constrained calibration is
therefore a defensible way to offer a second, officially-anchored estimate
while preserving WorldPop's within-district spatial pattern, WITHOUT
overwriting the raw WorldPop feature.

calibration_factor_d = official_population_d / worldpop_population_d

is computed against the RAW WorldPop total already assigned to each
district by the Phase 2 grid (i.e. summed over grid cells whose primary
district is d) — this is the exact mass the calibration needs to rescale to
match the official total for that district's set of grid cells.

For grid cells that straddle a district boundary, the cell's pixel mass is
split by district BEFORE calibration (each district-piece scaled by its own
factor) and summed back — never by applying one district's factor to a
cell's full population. This is done via a three-way overlay: pixel x grid
x district, not a two-step pixel x grid then a per-cell district lookup.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from src.features.population_features import _read_pixels_as_polygons
from src.utils import config as cfg


def compute_calibration_factors(pop_features: pd.DataFrame, grid: gpd.GeoDataFrame, official: dict) -> dict:
    merged = grid[["grid_id", "district"]].merge(pop_features[["grid_id", "population"]], on="grid_id")
    raw_by_district = merged.groupby("district")["population"].sum().to_dict()
    factors = {}
    for district, official_pop in official.items():
        raw = raw_by_district.get(district, 0.0)
        factors[district] = {
            "raw_worldpop_district_total": raw,
            "official_district_total": official_pop,
            "calibration_factor": official_pop / raw if raw else float("nan"),
        }
    return factors


def calibrate_population_to_grid(
    raster_path, grid: gpd.GeoDataFrame, study_area_geom, districts: gpd.GeoDataFrame, factors: dict
) -> tuple[pd.DataFrame, dict]:
    assert grid.crs.to_string() == cfg.METRIC_CRS

    pixels, _ = _read_pixels_as_polygons(raster_path, study_area_geom)

    # Three-way split: pixel x grid x district, in one pass, so a pixel that
    # straddles both a grid-cell edge AND a district boundary is divided
    # correctly on both axes before any calibration factor is applied.
    grid_x_pixel = gpd.overlay(
        grid[["grid_id", "geometry"]], pixels[["population", "pixel_area_m2", "geometry"]],
        how="intersection", keep_geom_type=True,
    )
    three_way = gpd.overlay(
        grid_x_pixel, districts[["district", "geometry"]], how="intersection", keep_geom_type=True
    )
    three_way["piece_area_m2"] = three_way.geometry.area
    three_way["piece_population_raw"] = (
        three_way["population"] * three_way["piece_area_m2"] / three_way["pixel_area_m2"]
    )
    three_way["calibration_factor"] = three_way["district"].map(
        {d: v["calibration_factor"] for d, v in factors.items()}
    )
    # Pieces falling in a district with no official figure (shouldn't occur
    # for our 3-district study area, but guarded defensively) pass through
    # uncalibrated rather than being silently dropped.
    three_way["calibration_factor"] = three_way["calibration_factor"].fillna(1.0)
    three_way["piece_population_calibrated"] = (
        three_way["piece_population_raw"] * three_way["calibration_factor"]
    )

    per_cell = three_way.groupby("grid_id").agg(
        population_calibrated=("piece_population_calibrated", "sum"),
        population_raw_via_threeway=("piece_population_raw", "sum"),
    )
    result = grid[["grid_id", "land_area_m2"]].merge(per_cell, on="grid_id", how="left")
    result["population_calibrated"] = result["population_calibrated"].fillna(0.0)
    result["population_raw_via_threeway"] = result["population_raw_via_threeway"].fillna(0.0)
    result["population_density_calibrated_km2"] = result["population_calibrated"] / (result["land_area_m2"] / 1e6)
    result = result.drop(columns=["land_area_m2"])

    # Identify how many grid cells actually straddle >1 district (used the
    # split logic for real), independent of Phase 2's "ambiguous" flag.
    cells_per_district_count = three_way.groupby("grid_id")["district"].nunique()
    n_cells_spanning_multiple_districts = int((cells_per_district_count > 1).sum())

    diagnostics = {
        "n_cells_spanning_multiple_districts_in_pixel_overlay": n_cells_spanning_multiple_districts,
    }
    return result[["grid_id", "population_calibrated", "population_density_calibrated_km2"]], diagnostics
