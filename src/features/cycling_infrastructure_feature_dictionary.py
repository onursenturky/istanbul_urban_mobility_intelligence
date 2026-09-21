"""Human-readable metadata for every column in cycling_infrastructure_features.*.

Exported as data/processed/features/cycling_infrastructure_feature_dictionary.csv.
"""

from src.utils import config as cfg

_SRC = "İBB (authoritative) + OpenStreetMap contributors (complementary, ODbL 1.0), deduplicated"
_DATE = cfg.CYCLING_RETRIEVAL_DATE

FEATURE_DICTIONARY = [
    {"feature_name": "cycle_infrastructure_length_km", "description": "Total length of all cycling-infrastructure categories (protected, dedicated lane, shared path, painted, other/unknown) inside the cell", "unit": "km",
     "processing_method": "Each deduplicated geometry clipped to the cell polygon; clipped lengths summed."},
    {"feature_name": "cycle_infrastructure_density_km_per_km2", "description": "cycle_infrastructure_length_km per km^2 of the cell's actual land area", "unit": "km / km^2",
     "processing_method": "cycle_infrastructure_length_km / (land_area_m2 / 1e6) — uses actual clipped land area, not the nominal 0.25 km^2."},
    {"feature_name": "protected_cycleway_length_km", "description": "Length of ONLY the protected_separated category inside the cell (İBB 'Mevcut Ayrılmış' + OSM highway=cycleway w/ foot=no + OSM cycleway(:*)=track)", "unit": "km",
     "processing_method": "Same clipping method, filtered to category=protected_separated."},
    {"feature_name": "protected_cycleway_density_km_per_km2", "description": "protected_cycleway_length_km per km^2 of land area", "unit": "km / km^2",
     "processing_method": "protected_cycleway_length_km / (land_area_m2 / 1e6)."},
    {"feature_name": "distance_to_nearest_cycle_infrastructure_m", "description": "Distance from the cell centroid to the nearest cycling-infrastructure geometry of ANY category, city-wide (not clipped to the study area)", "unit": "m",
     "processing_method": "True point-to-line distance (not vertex-to-vertex) from the centroid to every deduplicated geometry, minimum taken."},
    {"feature_name": "distance_to_nearest_bicycle_parking_m", "description": "Distance from the cell centroid to the nearest İBB 'Bisiklet Park Alanı' point, city-wide", "unit": "m",
     "processing_method": "cKDTree nearest-neighbor from the centroid."},
    {"feature_name": "pct_road_network_with_cycle_infrastructure", "description": f"Share of the cell's Phase 3A road network length lying within {cfg.CYCLING_DEDUP_BUFFER_M}m of any cycling-infrastructure geometry", "unit": "percent (0-100)",
     "processing_method": "Phase 3A's undirected, deduplicated road network clipped per cell; the fraction of that clipped length falling inside a buffered union of the cycling-infrastructure geometries."},
    {"feature_name": "bicycle_parking_count", "description": "Count of İBB-tagged 'Bisiklet Park Alanı' points located inside the cell (excludes 'Mikromobilite Park Alanı' — scooter/e-bike-oriented, per the source's own labeling)", "unit": "count",
     "processing_method": "Point-in-polygon join to the cell containing it."},
]

FEATURE_DICTIONARY_COLUMNS = ["feature_name", "description", "unit", "source", "processing_method", "retrieval_date"]


def as_dataframe():
    import pandas as pd

    rows = [dict(row, source=_SRC, retrieval_date=_DATE) for row in FEATURE_DICTIONARY]
    return pd.DataFrame(rows, columns=FEATURE_DICTIONARY_COLUMNS)
