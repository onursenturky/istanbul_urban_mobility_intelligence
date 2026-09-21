"""Human-readable metadata for every column in terrain_features.*.

Exported as data/processed/features/terrain_feature_dictionary.csv.

Methodological note (also in the module docstrings): TERRAIN SLOPE (physical
surface inclination, from the DEM) and ROAD GRADE (steepness experienced
along the actual street network) are kept as separate feature families here.
Neither implies a "cycling suitability" score — Istanbul's shared-bike fleet
includes e-bikes, whose effective slope penalty differs from conventional
cycling literature assumptions. These are stored as descriptive physical
measurements only; any suitability judgment is left to later modeling.
"""

from src.features import dem_source_config as dcfg
from src.utils import config as cfg

_SRC = f"{dcfg.COPERNICUS_DEM['dataset_name']} ({dcfg.COPERNICUS_DEM['provider']})"
_ELEV_METHOD = (
    "DEM reprojected to EPSG:32635 (bilinear resampling, 30m target resolution); each valid "
    "pixel's center point spatially joined to the one grid cell containing it (pixel-center "
    "zonal membership, not area-weighted); aggregated per cell."
)
_SLOPE_METHOD = (
    "Slope computed via Horn's method (3x3-kernel, GDAL/QGIS/ArcGIS default) on the "
    "reprojected metric-CRS DEM, then aggregated per cell the same way as elevation."
)

FEATURE_DICTIONARY = [
    {"feature_name": "mean_elevation_m", "description": "Mean surface elevation of valid DEM pixels in the cell", "unit": "m (EGM2008 geoid)", "processing_method": _ELEV_METHOD},
    {"feature_name": "median_elevation_m", "description": "Median surface elevation of valid DEM pixels in the cell", "unit": "m (EGM2008 geoid)", "processing_method": _ELEV_METHOD},
    {"feature_name": "min_elevation_m", "description": "Minimum surface elevation of valid DEM pixels in the cell", "unit": "m (EGM2008 geoid)", "processing_method": _ELEV_METHOD},
    {"feature_name": "max_elevation_m", "description": "Maximum surface elevation of valid DEM pixels in the cell", "unit": "m (EGM2008 geoid)", "processing_method": _ELEV_METHOD},
    {"feature_name": "elevation_range_m", "description": "max_elevation_m - min_elevation_m within the cell", "unit": "m", "processing_method": "Derived from the two columns above."},
    {"feature_name": "elevation_std_m", "description": "Standard deviation of elevation among valid pixels in the cell (terrain roughness proxy)", "unit": "m", "processing_method": _ELEV_METHOD},
    {"feature_name": "mean_slope_deg", "description": "Mean terrain slope (physical surface inclination) of valid pixels in the cell", "unit": "degrees", "processing_method": _SLOPE_METHOD},
    {"feature_name": "median_slope_deg", "description": "Median terrain slope of valid pixels in the cell", "unit": "degrees", "processing_method": _SLOPE_METHOD},
    {"feature_name": "max_slope_deg", "description": "Maximum terrain slope of valid pixels in the cell", "unit": "degrees", "processing_method": _SLOPE_METHOD},
    {"feature_name": "slope_std_deg", "description": "Standard deviation of terrain slope among valid pixels in the cell", "unit": "degrees", "processing_method": _SLOPE_METHOD},
    {"feature_name": "pct_area_slope_lt_3deg", "description": "Share of valid pixels in the cell with slope < 3 degrees — a DESCRIPTIVE terrain class, not a validated cycling-suitability threshold", "unit": "percent (0-100)", "processing_method": "Pixel-count share within the bin (pixels are equal-area, so this closely approximates an area share)."},
    {"feature_name": "pct_area_slope_3_6deg", "description": "Share of valid pixels with slope in [3, 6) degrees — descriptive terrain class only", "unit": "percent (0-100)", "processing_method": "Same as above."},
    {"feature_name": "pct_area_slope_6_10deg", "description": "Share of valid pixels with slope in [6, 10) degrees — descriptive terrain class only", "unit": "percent (0-100)", "processing_method": "Same as above."},
    {"feature_name": "pct_area_slope_gt_10deg", "description": "Share of valid pixels with slope >= 10 degrees — descriptive terrain class only", "unit": "percent (0-100)", "processing_method": "Same as above."},
    {"feature_name": "n_valid_dem_pixels", "description": "Number of valid DEM pixels used for this cell's elevation/slope statistics (QA field)", "unit": "count", "processing_method": "Count of pixel points joined to the cell."},
    {"feature_name": "mean_absolute_road_grade_pct", "description": "Length-weighted mean |grade| (elevation change / horizontal distance) of road segments in the cell — steepness EXPERIENCED ALONG THE NETWORK, distinct from areal terrain slope above", "unit": "percent grade", "processing_method": "Endpoint-elevation road-grade estimate (see road_grade_features.py); segments <30m or with invalid DEM samples excluded; length-weighted mean per cell."},
    {"feature_name": "median_absolute_road_grade_pct", "description": "Length-weighted median |grade| of road segments in the cell", "unit": "percent grade", "processing_method": "Same source as above; weighted median by clipped segment length."},
    {"feature_name": "pct_road_length_grade_gt_5pct", "description": "Share of sampled road length in the cell with |grade| > 5%", "unit": "percent (0-100)", "processing_method": "Sum of clipped lengths with grade_pct > 5, divided by total sampled length in the cell."},
    {"feature_name": "pct_road_length_grade_gt_8pct", "description": "Share of sampled road length in the cell with |grade| > 8%", "unit": "percent (0-100)", "processing_method": "Same as above with an 8% threshold."},
    {"feature_name": "road_grade_sample_length_m", "description": "Total road length actually used for this cell's grade statistics (QA field) — smaller than Phase 3A's road_length_m because segments <30m or with invalid DEM samples are excluded here", "unit": "m", "processing_method": "Sum of clipped lengths of eligible segments in the cell."},
]

FEATURE_DICTIONARY_COLUMNS = ["feature_name", "description", "unit", "source", "reference_year", "processing_method", "retrieval_date"]


def as_dataframe():
    import pandas as pd

    rows = [
        dict(row, source=_SRC, reference_year=f"{dcfg.COPERNICUS_DEM['acquisition_years']}", retrieval_date=cfg.DEM_RETRIEVAL_DATE)
        for row in FEATURE_DICTIONARY
    ]
    return pd.DataFrame(rows, columns=FEATURE_DICTIONARY_COLUMNS)
