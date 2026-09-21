"""Phase 9, Sections 1-2: cycling-network audit + cycling grid-anchor QA.

Reuses the FROZEN Phase 7 cycling graph (data/processed/network/cycling_graph.pkl)
and the FROZEN Phase 7 grid anchors (analysis/network_intelligence/
grid_network_anchors.parquet) read-only -- no rebuild, no new data.

Section 1: verifies node/edge/length counts against the Phase 7 frozen
values recorded in network_intelligence_manifest.json (integrity check,
not a rebuild), documents the KNOWN oneway:bicycle limitation (see
network_rules.py), and audits the cycling network's weakly-connected-
component structure using the SAME evidence-based method Phase 8.1 used
for walking (data-driven size/population/grid-coverage gaps, NOT the
walking-specific MAJOR_NODE_THRESHOLD=500,000 / LARGE_LOCAL_POP_THRESHOLD
=1,000 thresholds reused blindly -- cycling's own component-size
distribution is examined independently since it has 702 components vs
walking's 567, and cycling is a DIRECTED graph so weakly-connected
components are the correct reachability-relevant grouping).

Section 2: reports cycling grid-anchor quality (DIRECT/NEARBY/LARGE_SNAP/
QUESTIONABLE, snap-distance distribution, population affected by poor
anchors) from the already-computed cycling_* columns in
grid_network_anchors.parquet -- no new anchoring is computed here (that
was already done in Phase 7; anchors are IDENTICAL for Phase 9).
"""

from __future__ import annotations

import json

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.network import network_builder, network_rules
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "cycling_accessibility"
NET_DIR = cfg.PROJECT_ROOT / "analysis" / "network_intelligence"


