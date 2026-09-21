"""Phase 5B-V2 step 1: candidate-k diagnostics for the eight-family V2
typology (CITYWIDE_V2_EIGHT_FAMILY_TYPOLOGY).

Mirrors clustering_phase5b_step1_kdiagnostics.py's methodology exactly
(same K_RANGE, RANDOM_STATE, SILHOUETTE_SAMPLE_SIZE, n_init, Queen-
contiguity fragmentation diagnostics), applied to the frozen Phase 5A-V2
56-feature scaled matrix instead of V1's 45-feature matrix. Adds seed
stability (multi-seed pairwise ARI) per k, which V1's step-1 did not
compute (V1 only checked seed stability once, at the final selected k) --
included here per this phase's explicit "seed stability" requirement in
the k-sweep table itself.

Diagnostics only -- no k is selected here.

Writes to analysis/clustering_v2_eight_family/ -- no V1 or Phase 5A-V2
frozen artifact is read-write; this script only reads them.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, calinski_harabasz_score, davies_bouldin_score, silhouette_score

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.clustering_phase5b_step1_kdiagnostics import build_queen_graph, fragmentation_diagnostics
from src.utils import config as cfg

FEATURES_DIR = cfg.DATA_FEATURES
V2EF_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering_v2_eight_family"
K_RANGE = range(3, 11)
RANDOM_STATE = 42
SILHOUETTE_SAMPLE_SIZE = 5000
STABILITY_SEEDS = [42, 1, 7, 123, 2024]


def load_v2ef_matrix():
    scaled = pd.read_parquet(FEATURES_DIR / "phase5a_v2_reduced_matrix_scaled.parquet")
    feature_cols = [c for c in scaled.columns if c != "grid_id"]
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")[["grid_id", "district", "geometry"]]
    grid_df = scaled[["grid_id"]].merge(grid, on="grid_id", how="left")
    grid_df = gpd.GeoDataFrame(grid_df, geometry="geometry", crs=cfg.METRIC_CRS).reset_index(drop=True)
    assert len(grid_df) == 22322 and grid_df["grid_id"].is_unique
    X = scaled[feature_cols].to_numpy()
    assert not np.isnan(X).any()
    return grid_df, X, feature_cols


def main() -> None:
    print("=" * 72)
    print("Phase 5B-V2 step 1: candidate-k diagnostics (KMeans, k=3..10, eight-family V2 matrix)")
    print("=" * 72)

    V2EF_DIR.mkdir(parents=True, exist_ok=True)
    grid_df, X, feature_cols = load_v2ef_matrix()
    print(f"Matrix: {len(grid_df)} cells x {len(feature_cols)} features")

    print("\nBuilding Queen contiguity graph (once, reused across all k)...")
    full_graph = build_queen_graph(grid_df)
    print(f"  {full_graph.number_of_nodes()} nodes, {full_graph.number_of_edges()} edges")

    rng = np.random.default_rng(RANDOM_STATE)
    sil_sample_idx = rng.choice(len(X), size=min(SILHOUETTE_SAMPLE_SIZE, len(X)), replace=False)

    rows = []
    labels_by_k = {}
    for k in K_RANGE:
        print(f"\n[k={k}] fitting KMeans (primary seed + {len(STABILITY_SEEDS) - 1} stability seeds)...")
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10).fit(X)
        labels = km.labels_
        labels_by_k[k] = labels

        sil = silhouette_score(X[sil_sample_idx], labels[sil_sample_idx])
        ch = calinski_harabasz_score(X, labels)
        db = davies_bouldin_score(X, labels)
        sizes = np.bincount(labels)
        frag = fragmentation_diagnostics(full_graph, labels)

        seed_labels = {RANDOM_STATE: labels}
        for seed in STABILITY_SEEDS:
            if seed == RANDOM_STATE:
                continue
            seed_labels[seed] = KMeans(n_clusters=k, random_state=seed, n_init=10).fit(X).labels_
        all_seeds = list(seed_labels.keys())
        pairwise_aris = [adjusted_rand_score(seed_labels[a], seed_labels[b])
                          for i, a in enumerate(all_seeds) for b in all_seeds[i + 1:]]

        row = {
            "k": k, "silhouette_subsampled": round(float(sil), 4), "calinski_harabasz": round(float(ch), 1),
            "davies_bouldin": round(float(db), 4),
            "min_cluster_size": int(sizes.min()), "max_cluster_size": int(sizes.max()),
            "min_pct": round(float(sizes.min() / len(labels) * 100), 2),
            "max_pct": round(float(sizes.max() / len(labels) * 100), 2),
            "size_ratio_max_to_min": round(float(sizes.max() / sizes.min()), 2),
            "cluster_sizes": sizes.tolist(),
            "total_spatial_components": frag["total_components_all_clusters"],
            "mean_largest_component_share_weighted": frag["mean_largest_component_share_weighted_by_cluster_size"],
            "seed_stability_mean_ari": round(float(np.mean(pairwise_aris)), 4),
            "seed_stability_min_ari": round(float(np.min(pairwise_aris)), 4),
        }
        rows.append(row)
        print(f"  silhouette={sil:.4f} CH={ch:.1f} DB={db:.4f} size_range=[{sizes.min()},{sizes.max()}] "
              f"({row['min_pct']}%-{row['max_pct']}%) components={frag['total_components_all_clusters']} "
              f"largest_share={frag['mean_largest_component_share_weighted_by_cluster_size']:.3f} "
              f"seed_ari(mean/min)={row['seed_stability_mean_ari']}/{row['seed_stability_min_ari']}")

    diagnostics_df = pd.DataFrame(rows)
    diagnostics_df.to_csv(V2EF_DIR / "candidate_k_diagnostics_v2ef.csv", index=False)
    print(f"\n[save] {V2EF_DIR / 'candidate_k_diagnostics_v2ef.csv'}")

    labels_df = pd.DataFrame({"grid_id": grid_df["grid_id"]})
    for k, labels in labels_by_k.items():
        labels_df[f"k{k}"] = labels
    labels_df.to_parquet(V2EF_DIR / "_candidate_k_labels_v2ef.parquet")
    print(f"[save] {V2EF_DIR / '_candidate_k_labels_v2ef.parquet'} (intermediate, for step 2)")

    print("\n--- candidate-k diagnostics table (eight-family V2) ---")
    print(diagnostics_df.drop(columns=["cluster_sizes"]).to_string(index=False))


if __name__ == "__main__":
    main()
