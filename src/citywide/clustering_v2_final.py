"""Phase 5C step 3: final typology under Candidate D preprocessing, at the
re-selected k=5. Full profiling (raw/percentile), spatial coherence, GMM
comparison, seed stability, all 4 ablations, family-dominance, maps.

k=5 was selected (not k=7) because it sits at the silhouette peak (0.2661,
tied with k=4's 0.2676) under the corrected feature geometry, preserves a
clean interpretable structure, and avoids the k=6 transition's silhouette
cliff (0.266 -> 0.179), which indicates a materially less well-separated
split at k=6 and beyond.

Writes to analysis/clustering_v2/ only -- analysis/clustering/ (the
original k=7 diagnostic baseline) is never modified.
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from libpysal.weights import Queen
from scipy.stats import percentileofscore
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, calinski_harabasz_score, davies_bouldin_score
from sklearn.mixture import GaussianMixture

from src.analysis.spatial_diagnostics import binary_cluster_morans_i
from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.bcr_preprocessing_candidates import build_candidate_D, load_base_matrix
from src.citywide.clustering_phase5b_step1_kdiagnostics import build_queen_graph, fragmentation_diagnostics
from src.citywide.clustering_v2_kdiagnostics import build_v2_matrix
from src.utils import config as cfg

CLUSTER_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering"  # original, read-only
V2_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering_v2"
MAPS_DIR = V2_DIR / "maps"
FINAL_K = 5
RANDOM_STATE = 42
STABILITY_SEEDS = [42, 1, 7, 123, 2024]

ABLATION_GROUPS = {
    "population_limitation_only": ["population_density_calibrated_km2"],
    "main_gtfs_transit_only": [
        "metro_station_count", "distance_to_nearest_metro_m", "tram_station_count", "distance_to_nearest_tram_m",
        "rail_station_count", "distance_to_nearest_rail_m", "ferry_terminal_count", "distance_to_nearest_ferry_m",
        "distance_to_nearest_transit_m", "transit_stops_within_500m", "transit_stops_within_1000m",
        "fixed_guideway_stations_within_1000m", "unique_rail_lines",
    ],
    "ibb_cycling_only": [
        "cycle_infrastructure_density_km_per_km2_ibb_only", "protected_cycleway_density_km_per_km2_ibb_only",
        "distance_to_nearest_cycle_infrastructure_m_ibb_only",
    ],
}


def bss_by_feature(X: np.ndarray, labels: np.ndarray, feature_names: list[str]) -> pd.Series:
    global_mean = X.mean(axis=0)
    bss = np.zeros(X.shape[1])
    for cl in np.unique(labels):
        mask = labels == cl
        n_k = mask.sum()
        cl_mean = X[mask].mean(axis=0)
        bss += n_k * (cl_mean - global_mean) ** 2
    return pd.Series(bss, index=feature_names)


def raw_percentile_profile(master: pd.DataFrame, grid_df: pd.DataFrame, features_for_profile: list[str]) -> pd.DataFrame:
    df = master[["grid_id"] + features_for_profile].merge(grid_df[["grid_id", "cluster"]], on="grid_id")
    rows = []
    for feat in features_for_profile:
        citywide_vals = df[feat].dropna().to_numpy()
        for cl, g in df.groupby("cluster"):
            vals = g[feat].dropna()
            median = float(vals.median())
            q1, q3 = float(vals.quantile(0.25)), float(vals.quantile(0.75))
            pct = float(percentileofscore(citywide_vals, median, kind="mean"))
            rows.append({
                "cluster": int(cl), "feature": feat, "raw_median": median, "raw_q1": q1, "raw_q3": q3,
                "raw_iqr": q3 - q1, "citywide_percentile_of_cluster_median": round(pct, 1),
                "pct_deviation_from_50": round(abs(pct - 50), 1),
            })
    return pd.DataFrame(rows)


def main() -> None:
    print("=" * 72)
    print(f"Phase 5C step 3: final typology at k={FINAL_K} (Candidate D preprocessing)")
    print("=" * 72)

    grid_df, X, feature_names, d_diag = build_v2_matrix()
    matrix, reduced_features = load_base_matrix()
    master = gpd.read_parquet(cfg.DATA_PROCESSED / "features" / "urban_mobility_features_citywide.parquet")
    feat_dict = pd.read_csv(cfg.DATA_PROCESSED / "metadata" / "feature_dictionary_citywide.csv")
    original_assignments = pd.read_parquet(CLUSTER_DIR / "cluster_assignments.parquet")

    print(f"\n[1/8] Fitting final KMeans (k={FINAL_K})...")
    km_final = KMeans(n_clusters=FINAL_K, random_state=RANDOM_STATE, n_init=10).fit(X)
    labels = km_final.labels_
    grid_df["cluster"] = labels

    assignments = grid_df[["grid_id", "district", "cluster"]].copy()
    assignments.to_parquet(V2_DIR / "cluster_assignments_v2.parquet")
    print(f"  saved {V2_DIR / 'cluster_assignments_v2.parquet'}")

    ari_vs_original = adjusted_rand_score(
        original_assignments.merge(grid_df[["grid_id"]], on="grid_id")["cluster"], labels
    )
    print(f"  ARI vs original k=7 (Candidate A) assignments: {ari_vs_original:.4f}")

    print("\n[2/8] Raw/percentile cluster profiles...")
    # Profile on RAW features where available (using the ORIGINAL raw
    # building_coverage_ratio for interpretability, plus has_buildings),
    # not the internal two-part scaled representation.
    profile_features = [f for f in reduced_features if f != "building_coverage_ratio"] + ["building_coverage_ratio"]
    profile_df = raw_percentile_profile(master, grid_df, profile_features)
    profile_df.to_csv(V2_DIR / "cluster_profiles_raw_percentile_v2.csv", index=False)

    top_dist = {}
    for cl, g in profile_df.groupby("cluster"):
        g_sorted = g.sort_values("pct_deviation_from_50", ascending=False).head(6)
        top_dist[int(cl)] = [
            {"feature": r["feature"], "raw_median": round(r["raw_median"], 3),
             "citywide_percentile": r["citywide_percentile_of_cluster_median"]}
            for _, r in g_sorted.iterrows()
        ]
    sizes = grid_df["cluster"].value_counts().sort_index()
    for cl, feats in top_dist.items():
        print(f"  cluster {cl} (n={sizes[cl]}, {sizes[cl]/len(grid_df)*100:.1f}%): " +
              "; ".join(f"{f['feature']}=med {f['raw_median']} (p{f['citywide_percentile']})" for f in feats[:3]))
    (V2_DIR / "cluster_top_distinguishing_by_percentile_v2.json").write_text(
        json.dumps(top_dist, indent=2, default=str), encoding="utf-8"
    )

    print("\n[3/8] Family-level profile + dominant districts...")
    fam_map = dict(zip(feat_dict["feature_name"], feat_dict["feature_family"]))
    scaled_family_cols = {}
    Xdf = pd.DataFrame(X, columns=feature_names)
    Xdf["cluster"] = labels
    families = sorted(set(fam_map.get(f.replace("_conditional", "").replace("has_buildings", "building_coverage_ratio")) for f in feature_names if f not in ("has_buildings", "building_coverage_ratio_conditional")) | {"buildings"})
    family_feature_map = {fam: [] for fam in families}
    for f in feature_names:
        base = f
        fam = "buildings" if f in ("has_buildings", "building_coverage_ratio_conditional") else fam_map.get(f)
        if fam:
            family_feature_map.setdefault(fam, []).append(f)
    family_profile = pd.DataFrame({fam: Xdf.groupby("cluster")[cols].mean().mean(axis=1) for fam, cols in family_feature_map.items() if cols})

    district_dist = grid_df.groupby(["cluster", "district"]).size().reset_index(name="n_cells")
    dominant_districts = {}
    for cl in sorted(grid_df["cluster"].unique()):
        sub = district_dist[district_dist["cluster"] == cl].sort_values("n_cells", ascending=False)
        dominant_districts[int(cl)] = sub.head(5)[["district", "n_cells"]].to_dict(orient="records")
        print(f"  cluster {cl} dominant districts: {dominant_districts[int(cl)][:3]}")

    profiles_out = []
    for cl in sorted(grid_df["cluster"].unique()):
        profiles_out.append({
            "cluster": int(cl), "n_cells": int(sizes[cl]), "pct_of_city": round(float(sizes[cl] / len(grid_df) * 100), 2),
            "top_distinguishing_raw_percentile": top_dist[int(cl)],
            "family_level_mean_scaled": family_profile.loc[cl].round(3).to_dict(),
            "dominant_districts": dominant_districts[int(cl)],
        })
    (V2_DIR / "cluster_profiles_v2.json").write_text(json.dumps(profiles_out, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"  saved cluster_profiles_v2.json")

    print("\n[4/8] Spatial coherence...")
    full_graph = build_queen_graph(grid_df)
    frag = fragmentation_diagnostics(full_graph, labels)
    w = Queen.from_dataframe(grid_df, use_index=False)
    morans = binary_cluster_morans_i(labels, w)
    (V2_DIR / "spatial_coherence_diagnostics_v2.json").write_text(
        json.dumps({"fragmentation": frag, "morans_i_per_cluster": morans}, indent=2, default=str), encoding="utf-8"
    )
    print(f"  total spatial components: {frag['total_components_all_clusters']}")
    for cl, m in morans.items():
        print(f"    {cl}: Moran's I={m['morans_i']} ({m['interpretation']})")

    print("\n[5/8] GMM comparison + seed stability...")
    gmm = GaussianMixture(n_components=FINAL_K, random_state=RANDOM_STATE, n_init=5).fit(X)
    gmm_labels = gmm.predict(X)
    ari_km_gmm = adjusted_rand_score(labels, gmm_labels)
    algo_comparison = {
        "kmeans": {"calinski_harabasz": round(float(calinski_harabasz_score(X, labels)), 1), "davies_bouldin": round(float(davies_bouldin_score(X, labels)), 4)},
        "gaussian_mixture": {"calinski_harabasz": round(float(calinski_harabasz_score(X, gmm_labels)), 1), "davies_bouldin": round(float(davies_bouldin_score(X, gmm_labels)), 4), "bic": round(float(gmm.bic(X)), 1)},
        "adjusted_rand_index_kmeans_vs_gmm": round(float(ari_km_gmm), 4),
    }
    print(f"  ARI(KMeans, GMM) = {ari_km_gmm:.4f}")

    seed_labels = {seed: KMeans(n_clusters=FINAL_K, random_state=seed, n_init=10).fit(X).labels_ for seed in STABILITY_SEEDS}
    pairwise_aris = [adjusted_rand_score(seed_labels[a], seed_labels[b]) for i, a in enumerate(STABILITY_SEEDS) for b in STABILITY_SEEDS[i + 1:]]
    stability = {"seeds_tested": STABILITY_SEEDS, "pairwise_ari_mean": round(float(np.mean(pairwise_aris)), 4), "pairwise_ari_min": round(float(np.min(pairwise_aris)), 4)}
    print(f"  seed stability: mean ARI={stability['pairwise_ari_mean']}, min={stability['pairwise_ari_min']}")

    print("\n[6/8] Family-specific ablations (re-run for k=5)...")
    scaled_cols_all = [f"{c}_scaled" for c in reduced_features if c != "building_coverage_ratio"] + ["has_buildings", "building_coverage_ratio_conditional"]
    ablation_results = {}
    for name, drop_feats in ABLATION_GROUPS.items():
        drop_scaled = {f"{f}_scaled" for f in drop_feats}
        keep_idx = [i for i, c in enumerate(scaled_cols_all) if c not in drop_scaled]
        X_ablated = X[:, keep_idx]
        km_ablated = KMeans(n_clusters=FINAL_K, random_state=RANDOM_STATE, n_init=10).fit(X_ablated)
        ari = adjusted_rand_score(labels, km_ablated.labels_)
        ablation_results[name] = {"n_features_dropped": len(drop_feats), "ari_vs_v2_baseline": round(float(ari), 4)}
        print(f"  {name}: ARI={ari:.4f}")

    all_limitation_feats = sorted(set(f for g in ABLATION_GROUPS.values() for f in g))
    drop_scaled = {f"{f}_scaled" for f in all_limitation_feats}
    keep_idx = [i for i, c in enumerate(scaled_cols_all) if c not in drop_scaled]
    km_all = KMeans(n_clusters=FINAL_K, random_state=RANDOM_STATE, n_init=10).fit(X[:, keep_idx])
    ari_all = adjusted_rand_score(labels, km_all.labels_)
    ablation_results["all_limitations_removed"] = {"n_features_dropped": len(all_limitation_feats), "ari_vs_v2_baseline": round(float(ari_all), 4)}
    print(f"  all_limitations_removed: ARI={ari_all:.4f}")
    (V2_DIR / "sensitivity_family_ablations_v2.json").write_text(json.dumps(ablation_results, indent=2, default=str), encoding="utf-8")

    print("\n[7/8] Feature-family dominance (final)...")
    bss = bss_by_feature(X, labels, feature_names)
    total_bss = bss.sum()
    bss_pct = (bss / total_bss * 100).sort_values(ascending=False)
    family_bss = {}
    for fam, cols in family_feature_map.items():
        if cols:
            family_bss[fam] = round(float(bss_pct.reindex(cols).sum()), 2)
    dominance_v2 = {"top10_predictors_by_bss_pct": bss_pct.head(10).round(2).to_dict(), "family_bss_share_pct": family_bss}
    (V2_DIR / "feature_family_dominance_v2.json").write_text(json.dumps(dominance_v2, indent=2, default=str), encoding="utf-8")
    print(f"  top10: {dominance_v2['top10_predictors_by_bss_pct']}")
    print(f"  family shares: {family_bss}")

    print("\n[8/8] Maps...")
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    districts_gdf = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    minx, miny, maxx, maxy = districts_gdf.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    extent = (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)

    fig, ax = plt.subplots(figsize=(12, 12))
    grid_df.plot(column="cluster", categorical=True, cmap="tab10", ax=ax, legend=True, edgecolor="none", legend_kwds={"title": "Cluster (neutral ID)"})
    districts_gdf.boundary.plot(ax=ax, linewidth=0.5, color="black", alpha=0.5, zorder=3)
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_title(f"Citywide spatial typology v2 (k={FINAL_K}, corrected building-coverage treatment)")
    ax.set_axis_off()
    fig.savefig(MAPS_DIR / "citywide_cluster_map_v2.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 6))
    fp_vals = family_profile.values
    im = ax.imshow(fp_vals, cmap="RdBu_r", vmin=-np.abs(fp_vals).max(), vmax=np.abs(fp_vals).max(), aspect="auto")
    ax.set_xticks(range(len(family_profile.columns))); ax.set_xticklabels(family_profile.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(family_profile.index))); ax.set_yticklabels([f"cluster {i}" for i in family_profile.index])
    ax.set_title("Family-level mean scaled profile by cluster (v2)")
    fig.colorbar(im, ax=ax, label="mean scaled value")
    fig.savefig(MAPS_DIR / "family_profile_heatmap_v2.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved maps under {MAPS_DIR}")

    summary = {
        "final_k": FINAL_K,
        "preprocessing": "Candidate D: two-part (has_buildings 0/1 + building_coverage_ratio_conditional, "
        "fit only on built cells, zero-building cells floored below the built-cell minimum)",
        "selection_rationale": (
            "Silhouette peaks at k=4 (0.2676) and k=5 (0.2661, effectively tied) under the corrected feature "
            "geometry. k=5 was chosen over k=4 because it adds one further clean, interpretable split (a "
            "distinct small retail/POI-specific node) without the silhouette cliff seen at k=6 (0.2661 -> 0.1787), "
            "which indicates a materially less defensible split from k=6 onward."
        ),
        "ari_vs_original_k7_candidate_a": round(float(ari_vs_original), 4),
        "cluster_sizes": {int(k): int(v) for k, v in sizes.items()},
        "algorithm_comparison_kmeans_vs_gmm": algo_comparison,
        "stability_across_seeds": stability,
        "sensitivity_family_ablations": ablation_results,
        "feature_family_dominance": dominance_v2,
        "interim_typology_limitation": (
            "Interim six-family typology (buildings, POI, population, terrain, transit, cycling). Citywide "
            "land-use/green-space (PARTIAL, 22/39 districts) and the road network (PARTIAL, 0/39 districts) "
            "remain unavailable and are not represented -- their absence is not treated as zero."
        ),
    }
    (V2_DIR / "phase5c_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[save] {V2_DIR / 'phase5c_summary.json'}")


if __name__ == "__main__":
    main()