def main() -> None:
    print("=" * 72)
    print("Phase 9 Sections 1-2: cycling network + grid-anchor audit")
    print("=" * 72)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/5] Loading frozen cycling graph + verifying vs Phase 7 metadata...")
    G = network_builder.load_graph("cycling_graph")
    net_manifest = json.loads((NET_DIR / "network_intelligence_manifest.json").read_text(encoding="utf-8"))
    frozen = net_manifest["cycling_network_qa_summary"]
    n_nodes, n_edges = G.number_of_nodes(), G.number_of_edges()
    total_len_km = sum(d.get("length_m", 0.0) for _, _, d in G.edges(data=True)) / 1000
    integrity = {
        "n_nodes_current": n_nodes, "n_nodes_frozen": frozen["n_nodes"], "n_nodes_match": n_nodes == frozen["n_nodes"],
        "n_edges_current": n_edges, "n_edges_frozen": frozen["n_edges"], "n_edges_match": n_edges == frozen["n_edges"],
        "total_length_km_current": round(total_len_km, 1), "total_length_km_frozen": frozen["total_length_km"],
        "is_directed": G.is_directed(),
    }
    print(f"  {integrity}")
    assert integrity["n_nodes_match"] and integrity["n_edges_match"], "Cycling graph does not match Phase 7 frozen metadata!"

    print("\n[2/5] Documenting known limitations (from network_rules.py, unchanged)...")
    cycling_rules = network_rules.cycling_rules()
    known_limitation = cycling_rules["directedness"]
    print(f"  oneway:bicycle limitation: {known_limitation}")

    print("\n[3/5] Enumerating weakly-connected components...")
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")[["grid_id", "district", "geometry"]]
    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet", columns=["grid_id", "population_calibrated"])
    anchors = pd.read_parquet(NET_DIR / "grid_network_anchors.parquet")
    anchors = anchors.merge(grid[["grid_id", "district"]], on="grid_id", how="left").merge(v2, on="grid_id", how="left")

    comps = list(nx.weakly_connected_components(G))
    print(f"  {len(comps)} weakly-connected components, {n_nodes} total nodes "
          f"(frozen Phase 7 count: {net_manifest['cycling_network_qa_summary'].get('n_nodes')} nodes, "
          f"per network_intelligence: n_weakly_connected_components should be 702)")

    node_to_comp = {}
    for i, comp in enumerate(comps):
        for n in comp:
            node_to_comp[n] = i
    anchors["cycling_component_id"] = anchors["cycling_anchor_node"].map(node_to_comp)

    print("\n[4/5] Computing per-component statistics...")
    comp_grid_ids = anchors.groupby("cycling_component_id")["grid_id"].apply(list).to_dict()
    comp_pop = anchors.groupby("cycling_component_id")["population_calibrated"].sum().to_dict()
    comp_districts = anchors.groupby("cycling_component_id")["district"].apply(lambda s: sorted(s.dropna().unique().tolist())).to_dict()
    grid_geom = grid.set_index("grid_id")["geometry"]

    rows = []
    for i, comp in enumerate(comps):
        sub = G.subgraph(comp)
        n_nd = sub.number_of_nodes()
        n_ed = sub.number_of_edges()
        total_l = sum(d.get("length_m", 0.0) for _, _, d in sub.edges(data=True)) / 1000
        gids = comp_grid_ids.get(i, [])
        n_cells = len(gids)
        pop = comp_pop.get(i, 0.0)
        districts = comp_districts.get(i, [])
        extent_km2 = None
        if n_cells > 0:
            geoms = grid_geom.reindex(gids).dropna()
            if len(geoms):
                b = geoms.total_bounds
                extent_km2 = round((b[2] - b[0]) * (b[3] - b[1]) / 1e6, 2)
        rows.append({
            "component_id": i, "n_nodes": n_nd, "n_edges": n_ed, "total_length_km": round(total_l, 2),
            "n_anchored_grid_cells": n_cells, "calibrated_population": round(float(pop), 1),
            "n_districts": len(districts), "districts": ",".join(districts), "bbox_extent_km2": extent_km2,
        })
    comp_df = pd.DataFrame(rows).sort_values("n_nodes", ascending=False).reset_index(drop=True)
    comp_df["node_rank"] = range(1, len(comp_df) + 1)

    print(f"  size distribution (n_nodes): min={comp_df['n_nodes'].min()}, "
          f"p50={comp_df['n_nodes'].median():.0f}, p90={comp_df['n_nodes'].quantile(0.9):.0f}, "
          f"max={comp_df['n_nodes'].max()}")
    print(comp_df.head(10).to_string(index=False))

    sizes = comp_df["n_nodes"].to_numpy()
    log_sizes = np.log10(sizes[sizes > 0])
    gaps = -np.diff(np.sort(log_sizes)[::-1])
    top_gap_idx = np.argsort(gaps)[::-1][:5]
    print(f"\n  largest log10-gaps between consecutive (rank-sorted) components:")
    for idx in sorted(top_gap_idx.tolist())[:5]:
        print(f"    rank {idx+1}->{idx+2}: size {sizes[idx]} -> {sizes[idx+1]} (log gap {gaps[idx]:.3f})")

    # Data-driven classification derived from CYCLING's own distribution
    # (mirrors Phase 8.1's method, not its exact thresholds).
    major_threshold = None
    biggest_gap_idx = int(np.argsort(gaps)[::-1][0])
    if gaps[biggest_gap_idx] > 1.0:  # >10x jump -- a genuine structural break
        major_threshold = int(sizes[biggest_gap_idx])
    pop_nonzero = comp_df.loc[(comp_df["calibrated_population"] > 0) & (comp_df["n_nodes"] < (major_threshold or sizes.max())), "calibrated_population"]
    large_local_pop_threshold = float(pop_nonzero.quantile(0.9)) if len(pop_nonzero) >= 10 else 1000.0
    large_local_pop_threshold = round(large_local_pop_threshold, -2) or 1000.0
    print(f"\n  derived MAJOR_NODE_THRESHOLD (cycling): {major_threshold} nodes "
          f"(from largest log-gap, {gaps[biggest_gap_idx]:.2f} log10 at rank {biggest_gap_idx+1}->{biggest_gap_idx+2})")
    print(f"  derived LARGE_LOCAL_POP_THRESHOLD (cycling): {large_local_pop_threshold} "
          f"(90th pct of non-major, populated component sizes)")

    def classify(row):
        if major_threshold is not None and row["n_nodes"] >= major_threshold:
            return "MAJOR_VALID_COMPONENT"
        districts = str(row["districts"]).split(",") if pd.notna(row["districts"]) and row["districts"] else []
        if districts == ["Adalar"]:
            return "KNOWN_NETWORK_LIMITATION"
        if row["n_anchored_grid_cells"] == 0 or row["calibrated_population"] == 0:
            return "QUESTIONABLE_FRAGMENT"
        if row["calibrated_population"] >= large_local_pop_threshold:
            return "LARGE_LOCAL_VALID_COMPONENT"
        return "SMALL_LOCAL_COMPONENT"

    comp_df["component_class"] = comp_df.apply(classify, axis=1)
    print("\n  component classification counts:")
    print(comp_df["component_class"].value_counts().to_string())
    print("\n  population by component class:")
    print(comp_df.groupby("component_class")["calibrated_population"].sum().round(1).to_string())

    comp_df.to_csv(OUT_DIR / "cycling_network_component_audit.csv", index=False)
    print(f"\n[save] {OUT_DIR / 'cycling_network_component_audit.csv'}")

    anchors[["grid_id", "district", "cycling_anchor_node", "cycling_component_id"]].to_parquet(
        OUT_DIR / "_grid_cycling_component_membership.parquet"
    )

    print("\n[5/5] Cycling grid-anchor quality report (from frozen Phase 7 anchors)...")
    qual_counts = anchors["cycling_snap_quality"].value_counts().to_dict()
    pct_direct_or_nearby = round(float(anchors["cycling_snap_quality"].isin(["DIRECT", "NEARBY"]).mean() * 100), 2)
    n_questionable = int((anchors["cycling_snap_quality"] == "QUESTIONABLE").sum())
    pop_by_quality = anchors.groupby("cycling_snap_quality")["population_calibrated"].sum().round(1).to_dict()
    snap_stats = {
        "min": float(anchors["cycling_snap_distance_m"].min()), "median": float(anchors["cycling_snap_distance_m"].median()),
        "mean": float(anchors["cycling_snap_distance_m"].mean()), "p90": float(anchors["cycling_snap_distance_m"].quantile(0.9)),
        "p99": float(anchors["cycling_snap_distance_m"].quantile(0.99)), "max": float(anchors["cycling_snap_distance_m"].max()),
    }
    print(f"  quality_counts: {qual_counts}")
    print(f"  pct_direct_or_nearby: {pct_direct_or_nearby}")
    print(f"  n_questionable: {n_questionable}, population in QUESTIONABLE cells: "
          f"{pop_by_quality.get('QUESTIONABLE', 0):,.0f}")
    print(f"  snap_distance_stats: {snap_stats}")

    audit_summary = {
        "section": "Phase 9 Sections 1-2",
        "graph_integrity_check_vs_phase7": integrity,
        "known_limitation_oneway_bicycle": known_limitation,
        "n_weakly_connected_components": len(comps),
        "component_classification_thresholds": {
            "MAJOR_VALID_COMPONENT": f">={major_threshold:,} nodes (data-driven, cycling-specific)" if major_threshold else "not applicable",
            "LARGE_LOCAL_VALID_COMPONENT": f">=1 anchored cell AND population>={large_local_pop_threshold:,.0f} (cycling-specific, 90th pct)",
            "SMALL_LOCAL_COMPONENT": ">=1 anchored cell AND 0<population<threshold",
            "QUESTIONABLE_FRAGMENT": "0 anchored cells, OR anchored cells with 0 population",
            "KNOWN_NETWORK_LIMITATION": "component's only district is Adalar",
        },
        "component_class_counts": comp_df["component_class"].value_counts().to_dict(),
        "component_class_population": comp_df.groupby("component_class")["calibrated_population"].sum().round(1).to_dict(),
        "cycling_anchor_quality_counts": qual_counts,
        "cycling_anchor_pct_direct_or_nearby": pct_direct_or_nearby,
        "cycling_anchor_n_questionable": n_questionable,
        "cycling_anchor_population_by_quality": pop_by_quality,
        "cycling_anchor_snap_distance_stats": snap_stats,
        "note": "Anchors are IDENTICAL to the frozen Phase 7 grid_network_anchors.parquet cycling_* columns -- "
                "no re-anchoring performed here, this is a QA report over existing frozen values.",
    }
    (OUT_DIR / "_phase9_network_anchor_audit_summary.json").write_text(
        json.dumps(audit_summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"[save] {OUT_DIR / '_phase9_network_anchor_audit_summary.json'} (intermediate)")


if __name__ == "__main__":
    main()
