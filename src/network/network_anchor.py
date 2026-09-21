"""Phase 7 Network Intelligence Foundation: reproducible grid-cell-to-
network-node anchoring for all 22,322 grid cells, for both the walking and
cycling graphs independently (their node sets differ -- cycling excludes
footway/steps, walking excludes cycleway, so the nearest routable node for
each mode is not always the same physical point).

Rule (explicit, not a blind centroid-only rule):
  1. anchor_node = the network node NEAREST to the cell's CENTROID (global
     nearest-neighbor search over ALL nodes in that mode's graph, not
     restricted to nodes physically inside the cell -- a cell with no
     network presence at all, e.g. open water or dense forest, still needs
     a usable "nearest accessible point" anchor, exactly as a real
     accessibility query would need).
  2. snap_distance_m = Euclidean distance from centroid to that node.
  3. has_local_node = whether at least one network node of that mode lies
     INSIDE the cell polygon itself (a real, direct within-cell rule,
     distinguishing "the cell itself has network presence" from "the
     nearest node is merely close by").
  4. snap_quality is classified from snap_distance_m using EXPLICIT,
     documented thresholds (not hidden, not silently accepted):
       DIRECT      <= 100 m
       NEARBY      100-300 m
       LARGE_SNAP  300-1000 m
       QUESTIONABLE > 1000 m  -- flagged prominently, never hidden
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from src.utils import config as cfg

SNAP_DIRECT_M = 100.0
SNAP_NEARBY_M = 300.0
SNAP_LARGE_M = 1000.0


def _node_coords(G) -> tuple[np.ndarray, np.ndarray]:
    ids, xy = [], []
    for n, d in G.nodes(data=True):
        if "x" in d and "y" in d:
            ids.append(n)
            xy.append((d["x"], d["y"]))
    return np.array(ids), np.array(xy)


def _classify_snap(dist_m: float) -> str:
    if dist_m <= SNAP_DIRECT_M:
        return "DIRECT"
    if dist_m <= SNAP_NEARBY_M:
        return "NEARBY"
    if dist_m <= SNAP_LARGE_M:
        return "LARGE_SNAP"
    return "QUESTIONABLE"


def anchor_grid_to_network(G, grid: gpd.GeoDataFrame, mode_label: str) -> pd.DataFrame:
    assert grid.crs.to_string() == cfg.METRIC_CRS
    node_ids, node_xy = _node_coords(G)
    assert len(node_ids) > 0, f"{mode_label} graph has no nodes with x/y attributes"
    tree = cKDTree(node_xy)

    centroids = grid.geometry.centroid
    cxy = np.column_stack([centroids.x.to_numpy(), centroids.y.to_numpy()])
    dist, idx = tree.query(cxy, k=1)
    anchor_nodes = node_ids[idx]

    nodes_gdf = gpd.GeoDataFrame({"node": node_ids}, geometry=gpd.points_from_xy(node_xy[:, 0], node_xy[:, 1]), crs=cfg.METRIC_CRS)
    joined = gpd.sjoin(nodes_gdf, grid[["grid_id", "geometry"]], predicate="within", how="inner")
    cells_with_local_node = set(joined["grid_id"])

    out = pd.DataFrame({
        "grid_id": grid["grid_id"].to_numpy(),
        f"{mode_label}_anchor_node": anchor_nodes,
        f"{mode_label}_snap_distance_m": np.round(dist, 2),
        f"{mode_label}_has_local_node": grid["grid_id"].isin(cells_with_local_node).to_numpy(),
    })
    out[f"{mode_label}_snap_quality"] = out[f"{mode_label}_snap_distance_m"].apply(_classify_snap)
    return out


def build_anchors(G_walk, G_cycle, grid: gpd.GeoDataFrame) -> tuple[pd.DataFrame, dict]:
    walk_anchors = anchor_grid_to_network(G_walk, grid, "walking")
    cycle_anchors = anchor_grid_to_network(G_cycle, grid, "cycling")
    anchors = walk_anchors.merge(cycle_anchors, on="grid_id")

    diag = {}
    for mode in ["walking", "cycling"]:
        dist_col = f"{mode}_snap_distance_m"
        qual_col = f"{mode}_snap_quality"
        diag[mode] = {
            "n_cells": len(anchors),
            "snap_distance_stats": {
                "min": float(anchors[dist_col].min()), "median": float(anchors[dist_col].median()),
                "mean": float(anchors[dist_col].mean()), "p90": float(anchors[dist_col].quantile(0.9)),
                "p99": float(anchors[dist_col].quantile(0.99)), "max": float(anchors[dist_col].max()),
            },
            "quality_counts": anchors[qual_col].value_counts().to_dict(),
            "pct_direct_or_nearby": round(float(anchors[qual_col].isin(["DIRECT", "NEARBY"]).mean() * 100), 2),
            "n_questionable": int((anchors[qual_col] == "QUESTIONABLE").sum()),
            "pct_has_local_node": round(float(anchors[f"{mode}_has_local_node"].mean() * 100), 2),
        }
    return anchors, diag
