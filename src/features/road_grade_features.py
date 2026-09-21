"""Phase 3D road-grade feature engineering.

Reuses the SAME cached OSM road network from Phase 3A (never re-fetched)
and the SAME bidirectional-edge deduplication step (ox.convert.to_undirected)
used there, for the same reason: a MultiDiGraph stores a two-way street as
two directed edges, and sampling/aggregating both would double-count it.

Grade is estimated from bilinearly-sampled DEM elevation at each segment's
two endpoints: grade_pct = |elevation_change| / horizontal_length * 100.
Segments shorter than MIN_ROAD_SEGMENT_LENGTH_M (30m, matching the DEM's
native pixel size) are excluded — below that length, endpoint elevation
differences are dominated by DEM sampling noise rather than real terrain
signal.

This is a segment-endpoint estimate, not a full elevation profile along each
road — a defensible simplification at 30m DEM resolution, documented as such
rather than presented with false precision.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
from scipy.ndimage import map_coordinates

from src.utils import config as cfg


def _sample_bilinear(array: np.ndarray, transform, xs, ys) -> np.ndarray:
    inv = ~transform
    cols = np.empty(len(xs))
    rows = np.empty(len(xs))
    for idx, (x, y) in enumerate(zip(xs, ys)):
        c, r = inv * (x, y)
        cols[idx] = c - 0.5  # rasterio affine maps pixel corners; map_coordinates indexes pixel centers
        rows[idx] = r - 0.5
    return map_coordinates(array, [rows, cols], order=1, mode="nearest", cval=np.nan)


def prepare_road_edges(G, elevation: np.ndarray, transform) -> tuple[gpd.GeoDataFrame, dict]:
    G_proj = ox.project_graph(G, to_crs=cfg.METRIC_CRS)
    G_u = ox.convert.to_undirected(G_proj)
    edges = ox.graph_to_gdfs(G_u, nodes=False, edges=True).reset_index()
    edges["length_m"] = edges.geometry.length

    n_raw = len(edges)
    too_short = edges["length_m"] < cfg.MIN_ROAD_SEGMENT_LENGTH_M
    n_excluded_short = int(too_short.sum())
    edges = edges[~too_short].copy()

    start_pts = edges.geometry.apply(lambda g: g.coords[0])
    end_pts = edges.geometry.apply(lambda g: g.coords[-1])
    elev_start = _sample_bilinear(elevation, transform, [p[0] for p in start_pts], [p[1] for p in start_pts])
    elev_end = _sample_bilinear(elevation, transform, [p[0] for p in end_pts], [p[1] for p in end_pts])

    valid_elev = np.isfinite(elev_start) & np.isfinite(elev_end)
    n_excluded_invalid_elev = int((~valid_elev).sum())
    edges = edges[valid_elev].copy()
    elev_start, elev_end = elev_start[valid_elev], elev_end[valid_elev]

    edges["grade_pct"] = np.abs(elev_end - elev_start) / edges["length_m"].to_numpy() * 100
    n_suspicious = int((edges["grade_pct"] > cfg.ROAD_GRADE_SUSPICIOUS_THRESHOLD_PCT).sum())

    diagnostics = {
        "n_edges_undirected_total": n_raw,
        "n_excluded_short_segments": n_excluded_short,
        "n_excluded_invalid_elevation": n_excluded_invalid_elev,
        "n_edges_used_for_grade": len(edges),
        "n_suspicious_grade_segments_over_threshold": n_suspicious,
        "suspicious_threshold_pct": cfg.ROAD_GRADE_SUSPICIOUS_THRESHOLD_PCT,
        "min_segment_length_m": cfg.MIN_ROAD_SEGMENT_LENGTH_M,
    }
    return edges[["geometry", "length_m", "grade_pct"]], diagnostics


def _weighted_grade_stats(g: pd.DataFrame) -> pd.Series:
    lengths, grades = g["length_m"].to_numpy(), g["grade_pct"].to_numpy()
    total_len = lengths.sum()
    mean_grade = float(np.average(grades, weights=lengths))
    order = np.argsort(grades)
    sorted_grades, sorted_lengths = grades[order], lengths[order]
    cum = np.cumsum(sorted_lengths)
    median_grade = float(sorted_grades[np.searchsorted(cum, total_len / 2)])
    pct_gt5 = float(lengths[grades > 5].sum() / total_len * 100)
    pct_gt8 = float(lengths[grades > 8].sum() / total_len * 100)
    return pd.Series({
        "mean_absolute_road_grade_pct": mean_grade, "median_absolute_road_grade_pct": median_grade,
        "pct_road_length_grade_gt_5pct": pct_gt5, "pct_road_length_grade_gt_8pct": pct_gt8,
        "road_grade_sample_length_m": total_len,
    })


def compute_road_grade_features(edges: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> pd.DataFrame:
    assert grid.crs.to_string() == cfg.METRIC_CRS

    # Vectorized clip via gpd.overlay instead of a per-cell Python loop —
    # the expensive geometric operation (spatial-indexed internally) is done
    # once for all (cell, edge) pairs; the length-weighted mean/median/
    # threshold-share statistics are then computed per group exactly as
    # before (small, cheap per-group numpy work, not a geometry operation).
    # See data/processed/citywide/pipeline_optimization_validation.json.
    overlay = gpd.overlay(
        grid[["grid_id", "geometry"]], edges[["geometry", "grade_pct"]], how="intersection", keep_geom_type=False
    )
    overlay["length_m"] = overlay.geometry.length
    overlay = overlay[overlay["length_m"] > 0]

    stats = overlay.groupby("grid_id").apply(_weighted_grade_stats, include_groups=False).reset_index()

    result = grid[["grid_id"]].merge(stats, on="grid_id", how="left")
    result["road_grade_sample_length_m"] = result["road_grade_sample_length_m"].fillna(0.0)
    return result
