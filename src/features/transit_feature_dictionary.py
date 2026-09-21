"""Human-readable metadata for every column in transit_features.*.

Kept separate from processing code so meaning/provenance is auditable
without reading the pipeline. Exported as
data/processed/features/transit_feature_dictionary.csv.
"""

from src.utils import config as cfg

_MAIN_SRC = "İBB Açık Veri Portalı — Toplu Ulaşım GTFS Verisi (Metro İstanbul, Marmaray/TCDD, ferry operators)"
_IETT_SRC = "İBB Açık Veri Portalı — İETT GTFS Verisi (bus incl. Metrobüs)"
_DATE = cfg.TRANSIT_RETRIEVAL_DATE

_COUNT_METHOD = "Stop assigned to the grid cell whose POLYGON contains it (area-based membership, post dedup)."
_DIST_METHOD = (
    "Nearest-neighbor distance (cKDTree) from the grid CENTROID to the full CITY-WIDE stop set of "
    "this mode — never clipped to the study area, so a station just outside the three districts is "
    "still correctly identified as nearest for a boundary cell."
)

FEATURE_DICTIONARY = [
    # --- Station/stop counts (area-based) ---
    {"feature_name": "metro_station_count", "description": "Metro stations located inside the cell", "unit": "count",
     "source": _MAIN_SRC, "processing_method": _COUNT_METHOD},
    {"feature_name": "tram_station_count", "description": "Tram stops located inside the cell (incl. T3 Kadıköy-Moda)", "unit": "count",
     "source": _MAIN_SRC, "processing_method": _COUNT_METHOD},
    {"feature_name": "rail_station_count", "description": "Marmaray/TCDD urban rail stations located inside the cell", "unit": "count",
     "source": _MAIN_SRC, "processing_method": _COUNT_METHOD},
    {"feature_name": "metrobus_station_count", "description": "Metrobüs (BRT) stations located inside the cell", "unit": "count",
     "source": _IETT_SRC, "processing_method": _COUNT_METHOD},
    {"feature_name": "bus_stop_count", "description": "Regular İETT bus stops located inside the cell", "unit": "count",
     "source": _IETT_SRC, "processing_method": _COUNT_METHOD},
    {"feature_name": "ferry_terminal_count", "description": "Ferry terminals located inside the cell", "unit": "count",
     "source": _MAIN_SRC, "processing_method": _COUNT_METHOD},
    {"feature_name": "total_transit_stop_count", "description": "Sum of the six mode-specific counts above", "unit": "count",
     "source": "derived", "processing_method": "Sum across the six *_count/*_station_count columns."},
    # --- Distances (centroid-based) ---
    {"feature_name": "distance_to_nearest_metro_m", "description": "Distance from the cell centroid to the nearest metro station", "unit": "m",
     "source": _MAIN_SRC, "processing_method": _DIST_METHOD},
    {"feature_name": "distance_to_nearest_tram_m", "description": "Distance from the cell centroid to the nearest tram stop", "unit": "m",
     "source": _MAIN_SRC, "processing_method": _DIST_METHOD},
    {"feature_name": "distance_to_nearest_rail_m", "description": "Distance from the cell centroid to the nearest Marmaray/TCDD station", "unit": "m",
     "source": _MAIN_SRC, "processing_method": _DIST_METHOD},
    {"feature_name": "distance_to_nearest_metrobus_m", "description": "Distance from the cell centroid to the nearest Metrobüs station", "unit": "m",
     "source": _IETT_SRC, "processing_method": _DIST_METHOD},
    {"feature_name": "distance_to_nearest_bus_stop_m", "description": "Distance from the cell centroid to the nearest bus stop", "unit": "m",
     "source": _IETT_SRC, "processing_method": _DIST_METHOD},
    {"feature_name": "distance_to_nearest_ferry_m", "description": "Distance from the cell centroid to the nearest ferry terminal", "unit": "m",
     "source": _MAIN_SRC, "processing_method": _DIST_METHOD},
    {"feature_name": "distance_to_nearest_transit_m", "description": "Distance from the cell centroid to the nearest stop of ANY mode", "unit": "m",
     "source": "derived", "processing_method": _DIST_METHOD},
    # --- Accessibility (centroid-based, radius counts) ---
    {"feature_name": "transit_stops_within_500m", "description": "Count of stops of ANY mode within 500 m of the cell centroid", "unit": "count",
     "source": "derived", "processing_method": "cKDTree radius count from the centroid against the full city-wide stop set."},
    {"feature_name": "transit_stops_within_1000m", "description": "Count of stops of ANY mode within 1000 m of the cell centroid", "unit": "count",
     "source": "derived", "processing_method": "cKDTree radius count from the centroid against the full city-wide stop set."},
    {"feature_name": "fixed_guideway_stations_within_1000m", "description": "Count of metro+tram+rail stations within 1000 m of the centroid (fixed-guideway modes pooled)", "unit": "count",
     "source": "derived", "processing_method": "cKDTree radius count, pooling metro/tram/rail stop sets."},
    {"feature_name": "rail_stations_within_1000m", "description": "DEPRECATED alias of fixed_guideway_stations_within_1000m, kept for backward compatibility — identical values. Renamed because 'rail' alone was misleading for a column that pools metro+tram+rail.", "unit": "count",
     "source": "derived", "processing_method": "Identical to fixed_guideway_stations_within_1000m; use that column going forward."},
    {"feature_name": "bus_stops_within_500m", "description": "Count of regular bus stops within 500 m of the centroid", "unit": "count",
     "source": _IETT_SRC, "processing_method": "cKDTree radius count from the centroid against city-wide bus stops."},
    {"feature_name": "number_of_transit_modes_accessible", "description": f"Count of the six modes with distance_to_nearest_<mode>_m <= {cfg.TRANSIT_ACCESSIBILITY_RADIUS_M} m (accessibility radius defined explicitly, not a weighted score)", "unit": "count (0-6)",
     "source": "derived", "processing_method": f"Sum of (distance_to_nearest_<mode>_m <= {cfg.TRANSIT_ACCESSIBILITY_RADIUS_M}) across the six modes."},
    # --- Route diversity (topology; robust to feed staleness) ---
    {"feature_name": "routes_serving_grid", "description": "Distinct GTFS routes (any mode, both feeds) stopping inside the cell", "unit": "count",
     "source": f"{_MAIN_SRC}; {_IETT_SRC}", "processing_method": "Union of route_id sets across stops assigned to the cell by polygon membership."},
    {"feature_name": "unique_bus_routes", "description": "Distinct regular-bus routes stopping inside the cell (excludes Metrobüs)", "unit": "count",
     "source": _IETT_SRC, "processing_method": "Union of route_id sets across bus-mode stops assigned to the cell."},
    {"feature_name": "unique_rail_lines", "description": "Distinct metro+tram+rail lines stopping inside the cell", "unit": "count",
     "source": _MAIN_SRC, "processing_method": "Union of route_id sets across metro/tram/rail-mode stops assigned to the cell."},
    # --- Service intensity (bus/metrobüs only — see module docstring for why rail is excluded) ---
    {"feature_name": "bus_departures_per_day", "description": "Total weekday scheduled departures (bus + Metrobüs) at stops inside the cell — NOT computed for metro/tram/rail/ferry (see limitations)", "unit": "departures / weekday",
     "source": _IETT_SRC, "processing_method": "stop_times rows for weekday (service_id=0) trips, summed per cell across matched bus/metrobüs stops."},
    {"feature_name": "bus_departures_peak_hour", "description": f"Weekday departures (bus + Metrobüs) at stops inside the cell during {cfg.PEAK_HOUR_LABEL}", "unit": "departures / peak hour",
     "source": _IETT_SRC, "processing_method": "Same as bus_departures_per_day, filtered to stop_times rows whose time falls in the defined peak window."},
]

FEATURE_DICTIONARY_COLUMNS = ["feature_name", "description", "unit", "source", "processing_method", "retrieval_date"]


def as_dataframe():
    import pandas as pd

    rows = [dict(row, retrieval_date=_DATE) for row in FEATURE_DICTIONARY]
    return pd.DataFrame(rows, columns=FEATURE_DICTIONARY_COLUMNS)
