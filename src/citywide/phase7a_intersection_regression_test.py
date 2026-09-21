"""Phase 7A regression test: does a lightweight pyrosm u/v-degree method for
intersection_count reproduce the frozen OSMnx-graph G_u.degree() semantics
used by src.features.road_features.compute_road_features?

Baseline (A): the ACTUAL frozen pilot artifact data/raw/osm/osm_road_network_raw.graphml
(fetched live via OSMnx/Overpass for the exact pilot 3-district buffered
polygon) run through the real, unmodified compute_road_features().

Candidate (B): the PBF-derived pilot road extract
(data/raw/osm/pbf/pilot_road_network.osm.pbf, osmium-extracted from the same
istanbul.osm.pbf using the identical buffer/simplify parameters as the
pilot's own OSM query polygon), read via pyrosm.OSM.get_network(nodes=True),
projected to EPSG:32635, with node degree computed as the number of times
each node id appears across the concatenated u and v columns of the edges
table (no to_graph(), no directed-edge duplication step).

This intentionally does NOT just trust value_counts() -- it checks, on this
same PBF subset, whether get_network()'s edges are already direction-
deduplicated (one row per physical way/sub-edge) by comparing against a
to_graph()-based degree computed on the SAME small subset, before accepting
the lightweight method for citywide use.
"""

from __future__ import annotations

import json

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from pyrosm import OSM

from src.utils import config as cfg
from src.features.road_features import compute_road_features

PILOT_GRAPHML = cfg.DATA_RAW / "osm" / "osm_road_network_raw.graphml"
PILOT_PBF = cfg.DATA_RAW / "osm" / "pbf" / "pilot_road_network.osm.pbf"
PILOT_GRID = cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg"
OUT_PATH = cfg.DATA_PROCESSED / "qa" / "phase7a_intersection_regression.json"


def load_pilot_grid() -> gpd.GeoDataFrame:
    grid = gpd.read_file(PILOT_GRID)
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 514, f"expected the frozen pilot grid (514 cells), found {len(grid)}"
    return grid


def baseline_via_osmnx_graph(grid: gpd.GeoDataFrame) -> tuple[pd.Series, dict]:
    print(f"[A] loading frozen pilot graph: {PILOT_GRAPHML}")
    G = ox.load_graphml(PILOT_GRAPHML)
    result, diagnostics = compute_road_features(G, grid)
    print(f"    n_intersections_total (degree>=3, undirected): {diagnostics['n_intersections_total']}")
    return result.set_index("grid_id")["intersection_count"], diagnostics


def candidate_via_pyrosm_uv(grid: gpd.GeoDataFrame) -> tuple[pd.Series, dict]:
    print(f"[B] loading PBF-derived pilot road extract: {PILOT_PBF}")
    osm = OSM(str(PILOT_PBF))
    nodes, edges = osm.get_network(network_type="all", nodes=True)
    n_edges_get_network = len(edges)
    print(f"    get_network(): {len(nodes)} nodes, {n_edges_get_network} edges")

    # --- Verify get_network() is NOT direction-duplicated, before trusting
    # a plain value_counts() as a stand-in for undirected graph degree. ---
    G_di = osm.to_graph(nodes, edges, graph_type="networkx")
    n_edges_to_graph = G_di.number_of_edges()
    G_u_check = ox.convert.to_undirected(G_di)
    n_edges_undirected_check = G_u_check.number_of_edges()
    directed_duplication_ratio = n_edges_to_graph / n_edges_get_network if n_edges_get_network else float("nan")
    print(f"    to_graph(): {n_edges_to_graph} directed edges -> to_undirected(): {n_edges_undirected_check} edges")
    print(f"    directed_duplication_ratio (to_graph / get_network) = {directed_duplication_ratio:.4f}")
    print(f"    get_network_edges == undirected_graph_edges: {n_edges_get_network == n_edges_undirected_check}")

    edges_m = edges.to_crs(cfg.METRIC_CRS)
    nodes_m = nodes.to_crs(cfg.METRIC_CRS)

    degree_counts = pd.concat([edges_m["u"], edges_m["v"]]).value_counts()
    intersections_uv = nodes_m[nodes_m["id"].map(degree_counts).fillna(0) >= 3].copy()
    n_intersections_uv = len(intersections_uv)
    print(f"    n_intersections_total (uv value_counts >=3): {n_intersections_uv}")

    joined = gpd.sjoin(intersections_uv[["geometry"]], grid[["grid_id", "geometry"]], predicate="intersects", how="inner")
    counts = joined.groupby("grid_id").size().rename("intersection_count")
    counts = grid.set_index("grid_id").index.to_series().map(counts).fillna(0).astype(int)
    counts.index.name = "grid_id"

    diagnostics = {
        "n_nodes_get_network": len(nodes),
        "n_edges_get_network": n_edges_get_network,
        "n_edges_to_graph_directed": n_edges_to_graph,
        "n_edges_to_undirected_via_osmnx": n_edges_undirected_check,
        "directed_duplication_ratio": directed_duplication_ratio,
        "get_network_already_undirected": bool(n_edges_get_network == n_edges_undirected_check),
        "n_intersections_total_uv_method": n_intersections_uv,
    }
    return counts, diagnostics


