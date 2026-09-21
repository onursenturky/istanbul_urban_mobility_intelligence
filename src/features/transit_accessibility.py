"""Phase 3B station-count and accessibility feature engineering.

Two deliberately different representative locations are used, per mode:

- *_count / total_transit_stop_count: a stop is assigned to the grid cell
  whose POLYGON contains it (area-based membership — same convention as the
  Phase 3A POI/building counts). This answers "is a station physically
  located here."

- distance_to_nearest_*_m, transit_stops_within_*m, rail_stations_within_1000m,
  number_of_transit_modes_accessible: computed from the grid CENTROID against
  the full CITY-WIDE stop set (never clipped to the study area) — this
  answers "how close is this location to transit," and is why a station just
  outside the three districts still counts as the nearest station for a
  boundary cell.

These two families are not interchangeable and are documented as such in
transit_feature_dictionary.py.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from src.features import transit_tag_config as tcfg
from src.utils import config as cfg

MODE_COUNT_COLS = {
    "metro": "metro_station_count",
    "tram": "tram_station_count",
    "rail": "rail_station_count",
    "metrobus": "metrobus_station_count",
    "bus": "bus_stop_count",
    "ferry": "ferry_terminal_count",
}

MODE_DISTANCE_COLS = {
    "metro": "distance_to_nearest_metro_m",
    "tram": "distance_to_nearest_tram_m",
    "rail": "distance_to_nearest_rail_m",
    "metrobus": "distance_to_nearest_metrobus_m",
    "bus": "distance_to_nearest_bus_stop_m",
    "ferry": "distance_to_nearest_ferry_m",
}

RAIL_LIKE_MODES = ("metro", "tram", "rail")


def compute_station_counts(stops: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> pd.DataFrame:
    assert grid.crs.to_string() == cfg.METRIC_CRS

    joined = gpd.sjoin(
        stops[["mode", "geometry"]], grid[["grid_id", "geometry"]], predicate="intersects", how="inner"
    )
    counts = (
        joined.groupby(["grid_id", "mode"]).size().unstack(fill_value=0)
        .reindex(columns=tcfg.ALL_MODES, fill_value=0)
        .rename(columns=MODE_COUNT_COLS)
        .reset_index()
    )

    result = grid[["grid_id"]].merge(counts, on="grid_id", how="left")
    for c in MODE_COUNT_COLS.values():
        result[c] = result[c].fillna(0).astype(int)
    result["total_transit_stop_count"] = result[list(MODE_COUNT_COLS.values())].sum(axis=1)
    return result


def _nearest_distance(centroid_xy: np.ndarray, stop_xy: np.ndarray) -> np.ndarray:
    if len(stop_xy) == 0:
        return np.full(len(centroid_xy), np.nan)
    dist, _ = cKDTree(stop_xy).query(centroid_xy, k=1)
    return dist


def _count_within(centroid_xy: np.ndarray, stop_xy: np.ndarray, radius: float) -> np.ndarray:
    if len(stop_xy) == 0:
        return np.zeros(len(centroid_xy), dtype=int)
    tree = cKDTree(stop_xy)
    return np.array([len(tree.query_ball_point(pt, r=radius)) for pt in centroid_xy])


def compute_distance_and_accessibility_features(
    stops: gpd.GeoDataFrame, grid: gpd.GeoDataFrame
) -> pd.DataFrame:
    assert grid.crs.to_string() == cfg.METRIC_CRS

    centroids = grid.geometry.centroid
    centroid_xy = np.column_stack([centroids.x.to_numpy(), centroids.y.to_numpy()])
    result = grid[["grid_id"]].copy()

    mode_xy = {}
    for mode in tcfg.ALL_MODES:
        sub = stops[stops["mode"] == mode]
        xy = np.column_stack([sub.geometry.x.to_numpy(), sub.geometry.y.to_numpy()]) if len(sub) else np.empty((0, 2))
        mode_xy[mode] = xy
        result[MODE_DISTANCE_COLS[mode]] = _nearest_distance(centroid_xy, xy)

    all_xy = np.column_stack([stops.geometry.x.to_numpy(), stops.geometry.y.to_numpy()])
    result["distance_to_nearest_transit_m"] = _nearest_distance(centroid_xy, all_xy)

    result["transit_stops_within_500m"] = _count_within(centroid_xy, all_xy, 500)
    result["transit_stops_within_1000m"] = _count_within(centroid_xy, all_xy, 1000)
    result["bus_stops_within_500m"] = _count_within(centroid_xy, mode_xy["bus"], 500)

    rail_parts = [mode_xy[m] for m in RAIL_LIKE_MODES if len(mode_xy[m])]
    rail_xy = np.vstack(rail_parts) if rail_parts else np.empty((0, 2))
    # Renamed from rail_stations_within_1000m: this pools metro + tram + rail
    # (fixed-guideway modes), so "rail" alone was misleading. The old name is
    # kept as a deprecated alias (identical values) for backward
    # compatibility — see transit_feature_dictionary.py.
    result["fixed_guideway_stations_within_1000m"] = _count_within(centroid_xy, rail_xy, 1000)
    result["rail_stations_within_1000m"] = result["fixed_guideway_stations_within_1000m"]

    radius = cfg.TRANSIT_ACCESSIBILITY_RADIUS_M
    accessible = pd.DataFrame(
        {mode: (result[MODE_DISTANCE_COLS[mode]] <= radius) for mode in tcfg.ALL_MODES}
    )
    result["number_of_transit_modes_accessible"] = accessible.sum(axis=1).astype(int)

    return result
