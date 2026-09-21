"""Phase 7 Network Intelligence Foundation: reusable citywide accessibility
engine. Given a mode's graph, an origin (network node or grid cell, via its
anchor), and a travel-time threshold, returns everything reachable within
that budget. Built on networkx's cutoff-Dijkstra
(single_source_dijkstra_path_length with `cutoff`), which stops expanding
once the cutoff is exceeded rather than computing the full shortest-path
tree -- the appropriate exact method for this use case (see
accessibility_engine_benchmark.json for why this was chosen over
precomputation/parallelization for the baseline).

This module answers "what is reachable from HERE within T minutes" -- it
does NOT compute 15-minute-city scores, destination counts, or any
application-level metric. Those are future applications built ON this engine.
"""

from __future__ import annotations

import networkx as nx
import pandas as pd

THRESHOLDS_MIN = [5, 10, 15]


def reachable_from_node(G, source_node, weight_time_attr: str, cutoff_seconds: float) -> dict[int, float]:
    """Returns {node: travel_time_seconds} for every node reachable from
    source_node within cutoff_seconds, INCLUDING the source itself (time 0).
    Uses networkx's built-in cutoff, not a full shortest-path tree."""
    return nx.single_source_dijkstra_path_length(G, source_node, cutoff=cutoff_seconds, weight=weight_time_attr)


def reachable_edges(G, reachable_node_times: dict) -> list[tuple]:
    """An edge is 'reachable' if BOTH its endpoints are in the reachable
    node set -- a conservative, unambiguous definition (an edge only
    partially within budget is not counted as fully reachable)."""
    reachable_nodes = set(reachable_node_times.keys())
    return [(u, v, k) for u, v, k in G.edges(keys=True) if u in reachable_nodes and v in reachable_nodes]


def reachable_grid_cells(reachable_node_times: dict, anchors: pd.DataFrame, mode_label: str) -> pd.DataFrame:
    """A grid cell is 'reachable' if ITS OWN anchor node is in the
    reachable set -- consistent with how the cell was anchored to the
    network in the first place (network_anchor.py)."""
    anchor_col = f"{mode_label}_anchor_node"
    reachable_mask = anchors[anchor_col].isin(reachable_node_times.keys())
    result = anchors.loc[reachable_mask, ["grid_id", anchor_col]].copy()
    result["travel_time_s"] = result[anchor_col].map(reachable_node_times)
    return result[["grid_id", "travel_time_s"]]


def accessibility_query(G, origin_node, weight_time_attr: str, anchors: pd.DataFrame, mode_label: str,
                          thresholds_min: list[int] = THRESHOLDS_MIN) -> dict:
    """Full reusable query: one origin, all requested thresholds. Returns,
    per threshold, reachable node/edge counts and reachable grid cells --
    the interface future applications (15-minute city, mobility hubs, etc.)
    will call."""
    max_cutoff_s = max(thresholds_min) * 60
    all_reachable = reachable_from_node(G, origin_node, weight_time_attr, max_cutoff_s)

    results = {}
    for t_min in thresholds_min:
        cutoff_s = t_min * 60
        sub_reachable = {n: t for n, t in all_reachable.items() if t <= cutoff_s}
        edges = reachable_edges(G, sub_reachable)
        cells = reachable_grid_cells(sub_reachable, anchors, mode_label)
        results[f"{t_min}min"] = {
            "n_reachable_nodes": len(sub_reachable), "n_reachable_edges": len(edges),
            "n_reachable_grid_cells": len(cells), "reachable_grid_cell_ids": cells["grid_id"].tolist(),
        }
    return {"origin_node": origin_node, "mode": mode_label, "by_threshold": results}
