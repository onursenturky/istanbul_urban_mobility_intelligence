"""Phase 5A orchestrator: unsupervised urban mobility typology.

Run from the project root:
    .venv/bin/python -m src.analysis.build_typology
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from src.analysis.clustering import K_RANGE, RANDOM_STATE, compare_algorithms, fit_final_clustering, pca_diagnostics, select_best
from src.analysis.feature_screening import build_clustering_matrix
from src.analysis.spatial_diagnostics import binary_cluster_morans_i, build_queen_weights
from src.utils import config as cfg

TYPOLOGY_DIR = cfg.PROJECT_ROOT / "data" / "processed" / "typology"


def load_features() -> gpd.GeoDataFrame:
    gdf = gpd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features.parquet")
    assert len(gdf) == 514 and gdf["grid_id"].is_unique
    return gdf


def interpret_clusters(features_df: gpd.GeoDataFrame, feature_list: list[str], labels: np.ndarray) -> pd.DataFrame:
    df = features_df[feature_list].copy()
    df["cluster"] = labels
    cluster_means = df.groupby("cluster")[feature_list].mean()
    overall_mean = df[feature_list].mean()
    overall_std = df[feature_list].std().replace(0, np.nan)

    z = (cluster_means - overall_mean) / overall_std
    profiles = []
    for cluster_id in cluster_means.index:
        top_high = z.loc[cluster_id].sort_values(ascending=False).head(4)
        top_low = z.loc[cluster_id].sort_values().head(4)
        profiles.append({
            "cluster": int(cluster_id),
            "n_cells": int((labels == cluster_id).sum()),
            "pct_of_grid": round(float((labels == cluster_id).mean() * 100), 1),
            "distinctively_high": {k: round(float(v), 2) for k, v in top_high.items()},
            "distinctively_low": {k: round(float(v), 2) for k, v in top_low.items()},
        })
    profile_df = pd.DataFrame(profiles)
    cluster_means_out = cluster_means.copy()
    cluster_means_out.insert(0, "n_cells", profile_df.set_index("cluster")["n_cells"])
    return profile_df, cluster_means_out


def _map_extent(districts_gdf: gpd.GeoDataFrame):
    minx, miny, maxx, maxy = districts_gdf.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    return (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)


def make_typology_map(grid_with_clusters: gpd.GeoDataFrame, k: int) -> str:
    districts_gdf = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    extent = _map_extent(districts_gdf)
    fig, ax = plt.subplots(figsize=(11, 11))
    grid_with_clusters.plot(column="cluster", categorical=True, cmap="tab10", ax=ax, legend=True, edgecolor="#666666", linewidth=0.1, legend_kwds={"title": "Cluster"})
    districts_gdf.boundary.plot(ax=ax, linewidth=1.4, color="black", zorder=3)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_title(f"Unsupervised urban mobility typology (k={k})")
    ax.set_axis_off()
    out = cfg.OUTPUTS_MAPS / "typology_clusters.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def make_profile_heatmap(cluster_means: pd.DataFrame, feature_list: list[str]) -> str:
    from scipy.stats import zscore

    z = cluster_means[feature_list].apply(zscore)
    fig, ax = plt.subplots(figsize=(max(10, len(feature_list) * 0.35), max(6, len(cluster_means) * 0.6)))
    im = ax.imshow(z.values, cmap="RdBu_r", vmin=-2.5, vmax=2.5, aspect="auto")
    ax.set_xticks(range(len(feature_list)))
    ax.set_xticklabels(feature_list, rotation=90, fontsize=7)
    ax.set_yticks(range(len(cluster_means)))
    ax.set_yticklabels([f"Cluster {i} (n={int(n)})" for i, n in zip(cluster_means.index, cluster_means['n_cells'])])
    fig.colorbar(im, ax=ax, label="z-score of cluster mean vs. grid-wide mean")
    ax.set_title("Cluster feature profiles (standardized)")
    fig.tight_layout()
    out = cfg.OUTPUTS_MAPS / "typology_cluster_profiles.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def main() -> None:
    print("=" * 72)
    print("Phase 5A — Unsupervised Urban Mobility Typology")
    print("=" * 72)
    TYPOLOGY_DIR.mkdir(parents=True, exist_ok=True)

    features_df = load_features()
    X_scaled, feature_list, screening_diag = build_clustering_matrix(features_df)
    print("\n--- FEATURE SCREENING ---")
    print(json.dumps(screening_diag["redundancy_screening"], indent=2, default=str))
    print(json.dumps(screening_diag["transform_and_scale"], indent=2, default=str))

    pca_diag, pca_model, n_components_85 = pca_diagnostics(X_scaled)
    print("\n--- PCA DIAGNOSTICS ---")
    print(json.dumps(pca_diag, indent=2))

    X_pca = pd.DataFrame(
        PCA(n_components=n_components_85, random_state=RANDOM_STATE).fit_transform(X_scaled),
        index=X_scaled.index,
    )

    comparison_full = compare_algorithms(X_scaled, "full_feature_space")
    comparison_pca = compare_algorithms(X_pca, f"pca_{n_components_85}_components")
    comparison = pd.concat([comparison_full, comparison_pca], ignore_index=True)
    comparison.to_csv(TYPOLOGY_DIR / "clustering_algorithm_comparison.csv", index=False)

    representations = {"full_feature_space": X_scaled, f"pca_{n_components_85}_components": X_pca}

    def cluster_size_lookup(representation, algorithm, k):
        lbls = fit_final_clustering(representations[representation], algorithm, k)
        return list(pd.Series(lbls).value_counts())

    best = select_best(comparison, cluster_size_lookup=cluster_size_lookup)
    print("\n--- CLUSTER SELECTION (primary + degeneracy check + final) ---")
    print(json.dumps(best, indent=2))

    X_final = representations[best["representation"]]
    level1_labels = fit_final_clustering(X_final, best["algorithm"], best["k"])

    # k=2 is the genuine statistical optimum (strong, well-separated split)
    # but is too coarse to serve as a usable "typology" (one cluster holds
    # 88% of cells). Rather than override the quantitative result with a
    # different k chosen by preference, we keep it as Level 1 and apply the
    # SAME quantitative selection procedure recursively within the dominant
    # cluster, to reveal recurring sub-types where the actual variation
    # lives. This is decided as a fixed rule (triggered by the same
    # degeneracy check above), not a post-hoc visual adjustment, and is
    # capped at one refinement level to keep the typology interpretable.
    level1_sizes = pd.Series(level1_labels).value_counts()
    dominant_cluster_id = int(level1_sizes.idxmax())
    dominant_mask = level1_labels == dominant_cluster_id
    print(f"\n--- HIERARCHICAL REFINEMENT: re-clustering the dominant Level-1 cluster ({dominant_mask.sum()} cells) ---")

    X_scaled_sub = X_scaled[dominant_mask].reset_index(drop=True)
    pca_diag_sub, _, n_components_85_sub = pca_diagnostics(X_scaled_sub)
    X_pca_sub = pd.DataFrame(
        PCA(n_components=n_components_85_sub, random_state=RANDOM_STATE).fit_transform(X_scaled_sub),
    )
    sub_representations = {"full_feature_space": X_scaled_sub, f"pca_{n_components_85_sub}_components": X_pca_sub}
    comparison_sub = pd.concat([
        compare_algorithms(X_scaled_sub, "full_feature_space"),
        compare_algorithms(X_pca_sub, f"pca_{n_components_85_sub}_components"),
    ], ignore_index=True)

    def sub_cluster_size_lookup(representation, algorithm, k):
        lbls = fit_final_clustering(sub_representations[representation], algorithm, k)
        return list(pd.Series(lbls).value_counts())

    best_sub = select_best(comparison_sub, cluster_size_lookup=sub_cluster_size_lookup)
    print(json.dumps(best_sub, indent=2))
    sub_labels = fit_final_clustering(sub_representations[best_sub["representation"]], best_sub["algorithm"], best_sub["k"])

    # Merge: Level-1 non-dominant cluster(s) keep their own label; the
    # dominant cluster is replaced by its sub-cluster labels, renumbered to
    # continue after the non-dominant labels.
    final_labels = np.empty(len(level1_labels), dtype=int)
    next_label = 0
    non_dominant_ids = [c for c in level1_sizes.index if c != dominant_cluster_id]
    for old_id in non_dominant_ids:
        final_labels[level1_labels == old_id] = next_label
        next_label += 1
    sub_label_map = {old: next_label + i for i, old in enumerate(sorted(set(sub_labels)))}
    final_labels[dominant_mask] = [sub_label_map[s] for s in sub_labels]

    labels = final_labels
    best["hierarchical_refinement"] = {
        "level1_selection": best.get("final", best),
        "dominant_cluster_n_cells": int(dominant_mask.sum()),
        "level2_pca_diagnostics": pca_diag_sub,
        "level2_selection": best_sub,
        "final_n_clusters": int(len(set(labels))),
    }

    profile_df, cluster_means = interpret_clusters(features_df, feature_list, labels)
    profile_df.to_json(TYPOLOGY_DIR / "cluster_profiles.json", orient="records", indent=2)
    cluster_means.to_csv(TYPOLOGY_DIR / "cluster_means.csv")

    grid_with_clusters = features_df[["grid_id", "district", "geometry"]].copy()
    grid_with_clusters["cluster"] = labels
    grid_with_clusters.to_parquet(TYPOLOGY_DIR / "cluster_assignments.parquet")

    w = build_queen_weights(features_df[["grid_id", "geometry"]])
    cluster_spatial = binary_cluster_morans_i(labels, w)

    map_path = make_typology_map(grid_with_clusters, best["k"])
    profile_map_path = make_profile_heatmap(cluster_means, feature_list)

    print("\n--- CLUSTER PROFILES ---")
    print(json.dumps(profile_df.to_dict(orient="records"), indent=2, ensure_ascii=False))
    print("\n--- SPATIAL AUTOCORRELATION (per-cluster binary Moran's I) ---")
    print(json.dumps(cluster_spatial, indent=2))

    diagnostics = {
        "feature_screening": screening_diag,
        "pca_diagnostics": pca_diag,
        "algorithm_comparison_summary": comparison.to_dict(orient="records"),
        "selected": best,
        "cluster_profiles": profile_df.to_dict(orient="records"),
        "spatial_autocorrelation_per_cluster": cluster_spatial,
        "map_paths": {"typology_map": map_path, "cluster_profile_heatmap": profile_map_path},
    }
    with open(TYPOLOGY_DIR / "typology_diagnostics_report.json", "w", encoding="utf-8") as f:
        json.dump(diagnostics, f, indent=2, ensure_ascii=False, default=str)

    print("\n--- OUTPUT FILES ---")
    print(f"  {TYPOLOGY_DIR / 'cluster_assignments.parquet'}")
    print(f"  {TYPOLOGY_DIR / 'cluster_profiles.json'}")
    print(f"  {TYPOLOGY_DIR / 'cluster_means.csv'}")
    print(f"  {TYPOLOGY_DIR / 'clustering_algorithm_comparison.csv'}")
    print(f"  {TYPOLOGY_DIR / 'typology_diagnostics_report.json'}")
    print(f"  {map_path}")
    print(f"  {profile_map_path}")


if __name__ == "__main__":
    main()
