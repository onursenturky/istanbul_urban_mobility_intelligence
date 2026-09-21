"""Phase 8.1 step 1: full connected-component audit of the walking network
and a data-driven (not mechanical) component classification.

Does NOT rebuild the network or recompute accessibility -- reads
data/processed/network/walking_graph.pkl (frozen Phase 7 artifact) and the
Phase 8 outputs (grid_network_anchors, accessibility_quality_flags,
population data) read-only.
"""

from __future__ import annotations

import json

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.network import network_builder
from src.utils import config as cfg

APP_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city"
VAL_DIR = APP_DIR / "validation"


def main() -> None:
    print("=" * 72)
    print("Phase 8.1 step 1: walking-network component audit")
    print("=" * 72)
    VAL_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/4] Loading walking graph + grid anchors...")
    G = network_builder.load_graph("walking_graph")
    anchors = pd.read_parquet(cfg.PROJECT_ROOT / "analysis" / "network_intelligence" / "grid_network_anchors.parquet")
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")[["grid_id", "district", "geometry"]]
    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet", columns=["grid_id", "population_calibrated"])
    anchors = anchors.merge(grid[["grid_id", "district"]], on="grid_id", how="left").merge(v2, on="grid_id", how="left")

    print("\n[2/4] Enumerating connected components...")
    comps = list(nx.connected_components(G))
    print(f"  {len(comps)} components, {G.number_of_nodes()} total nodes")

    node_to_comp = {}
    for i, comp in enumerate(comps):
        for n in comp:
            node_to_comp[n] = i
    anchors["walking_component_id"] = anchors["walking_anchor_node"].map(node_to_comp)

    print("\n[3/4] Computing per-component statistics...")
    comp_grid_ids = anchors.groupby("walking_component_id")["grid_id"].apply(list).to_dict()
    comp_pop = anchors.groupby("walking_component_id")["population_calibrated"].sum().to_dict()
    comp_districts = anchors.groupby("walking_component_id")["district"].apply(lambda s: sorted(s.dropna().unique().tolist())).to_dict()

    grid_geom = grid.set_index("grid_id")["geometry"]

    rows = []
    for i, comp in enumerate(comps):
        sub = G.subgraph(comp)
        n_nodes = sub.number_of_nodes()
        n_edges = sub.number_of_edges()
        total_len_km = sum(d.get("length_m", 0.0) for _, _, d in sub.edges(data=True)) / 1000
        gids = comp_grid_ids.get(i, [])
        n_cells = len(gids)
        pop = comp_pop.get(i, 0.0)
        districts = comp_districts.get(i, [])

        if n_cells > 0:
            geoms = grid_geom.reindex(gids).dropna()
            bounds = geoms.total_bounds if len(geoms) else None
            extent_km2 = None
            if bounds is not None and len(bounds) == 4:
                extent_km2 = round((bounds[2] - bounds[0]) * (bounds[3] - bounds[1]) / 1e6, 2)
        else:
            extent_km2 = None

        rows.append({
            "component_id": i, "n_nodes": n_nodes, "n_edges": n_edges, "total_length_km": round(total_len_km, 2),
            "n_anchored_grid_cells": n_cells, "calibrated_population": round(float(pop), 1),
            "n_districts": len(districts), "districts": ",".join(districts),
            "bbox_extent_km2": extent_km2,
        })

    comp_df = pd.DataFrame(rows).sort_values("n_nodes", ascending=False).reset_index(drop=True)
    comp_df["node_rank"] = range(1, len(comp_df) + 1)

    print(f"  size distribution (n_nodes): min={comp_df['n_nodes'].min()}, "
          f"p50={comp_df['n_nodes'].median():.0f}, p90={comp_df['n_nodes'].quantile(0.9):.0f}, "
          f"max={comp_df['n_nodes'].max()}")
    print(comp_df.head(10).to_string(index=False))

    print("\n[4/4] Deriving data-driven classification thresholds...")
    # Log-scale gaps in the size distribution reveal natural breakpoints,
    # rather than an arbitrary round-number cutoff.
    sizes = comp_df["n_nodes"].to_numpy()
    log_sizes = np.log10(sizes[sizes > 0])
    print(f"  log10(n_nodes) range: [{log_sizes.min():.2f}, {log_sizes.max():.2f}]")
    print(f"  top 10 component sizes: {sizes[:10].tolist()}")
    print(f"  size at rank 2 (2nd largest): {sizes[1] if len(sizes) > 1 else None}")
    gaps = -np.diff(np.sort(log_sizes)[::-1])
    top_gap_idx = np.argsort(gaps)[::-1][:5]
    print(f"  largest log-gaps between consecutive (sorted desc) components at ranks: {sorted(top_gap_idx.tolist())}")
    for idx in sorted(top_gap_idx.tolist())[:5]:
        print(f"    rank {idx+1}->{idx+2}: size {sizes[idx]} -> {sizes[idx+1]} (log gap {gaps[idx]:.3f})")

    comp_df.to_csv(VAL_DIR / "network_component_audit.csv", index=False)
    print(f"\n[save] {VAL_DIR / 'network_component_audit.csv'}")

    anchors[["grid_id", "district", "walking_anchor_node", "walking_component_id"]].to_parquet(VAL_DIR / "_grid_component_membership.parquet")
    print(f"[save] {VAL_DIR / '_grid_component_membership.parquet'} (intermediate)")


if __name__ == "__main__":
    main()