def main() -> None:
    print("=" * 72)
    print("Phase 7A: intersection_count regression -- OSMnx graph vs pyrosm u/v")
    print("=" * 72)
    grid = load_pilot_grid()

    baseline, baseline_diag = baseline_via_osmnx_graph(grid)
    candidate, candidate_diag = candidate_via_pyrosm_uv(grid)

    compare = pd.DataFrame({"grid_id": grid["grid_id"], "district": grid["district"]})
    compare = compare.set_index("grid_id")
    compare["baseline_osmnx_graph"] = baseline
    compare["candidate_pyrosm_uv"] = candidate
    compare["diff"] = compare["candidate_pyrosm_uv"] - compare["baseline_osmnx_graph"]

    n_cells = len(compare)
    n_exact_match = int((compare["diff"] == 0).sum())
    agreement_rate = n_exact_match / n_cells * 100
    max_abs_diff = int(compare["diff"].abs().max())
    total_baseline = int(compare["baseline_osmnx_graph"].sum())
    total_candidate = int(compare["candidate_pyrosm_uv"].sum())
    total_diff = total_candidate - total_baseline
    total_diff_pct = total_diff / total_baseline * 100 if total_baseline else float("nan")

    worst_cells = compare.reindex(compare["diff"].abs().sort_values(ascending=False).index).head(15)

    by_district = compare.groupby("district").agg(
        n_cells=("diff", "size"),
        baseline_total=("baseline_osmnx_graph", "sum"),
        candidate_total=("candidate_pyrosm_uv", "sum"),
        n_exact_match=("diff", lambda s: int((s == 0).sum())),
        max_abs_diff=("diff", lambda s: int(s.abs().max())),
    )

    report = {
        "pilot_grid_cells": n_cells,
        "baseline_method": "OSMnx-fetched graph (osm_road_network_raw.graphml) -> compute_road_features() G_u.degree()",
        "candidate_method": "PBF-derived (osmium extract of istanbul.osm.pbf, same buffer/simplify as pilot query) -> pyrosm.get_network(nodes=True) -> u/v value_counts degree",
        "baseline_diagnostics": baseline_diag,
        "candidate_diagnostics": candidate_diag,
        "per_cell_exact_agreement_rate_pct": round(agreement_rate, 3),
        "n_cells_exact_match": n_exact_match,
        "n_cells_mismatch": n_cells - n_exact_match,
        "max_abs_cell_difference": max_abs_diff,
        "citywide_pilot_total_intersections_baseline": total_baseline,
        "citywide_pilot_total_intersections_candidate": total_candidate,
        "total_difference": total_diff,
        "total_difference_pct": round(total_diff_pct, 3),
        "by_district": by_district.to_dict(orient="index"),
        "worst_15_cells": worst_cells.reset_index().to_dict(orient="records"),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print("\n--- RESULT ---")
    print(f"per-cell exact agreement rate: {agreement_rate:.3f}% ({n_exact_match}/{n_cells})")
    print(f"max abs cell difference: {max_abs_diff}")
    print(f"total intersections -- baseline: {total_baseline}  candidate: {total_candidate}  diff: {total_diff} ({total_diff_pct:.3f}%)")
    print(f"get_network_already_undirected: {candidate_diag['get_network_already_undirected']}")
    print(f"[save] {OUT_PATH}")


if __name__ == "__main__":
    main()
