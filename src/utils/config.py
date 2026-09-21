"""Shared paths and constants for the Istanbul Urban Mobility Intelligence pipeline."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
OUTPUTS_MAPS = PROJECT_ROOT / "outputs" / "maps"

# Metric CRS for all distance/area/grid calculations (WGS84 / UTM zone 35N).
# Appropriate for Istanbul's longitude; chosen over EPSG:5254 (Turkish TM30)
# for broader library support (pyproj/GDAL ship its parameters by default).
METRIC_CRS = "EPSG:32635"

# Storage CRS for GeoJSON outputs, per RFC 7946 (GeoJSON coordinates are
# assumed WGS84 lon/lat by GIS clients). All metric attributes (areas,
# lengths, thresholds) are computed in METRIC_CRS *before* this reprojection,
# so reprojecting geometry for storage does not affect their values.
STORAGE_CRS = "EPSG:4326"

GRID_RESOLUTION_M = 500

# A retained grid cell must have at least this fraction of its nominal
# 500x500 m area actually inside the dissolved study area. Cells below this
# are dropped rather than kept as slivers. land_area_m2, cell_area_m2 and
# pct_in_study_area are preserved for every retained cell so this threshold
# can be revisited (e.g. 25% or 50%) without re-running the OSM fetch.
INTERSECTION_THRESHOLD = 0.10

# A retained cell's district assignment is flagged ambiguous when the
# second-largest district overlap is within this fraction of the largest
# overlap (i.e. no single district clearly dominates the cell).
AMBIGUOUS_DISTRICT_RATIO = 0.20

# Pilot study area: OSM administrative boundary relations (admin_level=6,
# network=TR34-districts), verified via Overpass API on 2026-09-18.
# İBB's open data portal (data.ibb.gov.tr) does not expose a scriptable,
# login-free district-boundary download as of this date; OSM boundaries are
# used instead and documented here for provenance.
DISTRICTS = {
    "Kadıköy": 1276548,
    "Üsküdar": 1276889,
    "Maltepe": 1276407,
}

BOUNDARY_SOURCE = "OpenStreetMap contributors"
BOUNDARY_LICENSE = "ODbL 1.0 (https://www.openstreetmap.org/copyright)"
BOUNDARY_RETRIEVAL_DATE = "2026-09-18"

# --- Phase 3A: OSM urban feature engineering ---

DATA_FEATURES = DATA_PROCESSED / "features"

# The road network needs continuity past the district edge (otherwise real
# streets get artificial dead ends at the boundary, distorting intersection
# counts and road length near the edge). Buildings/POIs/green space don't
# strictly need it, but querying once over the same buffered area is simpler
# and more reproducible than querying different extents per feature family.
OSM_QUERY_BUFFER_M = 500

# The buffered study-area polygon is simplified to this tolerance (meters)
# before being used as an Overpass "poly" filter. It is a query boundary
# only (a superset used purely to bound the fetch), not used for any area
# or distance calculation, so a small simplification is immaterial.
OSM_QUERY_SIMPLIFY_TOLERANCE_M = 25

# A POI node within this distance of a polygon/way of the SAME category is
# treated as a duplicate mapping of the same real-world feature (e.g. a shop
# mapped both as a building outline and a separate label node) and dropped,
# keeping the polygon/way representation.
POI_DEDUP_DISTANCE_M = 15

OSM_SOURCE = "OpenStreetMap contributors"
OSM_LICENSE = "ODbL 1.0 (https://www.openstreetmap.org/copyright)"
OSM_RETRIEVAL_DATE = "2026-09-18"

# land-use entropy is only computed if the mean fraction of a cell's land
# area actually covered by a classified landuse polygon meets this bar;
# below it, OSM land-use tagging is too incomplete here to support entropy
# as a meaningful measure, and reporting the coverage gap is preferred to
# fabricating a value from sparse data.
LANDUSE_ENTROPY_MIN_MEAN_COVERAGE_PCT = 50.0

# --- Phase 3B: public transport accessibility ---

DATA_RAW_TRANSIT = DATA_RAW / "transit"

TRANSIT_RETRIEVAL_DATE = "2026-09-18"

# Distances/within-radius accessibility features use the grid CENTROID as the
# representative location (not the cell polygon), so they stay internally
# consistent with each other; *_count infrastructure features instead use
# polygon membership (a station is "in" the cell whose polygon contains it).
# This split is documented per-feature in transit_feature_dictionary.py.
TRANSIT_ACCESSIBILITY_RADIUS_M = 500  # radius used for number_of_transit_modes_accessible

# Weekday morning peak window used for *_departures_peak_hour (İETT only —
# see transit_tag_config.py for why rail-mode frequency is excluded).
PEAK_HOUR_START = "08:"
PEAK_HOUR_LABEL = "08:00-09:00 weekday"

# --- Phase 3C: population and demographic exposure ---

DATA_RAW_POPULATION = DATA_RAW / "population"
POPULATION_RETRIEVAL_DATE = "2026-09-18"

# --- Phase 3D: terrain, elevation and cycling slope ---

DATA_RAW_DEM = DATA_RAW / "dem"
DEM_RETRIEVAL_DATE = "2026-09-19"

# Same buffer convention as Phase 3A/3B: margin beyond the study area so
# slope (a moving-window calculation) isn't computed with artificial edge
# padding right at the grid boundary, and so the DEM mosaic doesn't need to
# be re-fetched if analysis extent changes slightly.
DEM_BUFFER_M = 500
DEM_TARGET_RESOLUTION_M = 30  # matches Copernicus GLO-30's native ~30m posting

# Slope bins are descriptive terrain classes, not cycling-suitability
# thresholds (see terrain_feature_dictionary.py docstring).
SLOPE_BINS_DEG = [0, 3, 6, 10, float("inf")]
SLOPE_BIN_LABELS = ["pct_area_slope_lt_3deg", "pct_area_slope_3_6deg", "pct_area_slope_6_10deg", "pct_area_slope_gt_10deg"]

# A road segment shorter than this is excluded from grade calculation: at
# Copernicus GLO-30's ~30m posting, two endpoints closer together than one
# pixel width sample essentially the same (or adjacent-noise) DEM cells, so
# grade = delta_elevation/distance becomes dominated by DEM noise rather
# than real terrain signal.
MIN_ROAD_SEGMENT_LENGTH_M = 30
ROAD_GRADE_SUSPICIOUS_THRESHOLD_PCT = 30  # flagged for QA review, not excluded

# --- Phase 3E: cycling & micromobility infrastructure ---

DATA_RAW_CYCLING = DATA_RAW / "cycling"
DATA_RAW_SHARED_MOBILITY = DATA_RAW / "shared_mobility"  # kept OUT of the predictor table
CYCLING_RETRIEVAL_DATE = "2026-09-19"

CYCLING_QUERY_BUFFER_M = 500  # same network-continuity rationale as Phase 3A/3B

# Two OSM representations of the same physical facility (a road's own
# cycleway=* attribute, and a separately-digitized highway=cycleway way) are
# treated as duplicates when this much of the shorter segment's length falls
# within this buffer distance of the other geometry.
CYCLING_DEDUP_BUFFER_M = 15
CYCLING_DEDUP_OVERLAP_THRESHOLD = 0.5
