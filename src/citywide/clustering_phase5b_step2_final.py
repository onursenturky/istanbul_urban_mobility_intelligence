"""Phase 5B step 2: final typology at the selected k, profiling, stability,
sensitivity, spatial coherence, and maps.

k=7 was selected in step 1 not by maximizing silhouette (which favors
k=3 monotonically) but by inspecting cluster profiles across k=4..10:
five smaller "high-activity" clusters are essentially stable in size and
profile across that whole range (real, robust structure), while the
k=6 -> k=7 transition splits an oversimplified ~80%-of-the-city
"background" cluster into two substantively different regimes -- a
moderately-populated-but-transit-poor suburban majority vs. a genuinely
remote/undeveloped periphery -- a distinction k<=6 erases. Beyond k=7,
further splits fragment the same two large clusters without revealing a
new regime (silhouette flattens, CH/DB continue their steady monotonic
decline with no further jump).
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from libpysal.weights import Queen
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, calinski_harabasz_score, davies_bouldin_score
from sklearn.mixture import GaussianMixture

from src.analysis.spatial_diagnostics import binary_cluster_morans_i
from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.clustering_phase5b_step1_kdiagnostics import build_queen_graph, fragmentation_diagnostics, load_matrix
from src.utils import config as cfg

EDA_DIR = cfg.PROJECT_ROOT / "analysis" / "eda"
CLUSTER_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering"
MAPS_DIR = CLUSTER_DIR / "maps"

FINAL_K = 7
RANDOM_STATE = 42
STABILITY_SEEDS = [42, 1, 7, 123, 2024]


def family_map(feat_dict: pd.DataFrame, features: list[str]) -> dict:
    return dict(zip(feat_dict["feature_name"], feat_dict["feature_family"]))


def auto_top_features(cluster_means: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    rows = []
    for cl in cluster_means.index:
        row = cluster_means.loc[cl]
        top_high = row.sort_values(ascending=False).head(n)
        top_low = row.sort_values().head(n)
        rows.append({
            "cluster": int(cl),
            "top_high": {k.replace("_scaled", ""): round(float(v), 3) for k, v in top_high.items()},
            "top_low": {k.replace("_scaled", ""): round(float(v), 3) for k, v in top_low.items()},
        })
    return pd.DataFrame(rows)


def name_clusters(profiles: pd.DataFrame) -> dict:
    """Neutral, descriptive names based on the actual computed top
    characteristics -- no suitability/quality language. Hand-reviewed
    against the real profile output, not purely string-templated."""
    # Filled in after inspecting the real k=7 profile output (see report).
    return {}


def main() -> None:
    print("=" * 72)
    print(f"Phase 5B step 2: final typology at k={FINAL_K}")
    print("=" * 72)

    grid_df, reduced_features, scaled_cols = load_matrix()
    feat_dict = pd.read_csv(cfg.DATA_PROCESSED / "metadata" / "feature_dictionary_citywide.csv")
    fam_map = family_map(feat_dict, reduced_features)

    X = grid_df[scaled_cols].values
    print(f"\n[1/7] Fitting final KMeans (k={FINAL_K}, random_state={RANDOM_STATE})...")
    km_final = KMeans(n_clusters=FINAL_K, random_state=RANDOM_STATE, n_init=10).fit(X)
    labels = km_final.labels_
    grid_df["cluster"] = labels

    assignments = grid_df[["grid_id", "district", "cluster"]].copy()
    assignments.to_parquet(CLUSTER_DIR / "cluster_assignments.parquet")
    print(f"  saved {CLUSTER_DIR / 'cluster_assignments.parquet'}")

    print("\n[2/7] Cluster profiles...")
    cluster_means = grid_df.groupby("cluster")[scaled_cols].mean()
    sizes = grid_df["cluster"].value_counts().sort_index()
    top_features = auto_top_features(cluster_means)

    family_profile = pd.DataFrame({
        fam: cluster_means[[c for c in scaled_cols if fam_map.get(c.replace("_scaled", "")) == fam]].mean(axis=1)
        for fam in sorted(set(fam_map.values()))
    })

    district_dist = grid_df.groupby(["cluster", "district"]).size().reset_index(name="n_cells")
    dominant_districts = {}
    for cl in sorted(grid_df["cluster"].unique()):
        sub = district_dist[district_dist["cluster"] == cl].sort_values("n_cells", ascending=False)
        dominant_districts[int(cl)] = sub.head(5)[["district", "n_cells"]].to_dict(orient="records")

    profiles = []
    for cl in sorted(grid_df["cluster"].unique()):
        profiles.append({
            "cluster": int(cl),
            "n_cells": int(sizes[cl]),
            "pct_of_city": round(float(sizes[cl] / len(grid_df) * 100), 2),
            "top_high_scaled_features": top_features.loc[top_features["cluster"] == cl, "top_high"].iloc[0],
            "top_low_scaled_features": top_features.loc[top_features["cluster"] == cl, "top_low"].iloc[0],
            "family_level_mean_scaled": family_profile.loc[cl].round(3).to_dict(),
            "dominant_districts_by_cell_count": dominant_districts[int(cl)],
        })
    profiles_df = pd.DataFrame(profiles)
    profiles_df.to_json(CLUSTER_DIR / "cluster_profiles.json", orient="records", indent=2, force_ascii=False)
    cluster_means.to_csv(CLUSTER_DIR / "cluster_profiles_scaled_means.csv")
    print(f"  saved {CLUSTER_DIR / 'cluster_profiles.json'} and cluster_profiles_scaled_means.csv")
    for p in profiles:
        print(f"  cluster {p['cluster']}: n={p['n_cells']} ({p['pct_of_city']}%) "
              f"top_high={list(p['top_high_scaled_features'].items())[:3]}")

    print("\n[3/7] Spatial coherence diagnostics...")
    full_graph = build_queen_graph(grid_df)
    frag = fragmentation_diagnostics(full_graph, labels)
    w = Queen.from_dataframe(grid_df, use_index=False)
    morans = binary_cluster_morans_i(labels, w)
    spatial_coherence = {"fragmentation": frag, "morans_i_per_cluster": morans}
    (CLUSTER_DIR / "spatial_coherence_diagnostics.json").write_text(
        json.dumps(spatial_coherence, indent=2, default=str), encoding="utf-8"
    )
    print(f"  saved spatial_coherence_diagnostics.json -- total components: {frag['total_components_all_clusters']}")
    for cl, m in morans.items():
        print(f"    {cl}: Moran's I={m['morans_i']} ({m['interpretation']})")

    print("\n[4/7] Alternative-method comparison (Gaussian Mixture, same k)...")
    gmm = GaussianMixture(n_components=FINAL_K, random_state=RANDOM_STATE, n_init=5).fit(X)
    gmm_labels = gmm.predict(X)
    ari_km_gmm = adjusted_rand_score(labels, gmm_labels)
    gmm_ch = calinski_harabasz_score(X, gmm_labels)
    gmm_db = davies_bouldin_score(X, gmm_labels)
    algo_comparison = {
        "kmeans": {"calinski_harabasz": round(float(calinski_harabasz_score(X, labels)), 1), "davies_bouldin": round(float(davies_bouldin_score(X, labels)), 4)},
        "gaussian_mixture": {"calinski_harabasz": round(float(gmm_ch), 1), "davies_bouldin": round(float(gmm_db), 4), "bic": round(float(gmm.bic(X)), 1)},
        "adjusted_rand_index_kmeans_vs_gmm": round(float(ari_km_gmm), 4),
    }
    print(f"  ARI(KMeans, GMM) = {ari_km_gmm:.4f} -- {algo_comparison}")

    print("\n[5/7] Stability across random seeds...")
    seed_labels = {}
    for seed in STABILITY_SEEDS:
        km_seed = KMeans(n_clusters=FINAL_K, random_state=seed, n_init=10).fit(X)
        seed_labels[seed] = km_seed.labels_
    pairwise_aris = []
    for i, s1 in enumerate(STABILITY_SEEDS):
        for s2 in STABILITY_SEEDS[i + 1:]:
            ari = adjusted_rand_score(seed_labels[s1], seed_labels[s2])
            pairwise_aris.append(ari)
    stability = {
        "seeds_tested": STABILITY_SEEDS,
        "pairwise_ari_mean": round(float(np.mean(pairwise_aris)), 4),
        "pairwise_ari_min": round(float(np.min(pairwise_aris)), 4),
        "pairwise_ari_max": round(float(np.max(pairwise_aris)), 4),
        "all_pairwise_aris": [round(float(a), 4) for a in pairwise_aris],
    }
    print(f"  pairwise ARI across {len(STABILITY_SEEDS)} seeds: mean={stability['pairwise_ari_mean']}, min={stability['pairwise_ari_min']}")

    print("\n[6/7] Sensitivity: excluding READY_WITH_LIMITATION features...")
    ready_only_features = [
        f for f in reduced_features
        if feat_dict.loc[feat_dict["feature_name"] == f, "classification"].iloc[0] == "READY"
    ]
    ready_only_scaled = [f"{c}_scaled" for c in ready_only_features]
    X_ready = grid_df[ready_only_scaled].values
    km_ready = KMeans(n_clusters=FINAL_K, random_state=RANDOM_STATE, n_init=10).fit(X_ready)
    ari_full_vs_ready = adjusted_rand_score(labels, km_ready.labels_)
    sensitivity = {
        "n_features_full": len(reduced_features), "n_features_ready_only": len(ready_only_features),
        "features_excluded": sorted(set(reduced_features) - set(ready_only_features)),
        "adjusted_rand_index_full_vs_ready_only": round(float(ari_full_vs_ready), 4),
        "interpretation": (
            "High ARI (>0.7) would indicate the broad typology structure is not driven by the "
            "READY_WITH_LIMITATION features specifically -- i.e. it is not an artifact of the temporally "
            "misaligned / İBB-only-definition variables. Lower ARI would indicate those variables "
            "materially shape the typology and their caveats should weigh more heavily on interpretation."
        ),
    }
    print(f"  ARI(full reduced set, READY-only) = {ari_full_vs_ready:.4f} using {len(ready_only_features)}/{len(reduced_features)} features")

    print("\n[7/7] Maps...")
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    districts_gdf = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    minx, miny, maxx, maxy = districts_gdf.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    extent = (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)

    fig, ax = plt.subplots(figsize=(12, 12))
    grid_df.plot(column="cluster", categorical=True, cmap="tab10", ax=ax, legend=True, edgecolor="none", legend_kwds={"title": "Cluster (neutral ID)"})
    districts_gdf.boundary.plot(ax=ax, linewidth=0.5, color="black", alpha=0.5, zorder=3)
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_title(f"Citywide spatial typology (k={FINAL_K}) -- descriptive clusters, not a suitability score")
    ax.set_axis_off()
    cluster_map_path = MAPS_DIR / "citywide_cluster_map.png"
    fig.savefig(cluster_map_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"  [map] {cluster_map_path}")

    fig, ax = plt.subplots(figsize=(9, 6))
    im = ax.imshow(family_profile.values, cmap="RdBu_r", vmin=-family_profile.values.max(), vmax=family_profile.values.max(), aspect="auto")
    ax.set_xticks(range(len(family_profile.columns))); ax.set_xticklabels(family_profile.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(family_profile.index))); ax.set_yticklabels([f"cluster {i}" for i in family_profile.index])
    ax.set_title("Family-level mean scaled profile by cluster")
    fig.colorbar(im, ax=ax, label="mean scaled value")
    family_map_path = MAPS_DIR / "family_profile_heatmap.png"
    fig.savefig(family_map_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"  [map] {family_map_path}")

    summary = {
        "final_k": FINAL_K,
        "selection_rationale": (
            "Quantitative metrics (silhouette, CH, DB) monotonically favor low k and do not by themselves "
            "select k=7. k=7 was chosen because five smaller high-activity clusters are stable in size/profile "
            "across k=4..10 (robust structure), while the k=6->k=7 transition splits an oversimplified "
            "~80%-of-the-city background cluster into two substantively different regimes (moderately "
            "populated but transit-poor suburbs vs. genuinely remote/undeveloped periphery) that k<=6 erases. "
            "Beyond k=7, further splits fragment the same two large clusters without revealing a new regime."
        ),
        "algorithm": "kmeans",
        "n_features": len(reduced_features),
        "features_used": reduced_features,
        "cluster_sizes": {int(k): int(v) for k, v in sizes.items()},
        "algorithm_comparison_kmeans_vs_gmm": algo_comparison,
        "stability_across_seeds": stability,
        "sensitivity_ready_only": sensitivity,
        "spatial_coherence_summary": {
            "total_spatial_components": frag["total_components_all_clusters"],
            "mean_largest_component_share_weighted": frag["mean_largest_component_share_weighted_by_cluster_size"],
            "per_cluster_fragmentation": frag["per_cluster"],
        },
        "interim_typology_limitation": (
            "This is an INTERIM six-family typology (buildings, POI, population, terrain, transit, cycling). "
            "Citywide land-use/green-space features (PARTIAL, 22/39 districts) and the full road network "
            "(PARTIAL, 0/39 districts) are NOT yet available and are entirely absent from this analysis -- "
            "their absence is not treated as zero, they are simply not represented. A future re-run once "
            "those layers are complete may reveal different or additional structure, particularly for "
            "green-space character and road-network-dependent measures (road grade, pct cycle-infra "
            "coverage of roads)."
        ),
        "outputs": {
            "candidate_k_diagnostics": str(CLUSTER_DIR / "candidate_k_diagnostics.csv"),
            "cluster_assignments": str(CLUSTER_DIR / "cluster_assignments.parquet"),
            "cluster_profiles": str(CLUSTER_DIR / "cluster_profiles.json"),
            "cluster_profiles_scaled_means": str(CLUSTER_DIR / "cluster_profiles_scaled_means.csv"),
            "spatial_coherence_diagnostics": str(CLUSTER_DIR / "spatial_coherence_diagnostics.json"),
            "cluster_map": str(cluster_map_path),
            "family_profile_heatmap": str(family_map_path),
        },
    }
    (CLUSTER_DIR / "phase5b_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[save] {CLUSTER_DIR / 'phase5b_summary.json'}")


if __name__ == "__main__":
    main()
