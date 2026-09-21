"""Phase 10, Sections 6-8: walking + cycling accessibility to System A
(general transit) and System B (fixed-guideway) transit access points.

ONE cutoff-Dijkstra run per origin per graph (15-min cutoff) serves BOTH
systems (System B's access points are a subset of System A's node set) --
not 4 separate routing passes. 5/10-min results are derived by
sub-filtering the same reachable set, per this project's established
pattern (src/network/accessibility.py).

Baseline speeds are the SAME transparent constants used throughout this
project (network_builder.WALKING_SPEED_KMH=5.0, CYCLING_SPEED_KMH=15.0) --
no terrain adjustment, no stress/comfort penalty.
"""

from __future__ import annotations

import json
import time
from collections import Counter

import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.network import accessibility, network_builder
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "first_last_mile_transit"
NET_DIR = cfg.PROJECT_ROOT / "analysis" / "network_intelligence"
THRESHOLDS_MIN = [5, 10, 15]


def compute_mode_accessibility(G, weight_attr: str, anchors: pd.DataFrame, anchor_col: str,
                                access_points: pd.DataFrame, node_col: str, snap_status_col: str,
                                mode_label: str) -> dict[str, pd.DataFrame]:
    ap_ok = access_points[access_points[snap_status_col] == "OK"]
    nodes_a = Counter(ap_ok[node_col].tolist())
    nodes_b = Counter(ap_ok.loc[ap_ok["in_system_b"], node_col].tolist())
    print(f"  {mode_label}: System A nodes={len(nodes_a)} (from {len(ap_ok)} OK access points), "
          f"System B nodes={len(nodes_b)} (from {int(ap_ok['in_system_b'].sum())} OK access points)")

    max_cutoff_s = max(THRESHOLDS_MIN) * 60
    rows_a = []
    rows_b = []
    t0 = time.time()
    for i, row in enumerate(anchors.itertuples(index=False)):
        grid_id, district, origin_node = row.grid_id, row.district, getattr(row, anchor_col)
        reachable = accessibility.reachable_from_node(G, origin_node, weight_attr, max_cutoff_s)

        for system_label, node_counts, rows in [("A", nodes_a, rows_a), ("B", nodes_b, rows_b)]:
            reachable_in_system = {n: t for n, t in reachable.items() if n in node_counts}
            nearest_s = min(reachable_in_system.values()) if reachable_in_system else np.nan
            rec = {"grid_id": grid_id, "district": district,
                   "nearest_time_min": round(nearest_s / 60, 3) if not np.isnan(nearest_s) else np.nan}
            for t_min in THRESHOLDS_MIN:
                cutoff_s = t_min * 60
                count = sum(node_counts[n] for n, tt in reachable_in_system.items() if tt <= cutoff_s)
                rec[f"access_{t_min}min"] = count > 0
                rec[f"reachable_count_{t_min}min"] = count
            rows.append(rec)
        if (i + 1) % 5000 == 0:
            print(f"    ...{mode_label} {i+1}/{len(anchors)} origins done ({time.time()-t0:.0f}s elapsed)")

    elapsed = time.time() - t0
    print(f"  {mode_label} done in {elapsed:.1f}s ({elapsed/len(anchors)*1000:.2f} ms/origin)")
    return {"A": pd.DataFrame(rows_a), "B": pd.DataFrame(rows_b), "elapsed_s": elapsed,
            "n_system_a_ok_points": len(ap_ok), "n_system_b_ok_points": int(ap_ok["in_system_b"].sum())}


