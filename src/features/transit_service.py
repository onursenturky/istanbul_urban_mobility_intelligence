"""Phase 3B service-intensity and route-diversity features.

Route diversity (routes_serving_grid, unique_bus_routes, unique_rail_lines)
uses route topology from both GTFS feeds — reasonably robust even against a
stale snapshot, since a route's basic existence changes far less often than
its exact timetable, though newer lines/extensions opened after each feed's
last-modified date would be missing (documented limitation).

bus_departures_per_day / bus_departures_peak_hour are computed ONLY from the
İETT feed (bus + metrobüs), because it is the only GTFS with a still-valid
calendar.csv service window as of the retrieval date (service_id=0,
"WEEKDAYS", valid through 2026-12-31). The main GTFS (metro/tram/rail/ferry)
is deliberately NOT used for departure counts: every calendar.csv entry in
that feed had already expired (mostly end_date 2024-12-31, some as early as
2019) as of the 2026-09-18 retrieval date, so it cannot support a defensible
current-day departure count. There is intentionally no rail/tram/ferry
departure-frequency column in the output.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from src.features import transit_tag_config as tcfg
from src.features.transit_infrastructure import load_gtfs_csv
from src.utils import config as cfg


def compute_route_diversity(stops: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> pd.DataFrame:
    assert grid.crs.to_string() == cfg.METRIC_CRS

    joined = gpd.sjoin(
        stops[["mode", "route_ids", "geometry"]],
        grid[["grid_id", "geometry"]],
        predicate="intersects",
        how="inner",
    )

    def _union(series: pd.Series) -> set:
        out: set = set()
        for s in series:
            out |= s
        return out

    per_cell_all = joined.groupby("grid_id")["route_ids"].apply(_union)
    per_cell_bus = joined[joined["mode"] == "bus"].groupby("grid_id")["route_ids"].apply(_union)
    per_cell_rail = (
        joined[joined["mode"].isin(("metro", "tram", "rail"))].groupby("grid_id")["route_ids"].apply(_union)
    )

    result = grid[["grid_id"]].copy()
    result["routes_serving_grid"] = result["grid_id"].map(per_cell_all).apply(lambda s: len(s) if isinstance(s, set) else 0)
    result["unique_bus_routes"] = result["grid_id"].map(per_cell_bus).apply(lambda s: len(s) if isinstance(s, set) else 0)
    result["unique_rail_lines"] = result["grid_id"].map(per_cell_rail).apply(lambda s: len(s) if isinstance(s, set) else 0)
    return result


def compute_bus_departures(
    iett_gtfs_dir, stops: gpd.GeoDataFrame, grid: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, dict]:
    assert grid.crs.to_string() == cfg.METRIC_CRS
    feed_cfg = tcfg.IETT_GTFS

    trips = load_gtfs_csv(iett_gtfs_dir, "trips", feed_cfg)
    stop_times = load_gtfs_csv(
        iett_gtfs_dir, "stop_times", feed_cfg, usecols=["trip_id", "stop_id", "arrival_time", "departure_time"]
    )

    weekday_trip_ids = set(trips.loc[trips["service_id"] == feed_cfg["weekday_service_id"], "trip_id"])
    weekday_st = stop_times[stop_times["trip_id"].isin(weekday_trip_ids)]

    daily = weekday_st.groupby("stop_id").size().rename("bus_departures_per_day")
    time_col = weekday_st["departure_time"].fillna(weekday_st["arrival_time"]).astype(str)
    peak = weekday_st[time_col.str.startswith(cfg.PEAK_HOUR_START)].groupby("stop_id").size().rename(
        "bus_departures_peak_hour"
    )

    bus_stops = stops[stops["mode"].isin(("bus", "metrobus")) & (stops["source_feed"] == "iett_gtfs")].copy()
    bus_stops["bus_departures_per_day"] = bus_stops["raw_stop_id"].map(daily).fillna(0)
    bus_stops["bus_departures_peak_hour"] = bus_stops["raw_stop_id"].map(peak).fillna(0)

    joined = gpd.sjoin(
        bus_stops[["bus_departures_per_day", "bus_departures_peak_hour", "geometry"]],
        grid[["grid_id", "geometry"]],
        predicate="intersects",
        how="inner",
    )
    per_cell = joined.groupby("grid_id")[["bus_departures_per_day", "bus_departures_peak_hour"]].sum()

    result = grid[["grid_id"]].merge(per_cell, on="grid_id", how="left")
    result["bus_departures_per_day"] = result["bus_departures_per_day"].fillna(0).astype(int)
    result["bus_departures_peak_hour"] = result["bus_departures_peak_hour"].fillna(0).astype(int)

    diagnostics = {
        "weekday_service_id": feed_cfg["weekday_service_id"],
        "n_weekday_trips": len(weekday_trip_ids),
        "n_weekday_stop_time_rows": int(len(weekday_st)),
        "peak_hour_window": cfg.PEAK_HOUR_LABEL,
        "total_bus_departures_per_day_citywide_at_matched_stops": int(daily.sum()),
    }
    return result, diagnostics
