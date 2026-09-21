"""Phase 5B-V2 step 4: final V2 typology (CITYWIDE_V2_EIGHT_FAMILY_TYPOLOGY,
k=5 selected -- see selection_rationale in the saved summary), V1<->V2
comparison, spatial change analysis + attribution to new road/land-use
information, controlled ablations, and algorithm/limitation robustness.

Reuses the k=5 labels already fit and stored in step 1
(_candidate_k_labels_v2ef.parquet) for the primary assignment, so the
"selected" solution is bit-identical to what step 1/2/3 already profiled --
no silent re-fit with different results.

Writes to analysis/clustering_v2_eight_family/ only. V1
(analysis/clustering_v2/) and all Phase 5A-V2 / V2 baseline artifacts are
read-only inputs.
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from libpysal.weights import Queen
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.metrics import (
    adjusted_rand_score, calinski_harabasz_score, davies_bouldin_score,
    normalized_mutual_info_score,
)
from sklearn.mixture import GaussianMixture

from src.analysis.spatial_diagnostics import binary_cluster_morans_i
from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.clustering_phase5b_step1_kdiagnostics import build_queen_graph, fragmentation_diagnostics
from src.citywide.clustering_v2ef_step1_kdiagnostics import load_v2ef_matrix
from src.utils import config as cfg

FEATURES_DIR = cfg.DATA_FEATURES
V2EF_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering_v2_eight_family"
V1_TYPOLOGY_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering_v2"  # frozen V1 Candidate-D k=5 typology
SELECTED_K = 5
RANDOM_STATE = 42
STABILITY_SEEDS = [42, 1, 7, 123, 2024]
VERSION_TAG = "CITYWIDE_V2_EIGHT_FAMILY_TYPOLOGY"

ROAD_COLS = ["major_road_length_m", "local_road_length_m", "road_density_km_per_km2",
             "intersection_density_km2", "cycle_accessible_road_density_km_per_km2"]
LANDUSE_COLS = ["green_area_ratio", "landuse_has_mapped_evidence", "residential_share_conditional",
                "industrial_share_conditional"]
ROAD_GRADE_COLS = ["mean_absolute_road_grade_pct", "pct_road_length_grade_gt_8pct"]

LIMITATION_GROUPS = {
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

ATTRIBUTION_FEATURES = [
    "road_density_km_per_km2", "intersection_density_km2", "major_road_length_m", "local_road_length_m",
    "mean_absolute_road_grade_pct", "green_area_ratio", "residential_area_ratio", "industrial_area_ratio",
]


def fit_kmeans(X: np.ndarray, k: int, seed: int = RANDOM_STATE) -> np.ndarray:
    return KMeans(n_clusters=k, random_state=seed, n_init=10).fit(X).labels_


def best_match_mapping(v1_labels: np.ndarray, v2_labels: np.ndarray) -> tuple[dict, np.ndarray]:
    """Hungarian-algorithm best-match mapping V2 cluster -> V1 cluster
    (maximizing overlap), for interpretive comparison ONLY -- cluster IDs
    are nominal, never treated as equivalent without this explicit mapping."""
    v1_ids = sorted(set(v1_labels))
    v2_ids = sorted(set(v2_labels))
    overlap = np.zeros((len(v2_ids), len(v1_ids)))
    for i, v2c in enumerate(v2_ids):
        for j, v1c in enumerate(v1_ids):
            overlap[i, j] = np.sum((v2_labels == v2c) & (v1_labels == v1c))
    row_ind, col_ind = linear_sum_assignment(-overlap)
    mapping = {int(v2_ids[r]): int(v1_ids[c]) for r, c in zip(row_ind, col_ind)}
    return mapping, overlap


def main() -> None:
    print("=" * 72)
    print(f"Phase 5B-V2 step 4: final typology ({VERSION_TAG}, k={SELECTED_K})")
    print("=" * 72)

    grid_df, X, feature_cols = load_v2ef_matrix()
    labels_df = pd.read_parquet(V2EF_DIR / "_candidate_k_labels_v2ef.parquet")
    labels = labels_df[f"k{SELECTED_K}"].to_numpy()
    grid_df["cluster"] = labels

    assignments = grid_df[["grid_id", "district", "cluster"]].copy()
    assignments.to_parquet(V2EF_DIR / "cluster_assignments_v2ef.parquet")
    print(f"\n[1/9] Saved cluster assignments: {V2EF_DIR / 'cluster_assignments_v2ef.parquet'}")
    sizes = np.bincount(labels)
    print(f"  sizes: {sizes.tolist()} ({(sizes/len(labels)*100).round(2).tolist()}%)")

    # ---- V1 <-> V2 comparison ----
    print("\n[2/9] V1 <-> V2 comparison...")
    v1_assign = pd.read_parquet(V1_TYPOLOGY_DIR / "cluster_assignments_v2.parquet")
    merged = assignments.merge(v1_assign[["grid_id", "cluster"]], on="grid_id", suffixes=("_v2", "_v1"))
    assert len(merged) == 22322

    ari = adjusted_rand_score(merged["cluster_v1"], merged["cluster_v2"])
    nmi = normalized_mutual_info_score(merged["cluster_v1"], merged["cluster_v2"])
    contingency = pd.crosstab(merged["cluster_v1"], merged["cluster_v2"])
    mapping, overlap = best_match_mapping(merged["cluster_v1"].to_numpy(), merged["cluster_v2"].to_numpy())
    merged["v2_mapped_to_v1_id"] = merged["cluster_v2"].map(mapping)
    pct_retained = float((merged["v2_mapped_to_v1_id"] == merged["cluster_v1"]).mean() * 100)

    print(f"  ARI={ari:.4f}  NMI={nmi:.4f}")
    print(f"  best-match mapping (V2 -> V1): {mapping}")
    print(f"  pct cells retaining corresponding regime (via best-match mapping): {pct_retained:.2f}%")
    print(f"  pct changing regime: {100 - pct_retained:.2f}%")

    v1_v2_comparison = {
        "adjusted_rand_index": round(float(ari), 4), "normalized_mutual_info": round(float(nmi), 4),
        "contingency_matrix": contingency.to_dict(),
        "best_match_mapping_v2_to_v1": mapping,
        "pct_cells_retaining_corresponding_regime": round(pct_retained, 2),
        "pct_cells_changing_regime": round(100 - pct_retained, 2),
        "note": "best-match mapping is for interpretive comparison ONLY -- V1 and V2 cluster IDs are nominal "
                "(unordered) and not otherwise equivalent.",
    }

    # ---- Spatial change analysis ----
    print("\n[3/9] Spatial change analysis...")
    merged["changed"] = merged["v2_mapped_to_v1_id"] != merged["cluster_v1"]
    by_district = merged.groupby("district").agg(n_cells=("grid_id", "size"), n_changed=("changed", "sum"))
    by_district["pct_changed"] = (by_district["n_changed"] / by_district["n_cells"] * 100).round(2)
    by_district = by_district.sort_values("pct_changed", ascending=False)

    transition_counts = merged.groupby(["cluster_v1", "cluster_v2"]).size().reset_index(name="n_cells")
    transition_counts = transition_counts.sort_values("n_cells", ascending=False)

    grid_geom = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")[["grid_id", "geometry"]]
    merged_geo = merged.merge(grid_geom, on="grid_id")
    merged_geo = gpd.GeoDataFrame(merged_geo, geometry="geometry", crs=cfg.METRIC_CRS)
    city_centroid = merged_geo.geometry.unary_union.centroid
    merged_geo["dist_to_center_km"] = merged_geo.geometry.centroid.distance(city_centroid) / 1000
    merged_geo["urban_context"] = pd.qcut(merged_geo["dist_to_center_km"], 3, labels=["core", "intermediate", "peripheral"])
    by_context = merged_geo.groupby("urban_context", observed=True).agg(n_cells=("grid_id", "size"), n_changed=("changed", "sum"))
    by_context["pct_changed"] = (by_context["n_changed"] / by_context["n_cells"] * 100).round(2)

    print(f"  citywide pct changed: {merged['changed'].mean()*100:.2f}%")
    print("  by urban context:")
    print(by_context.to_string())
    print("  top 10 districts by pct changed:")
    print(by_district.head(10).to_string())
    print("  top 10 transitions (V1 cluster -> V2 cluster):")
    print(transition_counts.head(10).to_string(index=False))

    # ---- Attribution: do changed cells differ on NEW road/land-use info vs stable cells in the same V1 regime? ----
    print("\n[4/9] Attribution to new road/land-use information...")
    v2_master = pd.read_parquet(FEATURES_DIR / "urban_mobility_features_citywide_v2.parquet",
                                 columns=["grid_id"] + ATTRIBUTION_FEATURES)
    merged_attr = merged.merge(v2_master, on="grid_id")
    attribution = {}
    for v1c in sorted(merged_attr["cluster_v1"].unique()):
        sub = merged_attr[merged_attr["cluster_v1"] == v1c]
        changed = sub[sub["changed"]]
        stable = sub[~sub["changed"]]
        if len(changed) < 20 or len(stable) < 20:
            continue
        feat_diffs = {}
        for feat in ATTRIBUTION_FEATURES:
            med_changed = float(changed[feat].median())
            med_stable = float(stable[feat].median())
            feat_diffs[feat] = {"median_changed_cells": round(med_changed, 4), "median_stable_cells": round(med_stable, 4)}
        attribution[f"v1_cluster_{v1c}"] = {
            "n_changed": int(len(changed)), "n_stable": int(len(stable)), "feature_medians": feat_diffs,
        }
    print(f"  computed for {len(attribution)} V1 regimes with sufficient changed/stable cells")

    # ---- Northern periphery focus ----
    NORTHERN_PERIPHERY_DISTRICTS = ["Çekmeköy", "Eyüpsultan", "Beykoz", "Çatalca", "Başakşehir", "Esenler", "Sarıyer", "Arnavutköy"]
    north_sub = merged[merged["district"].isin(NORTHERN_PERIPHERY_DISTRICTS)]
    north_pct_changed = float(north_sub["changed"].mean() * 100) if len(north_sub) else None
    print(f"  pct changed in northern/periphery focus districts ({NORTHERN_PERIPHERY_DISTRICTS}): {north_pct_changed:.2f}%"
          f" (n={len(north_sub)}) vs citywide {merged['changed'].mean()*100:.2f}%")

    spatial_change = {
        "citywide_pct_changed": round(float(merged["changed"].mean() * 100), 2),
        "by_district_pct_changed": by_district.reset_index().to_dict(orient="records"),
        "by_urban_context_pct_changed": by_context.reset_index().to_dict(orient="records"),
        "top_transitions_v1_to_v2": transition_counts.head(20).to_dict(orient="records"),
        "northern_periphery_focus_districts": NORTHERN_PERIPHERY_DISTRICTS,
        "northern_periphery_pct_changed": round(north_pct_changed, 2) if north_pct_changed is not None else None,
        "attribution_new_info_by_v1_regime": attribution,
    }

    # ---- Controlled ablations (Roads / Land-use) ----
    print("\n[5/9] Controlled ablations (Roads / Land-use / both)...")
    col_idx = {c: i for i, c in enumerate(feature_cols)}
    def drop_cols(cols):
        keep = [i for c, i in col_idx.items() if c not in cols]
        return X[:, keep]

    ablation_labels = {}
    ablation_results = {}
    for name, drop in [
        ("v2_full", []),
        ("v2_minus_roads", ROAD_COLS),
        ("v2_minus_landuse", LANDUSE_COLS),
        ("v2_minus_roads_and_landuse", ROAD_COLS + LANDUSE_COLS),
        ("v2_minus_roads_landuse_and_roadgrade_true_v1_lineage", ROAD_COLS + LANDUSE_COLS + ROAD_GRADE_COLS),
    ]:
        X_ab = drop_cols(drop) if drop else X
        lab = fit_kmeans(X_ab, SELECTED_K) if drop else labels
        ablation_labels[name] = lab
        ari_vs_full = adjusted_rand_score(labels, lab)
        ari_vs_v1 = adjusted_rand_score(merged["cluster_v1"], lab)
        ablation_results[name] = {
            "n_features_dropped": len(drop), "n_features_remaining": X_ab.shape[1],
            "ari_vs_selected_v2": round(float(ari_vs_full), 4),
            "ari_vs_frozen_v1": round(float(ari_vs_v1), 4),
        }
        print(f"  {name}: n_dropped={len(drop)} ARI_vs_V2full={ari_vs_full:.4f} ARI_vs_V1={ari_vs_v1:.4f}")

    # ---- Limitation ablations (repeat V1's most informative robustness checks) ----
    print("\n[6/9] Limitation ablations (population / GTFS transit / İBB cycling / all combined)...")
    limitation_results = {}
    all_limitation_feats = sorted(set(f for g in LIMITATION_GROUPS.values() for f in g))
    for name, feats in {**LIMITATION_GROUPS, "all_limitations_removed": all_limitation_feats}.items():
        missing = [f for f in feats if f not in col_idx]
        assert not missing, f"{name}: features not found in matrix: {missing}"
        X_ab = drop_cols(feats)
        lab = fit_kmeans(X_ab, SELECTED_K)
        ari_limitation = adjusted_rand_score(labels, lab)
        limitation_results[name] = {"n_features_dropped": len(feats), "ari_vs_selected_v2": round(float(ari_limitation), 4)}
        print(f"  {name}: n_dropped={len(feats)} ARI={ari_limitation:.4f}")

    # ---- Algorithm robustness: seed stability + GMM ----
    print("\n[7/9] Algorithm robustness (KMeans seed stability + GMM comparison)...")
    seed_labels = {seed: fit_kmeans(X, SELECTED_K, seed) for seed in STABILITY_SEEDS}
    pairwise_aris = [adjusted_rand_score(seed_labels[a], seed_labels[b])
                      for i, a in enumerate(STABILITY_SEEDS) for b in STABILITY_SEEDS[i + 1:]]
    seed_stability = {"seeds_tested": STABILITY_SEEDS, "pairwise_ari_mean": round(float(np.mean(pairwise_aris)), 4),
                       "pairwise_ari_min": round(float(np.min(pairwise_aris)), 4)}
    print(f"  seed stability: mean ARI={seed_stability['pairwise_ari_mean']}, min={seed_stability['pairwise_ari_min']}")

    gmm = GaussianMixture(n_components=SELECTED_K, random_state=RANDOM_STATE, n_init=5).fit(X)
    gmm_labels = gmm.predict(X)
    ari_km_gmm = adjusted_rand_score(labels, gmm_labels)
    algo_comparison = {
        "kmeans": {"calinski_harabasz": round(float(calinski_harabasz_score(X, labels)), 1), "davies_bouldin": round(float(davies_bouldin_score(X, labels)), 4)},
        "gaussian_mixture": {"calinski_harabasz": round(float(calinski_harabasz_score(X, gmm_labels)), 1), "davies_bouldin": round(float(davies_bouldin_score(X, gmm_labels)), 4), "bic": round(float(gmm.bic(X)), 1)},
        "adjusted_rand_index_kmeans_vs_gmm": round(float(ari_km_gmm), 4),
    }
    print(f"  ARI(KMeans, GMM) = {ari_km_gmm:.4f}")

    # ---- Spatial coherence of the final selected solution ----
    print("\n[8/9] Spatial coherence of selected V2 typology...")
    full_graph = build_queen_graph(grid_df)
    frag = fragmentation_diagnostics(full_graph, labels)
    w = Queen.from_dataframe(grid_df, use_index=False)
    morans = binary_cluster_morans_i(labels, w)
    spatial_coherence = {"fragmentation": frag, "morans_i_per_cluster": {k: v["morans_i"] for k, v in morans.items()}}

    # ---- Save everything ----
    print("\n[9/9] Saving artifacts...")
    (V2EF_DIR / "v1_v2_comparison.json").write_text(json.dumps(v1_v2_comparison, indent=2, default=str), encoding="utf-8")
    (V2EF_DIR / "spatial_change_analysis.json").write_text(json.dumps(spatial_change, indent=2, default=str), encoding="utf-8")
    (V2EF_DIR / "controlled_ablations.json").write_text(json.dumps(ablation_results, indent=2, default=str), encoding="utf-8")
    (V2EF_DIR / "limitation_ablations.json").write_text(json.dumps(limitation_results, indent=2, default=str), encoding="utf-8")
    (V2EF_DIR / "algorithm_robustness.json").write_text(json.dumps({"seed_stability": seed_stability, "kmeans_vs_gmm": algo_comparison}, indent=2, default=str), encoding="utf-8")
    (V2EF_DIR / "spatial_coherence_v2ef.json").write_text(json.dumps(spatial_coherence, indent=2, default=str), encoding="utf-8")

    summary = {
        "version": VERSION_TAG,
        "selected_k": SELECTED_K,
        "cluster_sizes": sizes.tolist(),
        "v1_v2_ari": round(float(ari), 4), "v1_v2_nmi": round(float(nmi), 4),
        "pct_cells_changed": round(float(merged["changed"].mean() * 100), 2),
        "seed_stability_min_ari": seed_stability["pairwise_ari_min"],
        "kmeans_vs_gmm_ari": round(float(ari_km_gmm), 4),
        "controlled_ablations": ablation_results,
        "limitation_ablations": limitation_results,
    }
    (V2EF_DIR / "phase5b_v2_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    for f in ["v1_v2_comparison.json", "spatial_change_analysis.json", "controlled_ablations.json",
              "limitation_ablations.json", "algorithm_robustness.json", "spatial_coherence_v2ef.json",
              "phase5b_v2_summary.json"]:
        print(f"[save] {V2EF_DIR / f}")


if __name__ == "__main__":
    main()
