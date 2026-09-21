"""Phase 5C step 2: full k=3..10 candidate-k re-evaluation under the
selected building_coverage_ratio treatment (Candidate D: two-part
has_buildings + conditional intensity). Mirrors the original Phase 5B
step-1 methodology exactly, applied to the corrected feature geometry.

Writes to analysis/clustering_v2/ -- the original analysis/clustering/
outputs (k=7 baseline) are never touched.
"""

from __future__ import annotations

import json

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from libpysal.weights import Queen
from sklearn.cluster import KMeans
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.bcr_preprocessing_candidates import build_candidate_D, load_base_matrix
from src.citywide.clustering_phase5b_step1_kdiagnostics import build_queen_graph, fragmentation_diagnostics
from src.utils import config as cfg

EDA_DIR = cfg.PROJECT_ROOT / "analysis" / "eda"
V2_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering_v2"
K_RANGE = range(3, 11)
RANDOM_STATE = 42
SILHOUETTE_SAMPLE_SIZE = 5000


def build_v2_matrix():
    matrix, reduced_features = load_base_matrix()
    scaled_cols = [f"{c}_scaled" for c in reduced_features]
    other_cols = [c for c in scaled_cols if c != "building_coverage_ratio_scaled"]
    other_feature_names = [c.replace("_scaled", "") for c in other_cols]

    raw_bcr = matrix["building_coverage_ratio_raw"]
    has_buildings, conditional, d_diag = build_candidate_D(raw_bcr)

    feature_names = other_feature_names + ["has_buildings", "building_coverage_ratio_conditional"]
    X = np.column_stack([matrix[other_cols].to_numpy(), has_buildings, conditional])

    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")[["grid_id", "geometry"]]
    grid_df = matrix[["grid_id", "district"]].merge(grid, on="grid_id", how="left")
    grid_df = gpd.GeoDataFrame(grid_df, geometry="geometry", crs=cfg.METRIC_CRS).reset_index(drop=True)
    assert len(grid_df) == 22322 and grid_df["grid_id"].is_unique
    return grid_df, X, feature_names, d_diag


def main() -> None:
    print("=" * 72)
    print("Phase 5C step 2: candidate-k re-evaluation under Candidate D preprocessing")
    print("=" * 72)

    V2_DIR.mkdir(parents=True, exist_ok=True)
    grid_df, X, feature_names, d_diag = build_v2_matrix()
    print(f"Feature matrix: {len(grid_df)} cells x {len(feature_names)} features "
          f"(building_coverage_ratio replaced by has_buildings + building_coverage_ratio_conditional)")
    assert not np.isnan(X).any()

    print("\nBuilding Queen contiguity graph...")
    full_graph = build_queen_graph(grid_df)

    rng = np.random.default_rng(RANDOM_STATE)
    sil_sample_idx = rng.choice(len(X), size=min(SILHOUETTE_SAMPLE_SIZE, len(X)), replace=False)

    rows = []
    labels_by_k = {}
    for k in K_RANGE:
        print(f"\n[k={k}] fitting KMeans...")
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10).fit(X)
        labels = km.labels_
        labels_by_k[k] = labels

        sil = silhouette_score(X[sil_sample_idx], labels[sil_sample_idx])
        ch = calinski_harabasz_score(X, labels)
        db = davies_bouldin_score(X, labels)
        sizes = np.bincount(labels)
        frag = fragmentation_diagnostics(full_graph, labels)

        row = {
            "k": k, "silhouette_subsampled": round(float(sil), 4), "calinski_harabasz": round(float(ch), 1),
            "davies_bouldin": round(float(db), 4),
            "min_cluster_size": int(sizes.min()), "max_cluster_size": int(sizes.max()),
            "min_pct": round(float(sizes.min() / len(labels) * 100), 2),
            "max_pct": round(float(sizes.max() / len(labels) * 100), 2),
            "size_ratio_max_to_min": round(float(sizes.max() / sizes.min()), 2),
            "total_spatial_components": frag["total_components_all_clusters"],
            "mean_largest_component_share_weighted": frag["mean_largest_component_share_weighted_by_cluster_size"],
        }
        rows.append(row)
        print(f"  silhouette={sil:.4f} CH={ch:.1f} DB={db:.4f} size_range=[{sizes.min()},{sizes.max()}] "
              f"components={frag['total_components_all_clusters']} largest_share={frag['mean_largest_component_share_weighted_by_cluster_size']:.3f}")

    diagnostics_df = pd.DataFrame(rows)
    diagnostics_df.to_csv(V2_DIR / "candidate_k_diagnostics_v2.csv", index=False)
    print(f"\n[save] {V2_DIR / 'candidate_k_diagnostics_v2.csv'}")

    labels_df = pd.DataFrame({"grid_id": grid_df["grid_id"]})
    for k, labels in labels_by_k.items():
        labels_df[f"k{k}"] = labels
    labels_df.to_parquet(V2_DIR / "_candidate_k_labels_v2.parquet")

    (V2_DIR / "feature_names_v2.json").write_text(json.dumps(feature_names, indent=2), encoding="utf-8")
    (V2_DIR / "bcr_two_part_construction.json").write_text(json.dumps(d_diag, indent=2, default=str), encoding="utf-8")

    print("\n--- candidate-k diagnostics table (v2, Candidate D preprocessing) ---")
    print(diagnostics_df.to_string(index=False))


if __name__ == "__main__":
    main()
