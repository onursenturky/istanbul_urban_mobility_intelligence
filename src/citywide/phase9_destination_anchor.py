"""Phase 9, Section 3-4: anchor the FROZEN Phase 8 destination set to the
cycling network, and document the baseline cycling speed assumption.

Reuses poi_network_anchors.parquet's destination_id/poi_category/name/
geometry AS-IS (the SAME 81,854 destinations across the SAME 8 categories)
-- only re-anchors each destination's NEAREST NODE against the cycling
graph instead of the walking graph, using the identical cKDTree
nearest-node method already used in Phase 8
(build_15min_taxonomy_destinations.anchor_destinations_to_network).

Section 4 (baseline speed): the cycling graph's travel_time_cycle_s edge
attribute was computed in Phase 7 (network_builder.py) from a constant
baseline speed of 15.0 km/h (network_builder.CYCLING_SPEED_KMH) -- no
terrain adjustment, no comfort/stress penalty. Distance (length_m) and
time (travel_time_cycle_s) remain separate edge attributes throughout.
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.network import network_anchor, network_builder
from src.utils import config as cfg

APP_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city"
OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "cycling_accessibility"
SNAP_QUESTIONABLE_M = 1000.0


def main() -> None:
    print("=" * 72)
    print("Phase 9 Sections 3-4: destination anchoring to cycling network + baseline speed")
    print("=" * 72)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/3] Loading frozen Phase 8 destination set (walking-anchored) -- reusing category/geometry AS-IS...")
    dest_walk = gpd.read_parquet(APP_DIR / "poi_network_anchors.parquet")
    print(f"  {len(dest_walk)} destinations across {dest_walk['poi_category'].nunique()} categories (unchanged from Phase 8)")
    dest = dest_walk[["destination_id", "poi_category", "name", "geometry"]].copy()

    print("\n[2/3] Re-anchoring to the cycling graph (nearest-node cKDTree, same method as Phase 8)...")
    G_cycle = network_builder.load_graph("cycling_graph")
    node_ids, xy = network_anchor._node_coords(G_cycle)
    tree = cKDTree(xy)
    dxy = np.column_stack([dest.geometry.x.to_numpy(), dest.geometry.y.to_numpy()])
    dist, idx = tree.query(dxy, k=1)
    dest["cycling_network_node"] = node_ids[idx]
    dest["cycling_snap_distance_m"] = np.round(dist, 2)
    dest["cycling_snap_status"] = np.where(dest["cycling_snap_distance_m"] > SNAP_QUESTIONABLE_M, "QUESTIONABLE", "OK")

    dest_out = dest.drop(columns="geometry").copy()
    dest_out["geometry"] = dest.geometry
    dest_out = gpd.GeoDataFrame(dest_out, geometry="geometry", crs=cfg.METRIC_CRS)
    dest_out.to_parquet(OUT_DIR / "cycling_destination_anchors.parquet")
    print(f"[save] {OUT_DIR / 'cycling_destination_anchors.parquet'}")

    print("\n[3/3] Anchoring success by category (cycling vs walking, for comparison)...")
    by_cat = []
    for cat, g in dest_out.groupby("poi_category"):
        walk_g = dest_walk[dest_walk["poi_category"] == cat]
        by_cat.append({
            "poi_category": cat, "n_destinations": len(g),
            "cycling_snap_distance_median_m": round(float(g["cycling_snap_distance_m"].median()), 2),
            "cycling_snap_distance_p90_m": round(float(g["cycling_snap_distance_m"].quantile(0.9)), 2),
            "cycling_snap_distance_max_m": round(float(g["cycling_snap_distance_m"].max()), 2),
            "cycling_n_questionable": int((g["cycling_snap_status"] == "QUESTIONABLE").sum()),
            "cycling_pct_ok": round(float((g["cycling_snap_status"] == "OK").mean() * 100), 2),
            "walking_pct_ok": round(float((walk_g["snap_status"] == "OK").mean() * 100), 2),
        })
    by_cat_df = pd.DataFrame(by_cat)
    print(by_cat_df.to_string(index=False))

    summary = {
        "section": "Phase 9 Sections 3-4",
        "destination_set_reused_unchanged_from": "analysis/applications/15min_city/poi_network_anchors.parquet (Phase 8, FROZEN)",
        "n_destinations": len(dest_out),
        "categories": sorted(dest_out["poi_category"].unique().tolist()),
        "anchoring_method": "Nearest cycling-graph node via cKDTree on node (x,y), identical method to Phase 8's "
                             "walking anchoring -- only the target graph differs.",
        "anchoring_success_by_category": by_cat_df.to_dict(orient="records"),
        "baseline_cycling_speed_kmh": network_builder.CYCLING_SPEED_KMH,
        "baseline_speed_assumption": "Constant 15.0 km/h for ALL cycling edges regardless of grade, surface, or "
                                      "traffic stress -- the SAME transparent baseline defined in Phase 7 "
                                      "(network_builder.py). No terrain-adjusted speed or comfort/stress penalty "
                                      "is introduced in Phase 9. Distance (length_m) and time "
                                      "(travel_time_cycle_s) are stored as separate edge attributes throughout.",
    }
    (OUT_DIR / "_phase9_destination_anchor_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"\n[save] {OUT_DIR / '_phase9_destination_anchor_summary.json'} (intermediate)")


if __name__ == "__main__":
    main()
