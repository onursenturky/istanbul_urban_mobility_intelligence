"""Phase 5B step 1: candidate-k diagnostics for citywide spatial typology.

Evaluates KMeans at k=3..10 on the Phase 5A reduced/scaled feature matrix
(analysis/eda/analysis_matrix_scaled.parquet), reporting silhouette (on a
fixed random subsample -- full pairwise silhouette on 22,322 points is
O(n^2) and impractical), Calinski-Harabasz and Davies-Bouldin (both
computed on the full data), cluster-size balance, and spatial fragmentation
(Queen-contiguity connected components per cluster).

This step produces diagnostics only -- no k is selected here. Selection is
a separate, reasoned step informed by these diagnostics plus profile
interpretability, not an automatic argmax rule.
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
from src.utils import config as cfg

EDA_DIR = cfg.PROJECT_ROOT / "analysis" / "eda"
CLUSTER_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering"
K_RANGE = range(3, 11)
RANDOM_STATE = 42
SILHOUETTE_SAMPLE_SIZE = 5000


def load_matrix():
    reduced = pd.read_csv(EDA_DIR / "reduced_feature_set.csv")
    reduced_features = reduced.loc[reduced["included_in_reduced_set"], "feature"].tolist()
    scaled_cols = [f"{c}_scaled" for c in reduced_features]

    analysis_matrix = pd.read_parquet(EDA_DIR / "analysis_matrix_scaled.parquet")
    missing = [c for c in scaled_cols if c not in analysis_matrix.columns]
    assert not missing, f"missing scaled columns: {missing}"

    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")[["grid_id", "geometry"]]
    merged = analysis_matrix[["grid_id", "district"] + scaled_cols].merge(grid, on="grid_id", how="left")
    merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=cfg.METRIC_CRS).reset_index(drop=True)
    assert len(merged) == 22322 and merged["grid_id"].is_unique
    return merged, reduced_features, scaled_cols


def build_queen_graph(grid: gpd.GeoDataFrame) -> nx.Graph:
    w = Queen.from_dataframe(grid, use_index=False)
    G = nx.Graph()
    G.add_nodes_from(range(len(grid)))
    for i, neighbors in w.neighbors.items():
        for j in neighbors:
            G.add_edge(i, j)
    return G


def fragmentation_diagnostics(full_graph: nx.Graph, labels: np.ndarray) -> dict:
    same_label_graph = nx.Graph()
    same_label_graph.add_nodes_from(full_graph.nodes)
    for i, j in full_graph.edges:
        if labels[i] == labels[j]:
            same_label_graph.add_edge(i, j)

    components = list(nx.connected_components(same_label_graph))
    comp_label = {}
    comp_size = {}
    for idx, comp in enumerate(components):
        any_node = next(iter(comp))
        comp_label[idx] = labels[any_node]
        comp_size[idx] = len(comp)

    per_cluster = {}
    for label in sorted(set(labels)):
        sizes = [comp_size[idx] for idx in comp_label if comp_label[idx] == label]
        total = sum(sizes)
        per_cluster[int(label)] = {
            "n_components": len(sizes),
            "largest_component_size": max(sizes),
            "largest_component_share": round(max(sizes) / total, 4),
        }

    total_components = len(components)
    weighted_largest_share = sum(
        v["largest_component_share"] * sum(1 for i in labels if i == k) for k, v in per_cluster.items()
    ) / len(labels)

    return {
        "total_components_all_clusters": total_components,
        "per_cluster": per_cluster,
        "mean_largest_component_share_weighted_by_cluster_size": round(float(weighted_largest_share), 4),
    }


def main() -> None:
    print("=" * 72)
    print("Phase 5B step 1: candidate-k diagnostics (KMeans, k=3..10)")
    print("=" * 72)

    CLUSTER_DIR.mkdir(parents=True, exist_ok=True)
    grid_df, reduced_features, scaled_cols = load_matrix()
    print(f"Analysis matrix: {len(grid_df)} cells x {len(scaled_cols)} scaled features")

    X = grid_df[scaled_cols].values
    assert not np.isnan(X).any(), "scaled matrix must have zero NaNs"

    print("\nBuilding Queen contiguity graph (once, reused across all k)...")
    full_graph = build_queen_graph(grid_df)
    print(f"  {full_graph.number_of_nodes()} nodes, {full_graph.number_of_edges()} edges")

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
        size_balance = {
            "min_cluster_size": int(sizes.min()), "max_cluster_size": int(sizes.max()),
            "min_pct": round(float(sizes.min() / len(labels) * 100), 2),
            "max_pct": round(float(sizes.max() / len(labels) * 100), 2),
            "size_ratio_max_to_min": round(float(sizes.max() / sizes.min()), 2),
        }

        frag = fragmentation_diagnostics(full_graph, labels)

        row = {
            "k": k, "silhouette_subsampled": round(float(sil), 4), "calinski_harabasz": round(float(ch), 1),
            "davies_bouldin": round(float(db), 4), **size_balance,
            "total_spatial_components": frag["total_components_all_clusters"],
            "mean_largest_component_share_weighted": frag["mean_largest_component_share_weighted_by_cluster_size"],
        }
        rows.append(row)
        print(f"  silhouette={sil:.4f} CH={ch:.1f} DB={db:.4f} size_range=[{sizes.min()},{sizes.max()}] "
              f"components={frag['total_components_all_clusters']} largest_share={frag['mean_largest_component_share_weighted_by_cluster_size']:.3f}")

    diagnostics_df = pd.DataFrame(rows)
    diagnostics_df.to_csv(CLUSTER_DIR / "candidate_k_diagnostics.csv", index=False)
    print(f"\n[save] {CLUSTER_DIR / 'candidate_k_diagnostics.csv'}")

    # Save labels for all k so step 2 (profiling + selection) doesn't need to refit
    labels_df = pd.DataFrame({"grid_id": grid_df["grid_id"]})
    for k, labels in labels_by_k.items():
        labels_df[f"k{k}"] = labels
    labels_df.to_parquet(CLUSTER_DIR / "_candidate_k_labels.parquet")
    print(f"[save] {CLUSTER_DIR / '_candidate_k_labels.parquet'} (intermediate, for profiling step)")

    print("\n--- candidate-k diagnostics table ---")
    print(diagnostics_df.to_string(index=False))


if __name__ == "__main__":
    main()
