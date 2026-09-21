"""Phase 3A road-network feature engineering.

Bidirectional streets are stored in OSMnx's fetched MultiDiGraph as two
directed edges (u->v and v->u) sharing the same physical geometry. Summing
them naively roughly doubles road length. `ox.convert.to_undirected` merges
reciprocal edges back into one before any length is computed — verified
empirically on this dataset (5,759 km directed vs 3,315 km undirected).
"""

from __future__ import annotations

import geopandas as gpd
import osmnx as ox
import pandas as pd

from src.features import osm_tag_config as tags
from src.utils import config as cfg


def _highway_class(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def compute_road_features(G, grid_gdf: gpd.GeoDataFrame) -> tuple[pd.DataFrame, dict]:
    assert grid_gdf.crs.to_string() == cfg.METRIC_CRS, "grid must already be in the metric CRS"

    n_edges_directed_raw = len(G.edges)
    G_proj = ox.project_graph(G, to_crs=cfg.METRIC_CRS)
    G_u = ox.convert.to_undirected(G_proj)

    edges = ox.graph_to_gdfs(G_u, nodes=False, edges=True).reset_index()
    edges["highway_class"] = edges["highway"].apply(_highway_class)
    edges["is_major"] = edges["highway_class"].isin(tags.MAJOR_ROAD_HIGHWAY_CLASSES)
    edges["is_local"] = edges["highway_class"].isin(tags.LOCAL_ROAD_HIGHWAY_CLASSES)
    edges["is_walkable"] = ~edges["highway_class"].isin(tags.NOT_WALKABLE_HIGHWAY_CLASSES)
    edges["is_cycle"] = ~edges["highway_class"].isin(tags.NOT_CYCLE_ACCESSIBLE_HIGHWAY_CLASSES)

    # Vectorized clip: gpd.overlay handles polygon-vs-line intersection
    # directly (verified empirically), doing its own spatial-indexed
    # pruning internally — this replaces a per-cell Python loop
    # (sindex.query + intersection per iteration) with one call plus a
    # grouped aggregation. Semantics are identical: each edge is clipped to
    # each cell it overlaps, and clipped lengths are summed per cell and
    # per class. See data/processed/citywide/pipeline_optimization_validation.json
    # for the old-vs-new equivalence check on the pilot grid.
    overlay = gpd.overlay(
        grid_gdf[["grid_id", "geometry"]], edges[["geometry", "is_major", "is_local", "is_walkable", "is_cycle"]],
        how="intersection", keep_geom_type=False,
    )
    overlay["length_m"] = overlay.geometry.length
    overlay["major_len"] = overlay["length_m"].where(overlay["is_major"], 0.0)
    overlay["local_len"] = overlay["length_m"].where(overlay["is_local"], 0.0)
    overlay["walkable_len"] = overlay["length_m"].where(overlay["is_walkable"], 0.0)
    overlay["cycle_len"] = overlay["length_m"].where(overlay["is_cycle"], 0.0)

    road_df = overlay.groupby("grid_id").agg(
        road_length_m=("length_m", "sum"),
        major_road_length_m=("major_len", "sum"),
        local_road_length_m=("local_len", "sum"),
        walkable_road_length_m=("walkable_len", "sum"),
        cycle_accessible_road_length_m=("cycle_len", "sum"),
    ).reset_index()

    # Intersections: nodes with street degree >= 3 in the undirected network
    # (excludes simple through-nodes and dead ends).
    degrees = dict(G_u.degree())
    nodes_gdf = ox.graph_to_gdfs(G_u, nodes=True, edges=False).reset_index()
    nodes_gdf["degree"] = nodes_gdf["osmid"].map(degrees)
    intersections = nodes_gdf[nodes_gdf["degree"] >= 3].copy()

    joined = gpd.sjoin(
        intersections[["geometry"]], grid_gdf[["grid_id", "geometry"]], predicate="intersects", how="inner"
    )
    intersection_counts = joined.groupby("grid_id").size().rename("intersection_count").reset_index()

    result = grid_gdf[["grid_id", "land_area_m2"]].merge(road_df, on="grid_id", how="left")
    result = result.merge(intersection_counts, on="grid_id", how="left")
    result["intersection_count"] = result["intersection_count"].fillna(0).astype(int)
    for col in [
        "road_length_m", "major_road_length_m", "local_road_length_m",
        "walkable_road_length_m", "cycle_accessible_road_length_m",
    ]:
        result[col] = result[col].fillna(0.0)

    result["road_density_km_per_km2"] = result["road_length_m"] / 1000 / (result["land_area_m2"] / 1e6)
    result["intersection_density_km2"] = result["intersection_count"] / (result["land_area_m2"] / 1e6)
    result = result.drop(columns=["land_area_m2"])

    diagnostics = {
        "n_edges_directed_raw": int(n_edges_directed_raw),
        "n_edges_undirected": int(len(edges)),
        "total_road_length_km_undirected": float(edges.geometry.length.sum() / 1000),
        "n_intersections_total": int(len(intersections)),
    }
    return result, diagnostics
