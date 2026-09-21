"""Phase 3B transit infrastructure loading and mode classification.

Loads both GTFS feeds, classifies every stop into one of the six required
modes via stop -> trip -> route -> (agency, route_type)/name-pattern joins
(see transit_tag_config.py for the exact rules), deduplicates near-identical
physical stops, and produces one clean GeoDataFrame of city-wide transit
stops with a `mode` column. This feeds both the infrastructure/accessibility
features (transit_infrastructure) and the service-intensity features
(transit_service).
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from src.features import transit_tag_config as tcfg
from src.utils import config as cfg


def load_gtfs_csv(feed_dir, name, feed_cfg, **kwargs):
    path = feed_dir / f"{name}.csv"
    return pd.read_csv(
        path, encoding=feed_cfg["encoding"], sep=feed_cfg["delimiter"], dtype=str, **kwargs
    )


def _fix_ibb_mangled_coordinate(raw: str, integer_digits: int) -> float | None:
    """İETT's stops.csv exports stop_lat/stop_lon with thousands-separator
    corruption for every row (e.g. '410.191.700.005.564' instead of
    '41.0191700005564') — almost certainly a Turkish-locale spreadsheet
    re-formatting a float as a grouped integer on export. Strips the dots and
    reinserts a single decimal point after `integer_digits` digits (2, since
    Istanbul lat/lon both have a 2-digit integer part). Returns None for
    anything that still doesn't parse (genuinely garbled rows)."""
    s = str(raw).strip()
    if s.count(".") <= 1:
        try:
            return float(s)
        except ValueError:
            return None
    digits = s.replace(".", "")
    if not digits.isdigit() or len(digits) <= integer_digits:
        return None
    try:
        return float(digits[:integer_digits] + "." + digits[integer_digits:])
    except ValueError:
        return None


# Generous bounding box for Istanbul province — anything outside this after
# the fix above is treated as an unrecoverable/invalid coordinate.
_ISTANBUL_LAT_RANGE = (39.5, 42.0)
_ISTANBUL_LON_RANGE = (27.0, 30.5)


def _stop_route_map(stop_times: pd.DataFrame, trips: pd.DataFrame) -> pd.Series:
    st = stop_times[["trip_id", "stop_id"]].drop_duplicates()
    merged = st.merge(trips[["trip_id", "route_id"]], on="trip_id", how="left")
    return merged.groupby("stop_id")["route_id"].apply(lambda s: set(s.dropna()))


def load_main_gtfs_stops(feed_dir) -> tuple[gpd.GeoDataFrame, dict]:
    feed_cfg = tcfg.MAIN_GTFS
    agency = load_gtfs_csv(feed_dir, "agency", feed_cfg)
    routes = load_gtfs_csv(feed_dir, "routes", feed_cfg)
    stops = load_gtfs_csv(feed_dir, "stops", feed_cfg)
    trips = load_gtfs_csv(feed_dir, "trips", feed_cfg)
    stop_times = load_gtfs_csv(feed_dir, "stop_times", feed_cfg)

    routes = routes.copy()
    routes["mode"] = routes.apply(
        lambda r: tcfg.MAIN_MODE_RULES.get((r.get("agency_id"), r.get("route_type"))), axis=1
    )
    in_scope_routes = routes[routes["mode"].notna()]
    n_routes_out_of_scope = int(routes["mode"].isna().sum())

    stop_routes = _stop_route_map(stop_times, trips)
    route_mode = in_scope_routes.set_index("route_id")["mode"]

    n_stops_raw = len(stops)
    stops = stops[stops["location_type"].isin(["0", "", None]) | stops["location_type"].isna()].copy()

    rows = []
    n_no_matching_route = 0
    for _, s in stops.iterrows():
        route_ids = stop_routes.get(s["stop_id"], set())
        modes = {route_mode.get(rid) for rid in route_ids} - {None}
        if not modes:
            n_no_matching_route += 1
            continue
        for m in modes:
            rows.append(
                {
                    "stop_id": f"main_{s['stop_id']}",
                    "raw_stop_id": s["stop_id"],
                    "stop_name": s["stop_name"],
                    "mode": m,
                    "route_ids": {f"main_{rid}" for rid in (route_ids & set(route_mode.index))},
                    "lat": float(s["stop_lat"]),
                    "lon": float(s["stop_lon"]),
                    "source_feed": "main_gtfs",
                }
            )

    gdf = gpd.GeoDataFrame(
        rows, geometry=[Point(r["lon"], r["lat"]) for r in rows], crs=cfg.STORAGE_CRS
    )
    diagnostics = {
        "n_stops_raw": n_stops_raw,
        "n_stops_after_location_type_filter": len(stops),
        "n_stops_with_no_in_scope_route": n_no_matching_route,
        "n_routes_out_of_scope": n_routes_out_of_scope,
        "n_stop_mode_rows": len(gdf),
    }
    return gdf, diagnostics


