"""Phase 5B.1: robustness and interpretation audit of the selected k=7
citywide typology. Does NOT change the k=7 solution -- audits it.

1. Re-profiles clusters using raw median/IQR/percentile position (the
   z-score magnitudes reported in Phase 5B, e.g. 67.7 sigma for building
   coverage, are mathematically real but not a defensible substantive
   description under this much skew).
2. Family-specific ablations (population-limitation-only, main_gtfs-
   transit-only, İBB-cycling-only, all-limitations) to find which
   limitation family actually drives the ARI=0.42 sensitivity result from
   Phase 5B.
3. Feature-family dominance: predictor counts per family, within-family
   redundancy remaining after screening, and each family's share of total
   between-cluster sum-of-squares (does transit dominate separation simply
   by contributing more columns?).
4. Quantitative k=6->7 and k=7->8 transition tables, to verify the claimed
   regime-change interpretation rather than asserting it.
5. A revised, raw/percentile-grounded interpretation of the k=7 typology.
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import percentileofscore
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.clustering_phase5b_step1_kdiagnostics import load_matrix
from src.utils import config as cfg

EDA_DIR = cfg.PROJECT_ROOT / "analysis" / "eda"
CLUSTER_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering"
FINAL_K = 7
RANDOM_STATE = 42

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


def load_baseline():
    grid_df, reduced_features, scaled_cols = load_matrix()
    assignments = pd.read_parquet(CLUSTER_DIR / "cluster_assignments.parquet")
    grid_df = grid_df.merge(assignments[["grid_id", "cluster"]], on="grid_id")
    master = gpd.read_parquet(cfg.DATA_PROCESSED / "features" / "urban_mobility_features_citywide.parquet")
    return grid_df, reduced_features, scaled_cols, master


# --------------------------------------------------------------------------
# 1. Raw/percentile re-profiling
# --------------------------------------------------------------------------

def raw_percentile_profile(grid_df: pd.DataFrame, master: pd.DataFrame, reduced_features: list[str]) -> pd.DataFrame:
    df = master[["grid_id"] + reduced_features].merge(grid_df[["grid_id", "cluster"]], on="grid_id")
    rows = []
    for feat in reduced_features:
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


def top_distinguishing_by_percentile(profile_df: pd.DataFrame, n: int = 6) -> dict:
    out = {}
    for cl, g in profile_df.groupby("cluster"):
        g_sorted = g.sort_values("pct_deviation_from_50", ascending=False)
        top = g_sorted.head(n)
        out[int(cl)] = [
            {
                "feature": r["feature"], "raw_median": round(r["raw_median"], 3), "raw_iqr": round(r["raw_iqr"], 3),
                "citywide_percentile": r["citywide_percentile_of_cluster_median"],
                "direction": "above_citywide_median" if r["citywide_percentile_of_cluster_median"] > 50 else "at_or_below_citywide_median",
            }
            for _, r in top.iterrows()
        ]
    return out


# --------------------------------------------------------------------------
# 2. Family-specific ablations
# --------------------------------------------------------------------------

def run_ablation(grid_df: pd.DataFrame, scaled_cols: list[str], drop_features: list[str], baseline_labels: np.ndarray) -> dict:
    drop_scaled = {f"{f}_scaled" for f in drop_features}
    keep_cols = [c for c in scaled_cols if c not in drop_scaled]
    X = grid_df[keep_cols].values
    km = KMeans(n_clusters=FINAL_K, random_state=RANDOM_STATE, n_init=10).fit(X)
    labels = km.labels_
    ari = adjusted_rand_score(baseline_labels, labels)

    baseline_sizes = pd.Series(baseline_labels).value_counts().sort_index()
    new_sizes = pd.Series(labels).value_counts().sort_index()

    ct = pd.crosstab(pd.Series(baseline_labels, name="baseline"), pd.Series(labels, name="ablated"))
    # For each baseline cluster, find how its cells are distributed across ablated clusters
    baseline_dispersion = {}
    for b in ct.index:
        row = ct.loc[b]
        row_pct = (row / row.sum() * 100).round(1)
        top2 = row_pct.sort_values(ascending=False).head(2)
        baseline_dispersion[int(b)] = {"baseline_size": int(row.sum()), "top_destinations_pct": top2.to_dict()}

    return {
        "n_features_dropped": len(drop_features), "features_dropped": drop_features,
        "n_features_remaining": len(keep_cols),
        "adjusted_rand_index_vs_baseline": round(float(ari), 4),
        "baseline_cluster_sizes": baseline_sizes.to_dict(),
        "ablated_cluster_sizes": new_sizes.to_dict(),
        "baseline_cluster_dispersion_into_ablated_clusters": baseline_dispersion,
    }


# --------------------------------------------------------------------------
# 3. Feature-family dominance
# --------------------------------------------------------------------------

def family_dominance(grid_df: pd.DataFrame, scaled_cols: list[str], reduced_features: list[str], feat_dict: pd.DataFrame, corr: pd.DataFrame) -> dict:
    fam_map = dict(zip(feat_dict["feature_name"], feat_dict["feature_family"]))
    families = sorted(set(fam_map.get(f) for f in reduced_features))

    labels = grid_df["cluster"].to_numpy()
    X = grid_df[scaled_cols].to_numpy()
    global_mean = X.mean(axis=0)
    bss_per_feature = np.zeros(X.shape[1])
    for cl in np.unique(labels):
        mask = labels == cl
        n_k = mask.sum()
        cl_mean = X[mask].mean(axis=0)
        bss_per_feature += n_k * (cl_mean - global_mean) ** 2
    total_bss = bss_per_feature.sum()

    result = {}
    for fam in families:
        fam_features = [f for f in reduced_features if fam_map.get(f) == fam]
        fam_scaled_idx = [scaled_cols.index(f"{f}_scaled") for f in fam_features]
        fam_bss = bss_per_feature[fam_scaled_idx].sum()

        # within-family mean absolute Spearman correlation (screened features only)
        if len(fam_features) > 1:
            sub_corr = corr.loc[fam_features, fam_features].to_numpy()
            iu = np.triu_indices_from(sub_corr, k=1)
            mean_abs_corr = float(np.abs(sub_corr[iu]).mean()) if len(iu[0]) else float("nan")
        else:
            mean_abs_corr = float("nan")

        result[fam] = {
            "n_predictors": len(fam_features),
            "predictors": fam_features,
            "mean_within_family_abs_spearman_after_screening": round(mean_abs_corr, 3) if not np.isnan(mean_abs_corr) else None,
            "pct_of_total_between_cluster_sum_of_squares": round(float(fam_bss / total_bss * 100), 2),
        }
    return result


# --------------------------------------------------------------------------
# 4. k transition tables
# --------------------------------------------------------------------------

def transition_table(labels_a: np.ndarray, labels_b: np.ndarray, label_a_name: str, label_b_name: str) -> pd.DataFrame:
    ct = pd.crosstab(pd.Series(labels_a, name=label_a_name), pd.Series(labels_b, name=label_b_name))
    return ct


def main() -> None:
    print("=" * 72)
    print("Phase 5B.1: robustness and interpretation audit of k=7")
    print("=" * 72)

    grid_df, reduced_features, scaled_cols, master = load_baseline()
    feat_dict = pd.read_csv(cfg.DATA_PROCESSED / "metadata" / "feature_dictionary_citywide.csv")
    baseline_labels = grid_df["cluster"].to_numpy()

    print("\n[1/5] Raw/percentile re-profiling...")
    profile_df = raw_percentile_profile(grid_df, master, reduced_features)
    profile_df.to_csv(CLUSTER_DIR / "cluster_profiles_raw_percentile.csv", index=False)
    top_dist = top_distinguishing_by_percentile(profile_df)
    (CLUSTER_DIR / "cluster_top_distinguishing_by_percentile.json").write_text(
        json.dumps(top_dist, indent=2, default=str), encoding="utf-8"
    )
    print(f"  saved cluster_profiles_raw_percentile.csv and cluster_top_distinguishing_by_percentile.json")
    for cl, feats in top_dist.items():
        print(f"  cluster {cl}: " + "; ".join(f"{f['feature']}=median {f['raw_median']} (p{f['citywide_percentile']})" for f in feats[:3]))

    print("\n[2/5] Family-specific ablations...")
    ablation_results = {}
    for name, drop_feats in ABLATION_GROUPS.items():
        print(f"  running ablation: {name} (dropping {len(drop_feats)} features)...")
        ablation_results[name] = run_ablation(grid_df, scaled_cols, drop_feats, baseline_labels)
        print(f"    ARI vs baseline = {ablation_results[name]['adjusted_rand_index_vs_baseline']}")

    all_limitation_feats = sorted(set(f for g in ABLATION_GROUPS.values() for f in g))
    print(f"  running ablation: all_limitations_removed (dropping {len(all_limitation_feats)} features)...")
    ablation_results["all_limitations_removed"] = run_ablation(grid_df, scaled_cols, all_limitation_feats, baseline_labels)
    print(f"    ARI vs baseline = {ablation_results['all_limitations_removed']['adjusted_rand_index_vs_baseline']}")

    (CLUSTER_DIR / "sensitivity_family_ablations.json").write_text(
        json.dumps(ablation_results, indent=2, default=str), encoding="utf-8"
    )
    print(f"  saved sensitivity_family_ablations.json")

    print("\n[3/5] Feature-family dominance...")
    corr = pd.read_csv(EDA_DIR / "feature_correlation_spearman.csv", index_col=0)
    dominance = family_dominance(grid_df, scaled_cols, reduced_features, feat_dict, corr)
    (CLUSTER_DIR / "feature_family_dominance.json").write_text(json.dumps(dominance, indent=2, default=str), encoding="utf-8")
    print("  saved feature_family_dominance.json")
    for fam, d in sorted(dominance.items(), key=lambda kv: -kv[1]["pct_of_total_between_cluster_sum_of_squares"]):
        print(f"    {fam}: n_predictors={d['n_predictors']}, BSS_share={d['pct_of_total_between_cluster_sum_of_squares']}%, "
              f"within_family_corr={d['mean_within_family_abs_spearman_after_screening']}")

    print("\n[4/5] k=6->7 and k=7->8 transition tables...")
    k_labels = pd.read_parquet(CLUSTER_DIR / "_candidate_k_labels.parquet")
    k_labels = k_labels.merge(grid_df[["grid_id"]], on="grid_id")  # align order
    t_6_7 = transition_table(k_labels["k6"].to_numpy(), k_labels["k7"].to_numpy(), "k6_cluster", "k7_cluster")
    t_7_8 = transition_table(k_labels["k7"].to_numpy(), k_labels["k8"].to_numpy(), "k7_cluster", "k8_cluster")
    t_6_7.to_csv(CLUSTER_DIR / "transition_k6_to_k7.csv")
    t_7_8.to_csv(CLUSTER_DIR / "transition_k7_to_k8.csv")
    print(f"  saved transition_k6_to_k7.csv:\n{t_6_7}")
    print(f"\n  saved transition_k7_to_k8.csv:\n{t_7_8}")

    print("\n[5/5] Saving revised interpretation summary...")
    summary = {
        "audit_scope": "Phase 5B.1 -- audits the existing k=7 solution; does NOT change it.",
        "raw_percentile_reprofiling_note": (
            "Phase 5B's z-score magnitudes (e.g. 67.7 sigma building coverage) are mathematically real "
            "consequences of extreme skew in count/density variables, not defensible substantive claims "
            "(a '67.7 standard deviation' building coverage does not mean the cell is 67x more built-up in "
            "any literal sense). Cluster descriptions are now grounded in raw median/IQR and citywide "
            "percentile position of the cluster median; scaled/z-score values are retained only as a "
            "secondary diagnostic (see cluster_profiles_scaled_means.csv from Phase 5B)."
        ),
        "sensitivity_family_ablations": {k: {kk: vv for kk, vv in v.items() if kk != "baseline_cluster_dispersion_into_ablated_clusters"} for k, v in ablation_results.items()},
        "feature_family_dominance": dominance,
        "k_transition_verification": {
            "k6_to_k7_note": "See transition_k6_to_k7.csv for the full cross-tabulation.",
            "k7_to_k8_note": "See transition_k7_to_k8.csv for the full cross-tabulation.",
        },
    }
    (CLUSTER_DIR / "phase5b1_audit_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  saved phase5b1_audit_summary.json")


if __name__ == "__main__":
    main()
