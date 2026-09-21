"""Phase 10, Sections 4-5: anchor deduplicated transit access points to the
FROZEN walking and cycling graphs, and assemble the origin-quality table
(reusing frozen grid anchor quality / component class / population /
district / V2 typology -- no new computation of any of those).
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

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "first_last_mile_transit"
CYC_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "cycling_accessibility"
WALK_VAL_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city" / "validation"
NET_DIR = cfg.PROJECT_ROOT / "analysis" / "network_intelligence"
SNAP_QUESTIONABLE_M = 1000.0


def anchor_to_graph(dest: gpd.GeoDataFrame, G, mode_label: str) -> pd.DataFrame:
    node_ids, xy = network_anchor._node_coords(G)
    tree = cKDTree(xy)
    dxy = np.column_stack([dest.geometry.x.to_numpy(), dest.geometry.y.to_numpy()])
    dist, idx = tree.query(dxy, k=1)
    out = pd.DataFrame({
        "access_point_id": dest["access_point_id"].to_numpy(),
        f"{mode_label}_node": node_ids[idx],
        f"{mode_label}_snap_distance_m": np.round(dist, 2),
    })
    out[f"{mode_label}_snap_status"] = np.where(out[f"{mode_label}_snap_distance_m"] > SNAP_QUESTIONABLE_M, "QUESTIONABLE", "OK")
    return out


def main() -> None:
    print("=" * 72)
    print("Phase 10 Sections 4-5: transit access-point anchoring + origin quality")
    print("=" * 72)

    print("\n[1/4] Loading deduplicated transit access points...")
    stops = gpd.read_parquet(OUT_DIR / "transit_access_point_dedup.parquet")
    print(f"  {len(stops)} access points")

    print("\n[2/4] Anchoring to walking graph...")
    G_walk = network_builder.load_graph("walking_graph")
    walk_anchor = anchor_to_graph(stops, G_walk, "walking")
    walk_out = stops[["access_point_id", "stop_id", "raw_stop_id", "stop_name", "mode", "district", "in_system_a", "in_system_b"]].merge(walk_anchor, on="access_point_id")
    assert len(walk_out) == len(stops), "anchoring must be 1:1 with access points"
    walk_out.to_parquet(OUT_DIR / "transit_walking_anchors.parquet")
    print(f"  walking anchoring QA by mode:")
    for m, g in walk_out.groupby("mode"):
        print(f"    {m}: n={len(g)}, median_snap={g['walking_snap_distance_m'].median():.1f}m, "
              f"p90={g['walking_snap_distance_m'].quantile(0.9):.1f}m, "
              f"n_questionable={(g['walking_snap_status']=='QUESTIONABLE').sum()}")
    print(f"[save] {OUT_DIR / 'transit_walking_anchors.parquet'}")

    print("\n[3/4] Anchoring to cycling graph...")
    G_cycle = network_builder.load_graph("cycling_graph")
    cyc_anchor = anchor_to_graph(stops, G_cycle, "cycling")
    cyc_out = stops[["access_point_id", "stop_id", "raw_stop_id", "stop_name", "mode", "district", "in_system_a", "in_system_b"]].merge(cyc_anchor, on="access_point_id")
    assert len(cyc_out) == len(stops), "anchoring must be 1:1 with access points"
    cyc_out.to_parquet(OUT_DIR / "transit_cycling_anchors.parquet")
    print(f"  cycling anchoring QA by mode:")
    for m, g in cyc_out.groupby("mode"):
        print(f"    {m}: n={len(g)}, median_snap={g['cycling_snap_distance_m'].median():.1f}m, "
              f"p90={g['cycling_snap_distance_m'].quantile(0.9):.1f}m, "
              f"n_questionable={(g['cycling_snap_status']=='QUESTIONABLE').sum()}")
    n_adalar_cyc = int((cyc_out["district"] == "Adalar").sum())
    print(f"  Adalar transit access points anchored to cycling graph: {n_adalar_cyc} "
          f"(these will cross water to the mainland mega-component -- known limitation, unchanged from Phase 9)")
    print(f"[save] {OUT_DIR / 'transit_cycling_anchors.parquet'}")

    anchor_qa = {
        "walking_by_mode": {m: {"n": int(len(g)), "median_snap_m": round(float(g["walking_snap_distance_m"].median()), 2),
                                  "p90_snap_m": round(float(g["walking_snap_distance_m"].quantile(0.9)), 2),
                                  "n_questionable": int((g["walking_snap_status"] == "QUESTIONABLE").sum())}
                             for m, g in walk_out.groupby("mode")},
        "cycling_by_mode": {m: {"n": int(len(g)), "median_snap_m": round(float(g["cycling_snap_distance_m"].median()), 2),
                                  "p90_snap_m": round(float(g["cycling_snap_distance_m"].quantile(0.9)), 2),
                                  "n_questionable": int((g["cycling_snap_status"] == "QUESTIONABLE").sum())}
                             for m, g in cyc_out.groupby("mode")},
        "adalar_cycling_cross_water_known_limitation": n_adalar_cyc,
    }
    (OUT_DIR / "_phase10_anchor_qa.json").write_text(json.dumps(anchor_qa, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {OUT_DIR / '_phase10_anchor_qa.json'} (intermediate)")

    print("\n[4/4] Assembling origin-quality table (reusing frozen quality artifacts, no recomputation)...")
    walk_quality = pd.read_parquet(WALK_VAL_DIR / "corrected_accessibility_quality_flags.parquet",
                                    columns=["grid_id", "district", "walking_snap_quality", "component_class", "corrected_quality_flag"]
                                    ).rename(columns={"component_class": "walking_component_class", "corrected_quality_flag": "walking_quality_flag"})
    cyc_quality = pd.read_parquet(CYC_DIR / "cycling_accessibility_quality_flags.parquet",
                                   columns=["grid_id", "cycling_snap_quality", "component_class", "corrected_quality_flag"]
                                   ).rename(columns={"component_class": "cycling_component_class", "corrected_quality_flag": "cycling_quality_flag"})
    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet", columns=["grid_id", "population_calibrated"])
    typology = pd.read_parquet(cfg.PROJECT_ROOT / "analysis" / "clustering_v2_eight_family" / "cluster_assignments_v2ef.parquet", columns=["grid_id", "cluster"])

    origin_quality = walk_quality.merge(cyc_quality, on="grid_id").merge(v2, on="grid_id").merge(typology, on="grid_id", how="left")
    origin_quality.to_parquet(OUT_DIR / "_origin_quality.parquet")
    print(f"  {len(origin_quality)} origins assembled")
    print(f"[save] {OUT_DIR / '_origin_quality.parquet'} (intermediate, reused by later Phase 10 sections)")


if __name__ == "__main__":
    main()