def load_iett_gtfs_stops(feed_dir) -> tuple[gpd.GeoDataFrame, dict]:
    feed_cfg = tcfg.IETT_GTFS
    routes = load_gtfs_csv(feed_dir, "routes", feed_cfg)
    stops = load_gtfs_csv(feed_dir, "stops", feed_cfg)
    trips = load_gtfs_csv(feed_dir, "trips", feed_cfg)
    stop_times = load_gtfs_csv(feed_dir, "stop_times", feed_cfg, usecols=["trip_id", "stop_id"])

    routes = routes.copy()
    routes["mode"] = routes["route_long_name"].fillna("").str.lower().apply(
        lambda name: "metrobus" if tcfg.METROBUS_NAME_MARKER in name else "bus"
    )
    route_mode = routes.set_index("route_id")["mode"]

    stop_routes = _stop_route_map(stop_times, trips)

    n_stops_raw = len(stops)
    location_type_col = stops["location_type"] if "location_type" in stops.columns else pd.Series("0", index=stops.index)
    stops = stops[location_type_col.isin(["0", "", None]) | location_type_col.isna()].copy()

    stops["_lat"] = stops["stop_lat"].apply(lambda v: _fix_ibb_mangled_coordinate(v, 2))
    stops["_lon"] = stops["stop_lon"].apply(lambda v: _fix_ibb_mangled_coordinate(v, 2))
    valid_coord = (
        stops["_lat"].between(*_ISTANBUL_LAT_RANGE) & stops["_lon"].between(*_ISTANBUL_LON_RANGE)
    )
    n_invalid_coords = int((~valid_coord).sum())
    stops = stops[valid_coord].copy()

    rows = []
    n_no_matching_route = 0
    for _, s in stops.iterrows():
        route_ids = stop_routes.get(s["stop_id"], set())
        modes = {route_mode.get(rid) for rid in route_ids} - {None}
        if not modes:
            n_no_matching_route += 1
            continue
        for m in modes:
            rows.append(
                {
                    "stop_id": f"iett_{s['stop_id']}",
                    "raw_stop_id": s["stop_id"],
                    "stop_name": s.get("stop_name", ""),
                    "mode": m,
                    "route_ids": {f"iett_{rid}" for rid in (route_ids & set(route_mode.index))},
                    "lat": s["_lat"],
                    "lon": s["_lon"],
                    "source_feed": "iett_gtfs",
                }
            )

    gdf = gpd.GeoDataFrame(
        rows, geometry=[Point(r["lon"], r["lat"]) for r in rows], crs=cfg.STORAGE_CRS
    )
    diagnostics = {
        "n_stops_raw": n_stops_raw,
        "n_stops_after_location_type_filter": len(stops) + n_invalid_coords,
        "n_stops_with_mangled_coordinates_recovered": len(stops),
        "n_stops_with_unrecoverable_invalid_coordinates": n_invalid_coords,
        "n_stops_with_no_in_scope_route": n_no_matching_route,
        "n_stop_mode_rows": len(gdf),
    }
    return gdf, diagnostics


def dedup_stops(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, int]:
    """Two stops of the same mode within STOP_DEDUP_DISTANCE_M are the same
    physical stop (e.g. duplicate platform entries); keep one."""
    gdf = gdf.copy()
    gdf["_drop"] = False
    for _, group in gdf.groupby("mode"):
        idx = group.index.to_numpy()
        coords = group.geometry
        sindex = group.sindex
        seen = set()
        for i in idx:
            if i in seen or gdf.at[i, "_drop"]:
                continue
            buf = coords.loc[i].buffer(tcfg.STOP_DEDUP_DISTANCE_M)
            nearby = list(sindex.query(buf, predicate="intersects"))
            nearby_idx = [group.index[n] for n in nearby if group.index[n] != i]
            for j in nearby_idx:
                if j not in seen:
                    gdf.at[j, "_drop"] = True
                    seen.add(j)
            seen.add(i)
    n_dropped = int(gdf["_drop"].sum())
    return gdf[~gdf["_drop"]].drop(columns=["_drop"]), n_dropped


def load_all_transit_stops(main_gtfs_dir, iett_gtfs_dir) -> tuple[gpd.GeoDataFrame, dict]:
    main_gdf, main_diag = load_main_gtfs_stops(main_gtfs_dir)
    iett_gdf, iett_diag = load_iett_gtfs_stops(iett_gtfs_dir)

    combined = pd.concat([main_gdf, iett_gdf], ignore_index=True)
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=cfg.STORAGE_CRS)
    combined = combined.to_crs(cfg.METRIC_CRS)

    combined, n_duplicates_removed = dedup_stops(combined)

    diagnostics = {
        "main_gtfs": main_diag,
        "iett_gtfs": iett_diag,
        "n_duplicate_stops_removed": n_duplicates_removed,
        "n_stops_by_mode_total_citywide": combined["mode"].value_counts().to_dict(),
    }
    return combined, diagnostics
