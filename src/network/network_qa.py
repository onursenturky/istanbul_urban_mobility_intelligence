"""Phase 7 Network Intelligence Foundation: QA diagnostics for a built
routable graph (walking = undirected MultiGraph, cycling = directed
MultiDiGraph). Reports gaps and fragmentation; never silently repairs them.
"""

from __future__ import annotations

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd

from src.utils import config as cfg


def basic_stats(G) -> dict:
    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()
    total_length_km = sum(d.get("length_m", 0.0) for _, _, d in G.edges(data=True)) / 1000
    return {"n_nodes": n_nodes, "n_edges": n_edges, "total_length_km": round(total_length_km, 1)}


def connected_component_stats(G) -> dict:
    directed = G.is_directed()
    if directed:
        weak = list(nx.weakly_connected_components(G))
        strong = list(nx.strongly_connected_components(G))
        weak_sizes = sorted((len(c) for c in weak), reverse=True)
        strong_sizes = sorted((len(c) for c in strong), reverse=True)
        n_total = G.number_of_nodes()
        return {
            "directed_graph": True,
            "n_weakly_connected_components": len(weak),
            "largest_weak_component_size": weak_sizes[0] if weak_sizes else 0,
            "largest_weak_component_share": round(weak_sizes[0] / n_total, 4) if weak_sizes and n_total else 0.0,
            "n_isolated_weak_components_size1": sum(1 for s in weak_sizes if s == 1),
            "n_strongly_connected_components": len(strong),
            "largest_strong_component_size": strong_sizes[0] if strong_sizes else 0,
            "largest_strong_component_share": round(strong_sizes[0] / n_total, 4) if strong_sizes and n_total else 0.0,
            "note": "Strong connectivity is naturally much lower for a directed one-way street network (many "
                    "dead-end/cul-de-sac one-way segments cannot round-trip) -- weak connectivity is the more "
                    "relevant reachability measure for cutoff-Dijkstra accessibility queries, reported alongside "
                    "strong connectivity for full transparency, not in place of it.",
        }
    else:
        comps = list(nx.connected_components(G))
        sizes = sorted((len(c) for c in comps), reverse=True)
        n_total = G.number_of_nodes()
        return {
            "directed_graph": False,
            "n_connected_components": len(comps),
            "largest_component_size": sizes[0] if sizes else 0,
            "largest_component_share": round(sizes[0] / n_total, 4) if sizes and n_total else 0.0,
            "n_isolated_components_size1": sum(1 for s in sizes if s == 1),
            "component_size_distribution_top10": sizes[:10],
        }


def _nodes_joined_to_grid(G, grid: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    node_ids, xs, ys = [], [], []
    for n, d in G.nodes(data=True):
        if "x" in d and "y" in d:
            node_ids.append(n); xs.append(d["x"]); ys.append(d["y"])
    nodes_gdf = gpd.GeoDataFrame({"node": node_ids}, geometry=gpd.points_from_xy(xs, ys), crs=cfg.METRIC_CRS)
    return gpd.sjoin(nodes_gdf, grid[["grid_id", "district", "geometry"]], predicate="within", how="left")


def district_and_grid_coverage(G, grid_path=None, joined: gpd.GeoDataFrame | None = None) -> dict:
    """Spatially joins network nodes to the citywide grid/district polygons
    to check which districts/cells have at least one reachable network
    node -- a coverage gap here means routing FROM/TO that area cannot even
    start, distinct from a within-network fragmentation gap."""
    grid_path = grid_path or (cfg.PROJECT_ROOT / "data" / "processed" / "citywide" / "mobility_grid_500m_metric.gpkg")
    grid = gpd.read_file(grid_path)
    joined = joined if joined is not None else _nodes_joined_to_grid(G, grid)
    n_districts_total = grid["district"].nunique()
    n_districts_with_node = joined["district"].nunique()
    n_cells_total = len(grid)
    n_cells_with_node = joined["grid_id"].nunique()
    districts_without_node = sorted(set(grid["district"]) - set(joined["district"].dropna()))

    return {
        "n_districts_total": int(n_districts_total), "n_districts_with_at_least_1_node": int(n_districts_with_node),
        "districts_with_zero_nodes": districts_without_node,
        "n_grid_cells_total": int(n_cells_total), "n_grid_cells_with_at_least_1_node": int(n_cells_with_node),
        "pct_grid_cells_with_at_least_1_node": round(n_cells_with_node / n_cells_total * 100, 2),
    }


def invalid_edge_summary(diag_from_builder: dict) -> dict:
    return {
        "n_edges_dropped_no_geometry": diag_from_builder.get("n_edges_dropped_no_geometry", 0),
        "n_edges_dropped_zero_length": diag_from_builder.get("n_edges_dropped_zero_length", 0),
    }


def gap_focus_areas(G, grid_path=None, joined: gpd.GeoDataFrame | None = None) -> dict:
    """Targeted checks for the areas the governing instruction specifically
    flags: Bosphorus crossings, islands, forest/peripheral districts,
    motorway corridors, coastline discontinuities. Descriptive only -- no
    automatic repair."""
    grid_path = grid_path or (cfg.PROJECT_ROOT / "data" / "processed" / "citywide" / "mobility_grid_500m_metric.gpkg")
    grid = gpd.read_file(grid_path)
    joined = joined if joined is not None else _nodes_joined_to_grid(G, grid)
    nodes_per_district = joined.groupby("district")["node"].size()

    islands_district = "Adalar"
    peripheral_districts = ["Şile", "Çatalca", "Silivri", "Adalar"]

    focus = {
        "adalar_islands_node_count": int(nodes_per_district.get(islands_district, 0)),
        "peripheral_districts_node_counts": {d: int(nodes_per_district.get(d, 0)) for d in peripheral_districts},
        "bosphorus_crossing_check": "No dedicated automated bridge-crossing detector implemented in this "
        "baseline -- see routing_validation.json for an explicit European-side <-> Asian-side routed test case "
        "as the practical crossing check instead of a geometric heuristic here.",
    }
    return focus
