"""Phase 4: proper inspection of the complete Bicification dataset.

Bicification is an EIT-funded, İBB-hosted GAMIFIED PERSONAL BICYCLE trip
tracking pilot (June-December 2022) — its own documentation describes it as
routes from "people who use bicycles" via a reward app, NOT a shared-bike
or e-bike system. It must never be labeled "shared-bike demand"; that
interpretation is not supported by its documentation.

Two real data-quality issues were found and are handled explicitly rather
than silently degrading the sample:
  - 6 of 2,067 features (0.3%) have a degenerate (<2-point) LineString and
    cannot be read as geometry at all — dropped.
  - End-point coordinates for the majority of trips are corrupted by the
    same thousands-separator artifact found in Phase 3B's İETT stops.csv
    (e.g. "290.513.446.100.814" instead of "29.0513446100814"). The same
    fix (strip separators, reinsert the decimal after 2 digits) recovers
    2,034 of 2,061 (98.7%) after the geometry-level drop.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import shape

from src.utils import config as cfg

_ISTANBUL_LAT_RANGE = (39.5, 42.0)
_ISTANBUL_LON_RANGE = (27.0, 30.5)


def _fix_mangled_coordinate(raw, integer_digits: int = 2):
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


def load_all_bicification_trips(monthly_paths: list[Path]) -> tuple[gpd.GeoDataFrame, dict]:
    records = []
    n_raw = 0
    n_bad_geom = 0
    for path in monthly_paths:
        d = json.loads(path.read_text(encoding="utf-8"))
        for feat in d["features"]:
            n_raw += 1
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [])
            if geom.get("type") != "LineString" or len(coords) < 2:
                n_bad_geom += 1
                continue
            try:
                g = shape(geom)
            except Exception:  # noqa: BLE001
                n_bad_geom += 1
                continue
            records.append({**feat["properties"], "geometry": g})

    trips = gpd.GeoDataFrame(records, geometry="geometry", crs=cfg.STORAGE_CRS)

    for col in ["start_lat", "start_lng", "end_lat", "end_lng"]:
        trips[f"{col}_fixed"] = trips[col].apply(_fix_mangled_coordinate)

    valid_coords = (
        trips["start_lat_fixed"].between(*_ISTANBUL_LAT_RANGE)
        & trips["start_lng_fixed"].between(*_ISTANBUL_LON_RANGE)
        & trips["end_lat_fixed"].between(*_ISTANBUL_LAT_RANGE)
        & trips["end_lng_fixed"].between(*_ISTANBUL_LON_RANGE)
    )
    n_recovered_or_clean = int(valid_coords.sum())
    trips_usable = trips[valid_coords].copy()

    n_distinct_session_ids = trips["sessionid"].nunique() if "sessionid" in trips.columns else None
    diagnostics = {
        "n_raw_features_across_all_monthly_files": n_raw,
        "n_dropped_degenerate_geometry": n_bad_geom,
        "n_after_geometry_drop": len(trips),
        "n_usable_after_coordinate_fix": n_recovered_or_clean,
        "n_distinct_session_ids": n_distinct_session_ids,
        "session_id_equals_trip_count": n_distinct_session_ids == len(trips) if n_distinct_session_ids is not None else None,
        "date_range": [str(trips["starttime"].min()), str(trips["starttime"].max())] if "starttime" in trips.columns else None,
        "homework_flag_distribution": trips["homework"].value_counts().to_dict() if "homework" in trips.columns else None,
    }
    return trips_usable, diagnostics


def spatial_feasibility_analysis(trips: gpd.GeoDataFrame, study_area_geom, grid: gpd.GeoDataFrame) -> dict:
    assert grid.crs.to_string() == cfg.METRIC_CRS

    starts = gpd.GeoSeries(
        gpd.points_from_xy(trips["start_lng_fixed"], trips["start_lat_fixed"]), crs=cfg.STORAGE_CRS, index=trips.index
    ).to_crs(cfg.METRIC_CRS)
    ends = gpd.GeoSeries(
        gpd.points_from_xy(trips["end_lng_fixed"], trips["end_lat_fixed"]), crs=cfg.STORAGE_CRS, index=trips.index
    ).to_crs(cfg.METRIC_CRS)

    start_in = starts.within(study_area_geom)
    end_in = ends.within(study_area_geom)

    joined_start = gpd.sjoin(
        gpd.GeoDataFrame(geometry=starts[start_in]), grid[["grid_id", "geometry"]], predicate="within"
    )
    joined_end = gpd.sjoin(
        gpd.GeoDataFrame(geometry=ends[end_in]), grid[["grid_id", "geometry"]], predicate="within"
    )

    origin_counts = joined_start.groupby("grid_id").size()
    dest_counts = joined_end.groupby("grid_id").size()
    combined_counts = pd.concat([origin_counts, dest_counts], axis=1, keys=["origins", "destinations"]).fillna(0)
    combined_counts["total"] = combined_counts["origins"] + combined_counts["destinations"]

    n_cells = len(grid)

    def _dist_stats(counts: pd.Series, n_cells: int) -> dict:
        full = counts.reindex(range(n_cells), fill_value=0) if counts.index.dtype != object else counts
        nonzero = counts[counts > 0]
        return {
            "n_nonzero_cells": int((counts > 0).sum()),
            "pct_nonzero_cells": round(float((counts > 0).sum()) / n_cells * 100, 2),
            "pct_zero_cells": round(100 - float((counts > 0).sum()) / n_cells * 100, 2),
            "total_observations": int(counts.sum()),
            "mean_per_nonzero_cell": round(float(nonzero.mean()), 2) if len(nonzero) else 0.0,
            "median_per_nonzero_cell": float(nonzero.median()) if len(nonzero) else 0.0,
            "max_per_cell": int(counts.max()) if len(counts) else 0,
        }

    diagnostics = {
        "n_trips_with_start_in_study_area": int(start_in.sum()),
        "n_trips_with_end_in_study_area": int(end_in.sum()),
        "n_trips_with_start_or_end_in_study_area": int((start_in | end_in).sum()),
        "n_trips_with_both_in_study_area": int((start_in & end_in).sum()),
        "origin_distribution": _dist_stats(origin_counts, n_cells),
        "destination_distribution": _dist_stats(dest_counts, n_cells),
        "combined_or_distribution": {
            "n_nonzero_cells": int((combined_counts["total"] > 0).sum()),
            "pct_nonzero_cells": round(float((combined_counts["total"] > 0).sum()) / n_cells * 100, 2),
        },
    }
    return diagnostics
