"""Phase 5B-V2 step 2: split-transition analysis across k=3..10 for the
eight-family V2 typology.

Independent KMeans fits at each k are not a hierarchy, so a "split" is
inferred from the contingency table between adjacent k solutions: for each
parent cluster (at k), we look at how its cells distribute across the
k+1 solution's clusters.
  - COHERENT_CARRYOVER: >=90% of the parent's cells land in a single k+1 cluster.
  - CLEAN_SPLIT: the top-2 destination clusters together hold >=90% of the
    parent's cells, and each holds >=15% (a genuine two-way split, not a
    trace spray of misclassified cells).
  - DISPERSED: neither of the above -- the parent's cells scatter across
    3+ meaningfully-sized destinations (harder to interpret as a clean split).

For each detected split, reports parent/child sizes, whether it creates a
tiny cluster (<3% of all cells), raw-feature-profile separation between the
children (percentile-of-citywide-median gap on a curated interpretable
feature set), and spatial coherence of each child (Queen-contiguity largest-
component share).
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import percentileofscore

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.clustering_phase5b_step1_kdiagnostics import build_queen_graph, fragmentation_diagnostics
from src.citywide.clustering_v2ef_step1_kdiagnostics import load_v2ef_matrix
from src.utils import config as cfg

FEATURES_DIR = cfg.DATA_FEATURES
V2EF_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering_v2_eight_family"
K_RANGE = list(range(3, 11))
N_CELLS = 22322

PROFILE_FEATURES = [
    "population_density_calibrated_km2", "poi_density_km2", "building_coverage_ratio",
    "total_transit_stop_count", "distance_to_nearest_transit_m",
    "cycle_infrastructure_density_km_per_km2_ibb_only",
    "mean_slope_deg", "mean_absolute_road_grade_pct",
    "road_density_km_per_km2", "intersection_density_km2",
    "green_area_ratio", "residential_area_ratio", "industrial_area_ratio",
]


def load_raw_profile_source() -> pd.DataFrame:
    v2 = pd.read_parquet(FEATURES_DIR / "urban_mobility_features_citywide_v2.parquet",
                          columns=["grid_id"] + PROFILE_FEATURES)
    return v2


def classify_transition(parent_labels: np.ndarray, child_labels: np.ndarray) -> dict:
    df = pd.DataFrame({"parent": parent_labels, "child": child_labels})
    result = {}
    for p in sorted(set(parent_labels)):
        sub = df[df["parent"] == p]
        dist = (sub["child"].value_counts() / len(sub)).sort_values(ascending=False)
        top = dist.head(3)
        if top.iloc[0] >= 0.90:
            kind = "COHERENT_CARRYOVER"
        elif len(top) >= 2 and top.iloc[0] + top.iloc[1] >= 0.90 and top.iloc[1] >= 0.15:
            kind = "CLEAN_SPLIT"
        else:
            kind = "DISPERSED"
        result[int(p)] = {
            "kind": kind, "parent_size": int(len(sub)),
            "destination_shares": {int(k): round(float(v), 4) for k, v in top.items()},
        }
    return result


def profile_gap(raw_df: pd.DataFrame, grid_df: pd.DataFrame, labels: np.ndarray, cluster_ids: list[int]) -> dict:
    df = raw_df.merge(grid_df[["grid_id"]], on="grid_id")
    df["cluster"] = labels
    out = {}
    for feat in PROFILE_FEATURES:
        citywide_vals = df[feat].dropna().to_numpy()
        medians = {}
        for cl in cluster_ids:
            vals = df.loc[df["cluster"] == cl, feat].dropna()
            if len(vals) == 0:
                continue
            med = float(vals.median())
            pct = float(percentileofscore(citywide_vals, med, kind="mean"))
            medians[int(cl)] = {"raw_median": round(med, 4), "citywide_percentile": round(pct, 1)}
        if len(medians) >= 2:
            pcts = [v["citywide_percentile"] for v in medians.values()]
            out[feat] = {"per_cluster": medians, "percentile_gap": round(max(pcts) - min(pcts), 1)}
    return out


def spatial_component_share(full_graph, labels: np.ndarray, cluster_ids: list[int]) -> dict:
    frag = fragmentation_diagnostics(full_graph, labels)
    return {cl: frag["per_cluster"].get(cl, frag["per_cluster"].get(str(cl))) for cl in cluster_ids}


def main() -> None:
    print("=" * 72)
    print("Phase 5B-V2 step 2: split-transition analysis across k=3..10")
    print("=" * 72)

    labels_df = pd.read_parquet(V2EF_DIR / "_candidate_k_labels_v2ef.parquet")
    grid_df, X, feature_cols = load_v2ef_matrix()
    raw_df = load_raw_profile_source()
    full_graph = build_queen_graph(grid_df)

    transitions = {}
    for k in K_RANGE[:-1]:
        k1 = k + 1
        parent_labels = labels_df[f"k{k}"].to_numpy()
        child_labels = labels_df[f"k{k1}"].to_numpy()
        trans = classify_transition(parent_labels, child_labels)

        print(f"\n=== k={k} -> k={k1} ===")
        detail = {}
        for p, info in trans.items():
            print(f"  parent {p} (n={info['parent_size']}, {info['parent_size']/N_CELLS*100:.1f}%): "
                  f"{info['kind']} -> {info['destination_shares']}")
            if info["kind"] == "CLEAN_SPLIT":
                children = list(info["destination_shares"].keys())[:2]
                child_sizes = {c: int((child_labels == c).sum()) for c in children}
                tiny = any(sz / N_CELLS < 0.03 for sz in child_sizes.values())
                gaps = profile_gap(raw_df, grid_df, child_labels, children)
                spatial = spatial_component_share(full_graph, child_labels, children)
                meaningful_gap_features = {f: g["percentile_gap"] for f, g in gaps.items() if g["percentile_gap"] >= 15}
                detail[f"parent_{p}"] = {
                    "children": children, "child_sizes": child_sizes,
                    "child_pct": {c: round(sz / N_CELLS * 100, 2) for c, sz in child_sizes.items()},
                    "creates_tiny_cluster_lt_3pct": tiny,
                    "n_features_with_percentile_gap_ge_15": len(meaningful_gap_features),
                    "top_distinguishing_features": dict(sorted(meaningful_gap_features.items(), key=lambda x: -x[1])[:5]),
                    "spatial_component_share_per_child": spatial,
                }
                print(f"    -> SPLIT detail: sizes={detail[f'parent_{p}']['child_pct']}%  tiny={tiny}  "
                      f"distinguishing_features(gap>=15pct)={detail[f'parent_{p}']['top_distinguishing_features']}")
        transitions[f"k{k}_to_k{k1}"] = {"classification": trans, "split_detail": detail}

    out_path = V2EF_DIR / "split_transition_analysis_v2ef.json"
    out_path.write_text(json.dumps(transitions, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[save] {out_path}")


if __name__ == "__main__":
    main()
