"""Phase 9, Section 5: network-based cycling accessibility at 5/10/15
minutes -- exact mirror of Phase 8's build_15min_accessibility.py, only
substituting the cycling graph/anchor/edge-weight/destination-anchor set.

For every grid cell's CYCLING anchor, ONE cutoff-Dijkstra run (15-minute
cutoff) produces the full reachable-node/time set; the 5- and 10-minute
results are DERIVED by sub-filtering (not separate Dijkstra runs).

Destinations with cycling_snap_status == "QUESTIONABLE" are EXCLUDED from
counts, reported not hidden. Unreachable-within-15-min is NaN, never a
large finite placeholder.
"""

from __future__ import annotations

import json
import time
from collections import Counter

import geopandas as gpd
import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.network import accessibility, network_builder
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "cycling_accessibility"
NET_DIR = cfg.PROJECT_ROOT / "analysis" / "network_intelligence"
THRESHOLDS_MIN = [5, 10, 15]
CATEGORIES = ["A_food_groceries", "B_healthcare", "C_education", "D_daily_services",
              "E_retail_shopping", "F_leisure_social", "G_green_recreation", "H_public_transport_access"]


def main() -> None:
    print("=" * 72)
    print("Phase 9 Section 5: network-based cycling accessibility (5/10/15 min)")
    print("=" * 72)

    print("\n[1/4] Loading inputs...")
    G_cycle = network_builder.load_graph("cycling_graph")
    anchors = pd.read_parquet(NET_DIR / "grid_network_anchors.parquet")
    grid_districts = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")[["grid_id", "district"]]
    anchors = anchors.merge(grid_districts, on="grid_id", how="left")
    dest = pd.read_parquet(OUT_DIR / "cycling_destination_anchors.parquet", columns=["destination_id", "poi_category", "cycling_network_node", "cycling_snap_status"])
    n_dest_total = len(dest)
    dest_ok = dest[dest["cycling_snap_status"] == "OK"].copy()
    n_dest_excluded = n_dest_total - len(dest_ok)
    print(f"  destinations: {n_dest_total} total, {n_dest_excluded} QUESTIONABLE-anchor excluded, {len(dest_ok)} used")

    dest_nodes_by_cat = {}
    for cat in CATEGORIES:
        sub = dest_ok[dest_ok["poi_category"] == cat]
        dest_nodes_by_cat[cat] = Counter(sub["cycling_network_node"].tolist())
        print(f"    {cat}: {len(sub)} usable destinations at {len(dest_nodes_by_cat[cat])} distinct network nodes")

    print("\n[2/4] Running cutoff-Dijkstra for all grid origins (15-min cutoff, single pass, DIRECTED cycling graph)...")
    t0 = time.time()
    max_cutoff_s = max(THRESHOLDS_MIN) * 60
    per_threshold_rows = {t: [] for t in THRESHOLDS_MIN}
    nearest_time_rows = []

    for i, row in enumerate(anchors.itertuples(index=False)):
        grid_id, district, origin_node = row.grid_id, row.district, row.cycling_anchor_node
        reachable = accessibility.reachable_from_node(G_cycle, origin_node, "travel_time_cycle_s", max_cutoff_s)

        nearest_row = {"grid_id": grid_id, "district": district}
        thresh_rows = {t: {"grid_id": grid_id, "district": district} for t in THRESHOLDS_MIN}

        for cat in CATEGORIES:
            node_counts = dest_nodes_by_cat[cat]
            reachable_in_cat = {n: t for n, t in reachable.items() if n in node_counts}
            nearest_time_s = min(reachable_in_cat.values()) if reachable_in_cat else np.nan
            nearest_row[f"{cat}_nearest_time_min"] = round(nearest_time_s / 60, 3) if not np.isnan(nearest_time_s) else np.nan

            for t_min in THRESHOLDS_MIN:
                cutoff_s = t_min * 60
                count = sum(node_counts[n] for n, tt in reachable_in_cat.items() if tt <= cutoff_s)
                thresh_rows[t_min][f"{cat}_count_{t_min}min"] = count
                thresh_rows[t_min][f"{cat}_access_{t_min}min"] = count > 0

        nearest_time_rows.append(nearest_row)
        for t_min in THRESHOLDS_MIN:
            per_threshold_rows[t_min].append(thresh_rows[t_min])

        if (i + 1) % 5000 == 0:
            print(f"    ...{i+1}/{len(anchors)} origins done ({time.time()-t0:.0f}s elapsed)")

    elapsed = time.time() - t0
    print(f"  done in {elapsed:.1f}s ({elapsed/len(anchors)*1000:.2f} ms/origin) for {len(anchors)} origins")

    print("\n[3/4] Saving per-threshold accessibility tables...")
    for t_min in THRESHOLDS_MIN:
        df = pd.DataFrame(per_threshold_rows[t_min])
        df.to_parquet(OUT_DIR / f"cycling_accessibility_{t_min}min.parquet")
        print(f"  saved cycling_accessibility_{t_min}min.parquet ({len(df)} rows, {len(df.columns)} cols)")

    nearest_df = pd.DataFrame(nearest_time_rows)
    nearest_df.to_parquet(OUT_DIR / "cycling_nearest_service_times.parquet")
    print(f"  saved cycling_nearest_service_times.parquet")

    print("\n[4/4] Runtime + coverage diagnostics...")
    diag = {
        "n_origins": len(anchors), "n_destinations_total": n_dest_total,
        "n_destinations_excluded_questionable_anchor": n_dest_excluded,
        "n_destinations_used_by_category": {cat: len(dest_ok[dest_ok["poi_category"] == cat]) for cat in CATEGORIES},
        "runtime_seconds": round(elapsed, 1), "ms_per_origin": round(elapsed / len(anchors) * 1000, 3),
        "graph": "cycling (DIRECTED, respects oneway; oneway:bicycle contraflow NOT applied -- known limitation)",
        "baseline_speed_kmh": network_builder.CYCLING_SPEED_KMH,
        "method": "networkx cutoff-Dijkstra (exact), ONE 15-min run per origin, 5/10-min derived by sub-filtering "
                  "the same reachable set -- not 3 separate Dijkstra runs, not Euclidean buffers.",
        "unreachable_representation": "NaN for nearest_time_min when no category destination is reachable within "
                                       "the 15-minute search horizon -- never a large finite placeholder value.",
    }
    (OUT_DIR / "_phase9_accessibility_diagnostics.json").write_text(json.dumps(diag, indent=2, default=str), encoding="utf-8")
    print(json.dumps(diag, indent=2, default=str))


if __name__ == "__main__":
    main()