def main() -> None:
    print("=" * 72)
    print("Phase 10 Sections 6-8: walking + cycling transit accessibility (System A + B)")
    print("=" * 72)

    grid_anchors = pd.read_parquet(NET_DIR / "grid_network_anchors.parquet")
    origin_quality = pd.read_parquet(OUT_DIR / "_origin_quality.parquet", columns=["grid_id", "district"])
    anchors = grid_anchors.merge(origin_quality, on="grid_id", how="left")

    print("\n[1/3] Walking transit accessibility...")
    G_walk = network_builder.load_graph("walking_graph")
    walk_ap = pd.read_parquet(OUT_DIR / "transit_walking_anchors.parquet")
    walk_result = compute_mode_accessibility(G_walk, "travel_time_walk_s", anchors, "walking_anchor_node",
                                              walk_ap, "walking_node", "walking_snap_status", "walking")
    walk_result["A"].to_parquet(OUT_DIR / "walking_general_transit_accessibility.parquet")
    walk_result["B"].to_parquet(OUT_DIR / "walking_fixed_transit_accessibility.parquet")
    print(f"[save] walking_general_transit_accessibility.parquet, walking_fixed_transit_accessibility.parquet")

    print("\n[2/3] Cycling transit accessibility...")
    G_cycle = network_builder.load_graph("cycling_graph")
    cyc_ap = pd.read_parquet(OUT_DIR / "transit_cycling_anchors.parquet")
    cyc_result = compute_mode_accessibility(G_cycle, "travel_time_cycle_s", anchors, "cycling_anchor_node",
                                             cyc_ap, "cycling_node", "cycling_snap_status", "cycling")
    cyc_result["A"].to_parquet(OUT_DIR / "cycling_general_transit_accessibility.parquet")
    cyc_result["B"].to_parquet(OUT_DIR / "cycling_fixed_transit_accessibility.parquet")
    print(f"[save] cycling_general_transit_accessibility.parquet, cycling_fixed_transit_accessibility.parquet")

    print("\n[3/3] Primary threshold definitions + diagnostics...")
    walk_a10 = int(walk_result["A"]["access_10min"].sum())
    walk_b15 = int(walk_result["B"]["access_15min"].sum())
    cyc_a10 = int(cyc_result["A"]["access_10min"].sum())
    cyc_b15 = int(cyc_result["B"]["access_15min"].sum())
    n = len(anchors)
    print(f"  WALK_TRANSIT_10MIN_ACCESS: {walk_a10}/{n} ({walk_a10/n*100:.2f}%)")
    print(f"  WALK_FIXED_15MIN_ACCESS: {walk_b15}/{n} ({walk_b15/n*100:.2f}%)")
    print(f"  CYCLE_TRANSIT_10MIN_ACCESS: {cyc_a10}/{n} ({cyc_a10/n*100:.2f}%)")
    print(f"  CYCLE_FIXED_15MIN_ACCESS: {cyc_b15}/{n} ({cyc_b15/n*100:.2f}%)")

    diag = {
        "n_origins": n,
        "primary_definitions": {
            "WALK_TRANSIT_10MIN_ACCESS": {"n_cells": walk_a10, "pct_cells": round(walk_a10/n*100, 2)},
            "WALK_FIXED_15MIN_ACCESS": {"n_cells": walk_b15, "pct_cells": round(walk_b15/n*100, 2)},
            "CYCLE_TRANSIT_10MIN_ACCESS": {"n_cells": cyc_a10, "pct_cells": round(cyc_a10/n*100, 2)},
            "CYCLE_FIXED_15MIN_ACCESS": {"n_cells": cyc_b15, "pct_cells": round(cyc_b15/n*100, 2)},
        },
        "note": "These are descriptive thresholds, not claims of universal planning standards. Full 5/10/15-minute "
                "curves for both systems and both modes are retained in the per-system parquet files.",
        "walking_runtime_s": round(walk_result["elapsed_s"], 1),
        "cycling_runtime_s": round(cyc_result["elapsed_s"], 1),
        "n_system_a_ok_access_points_walking": walk_result["n_system_a_ok_points"],
        "n_system_b_ok_access_points_walking": walk_result["n_system_b_ok_points"],
        "n_system_a_ok_access_points_cycling": cyc_result["n_system_a_ok_points"],
        "n_system_b_ok_access_points_cycling": cyc_result["n_system_b_ok_points"],
        "unreachable_representation": "NaN for nearest_time_min when no access point of that system is reachable "
                                       "within the 15-minute search horizon -- never a large finite placeholder.",
    }
    (OUT_DIR / "_phase10_accessibility_diagnostics.json").write_text(json.dumps(diag, indent=2, default=str), encoding="utf-8")
    print(f"\n[save] {OUT_DIR / '_phase10_accessibility_diagnostics.json'} (intermediate)")


if __name__ == "__main__":
    main()
