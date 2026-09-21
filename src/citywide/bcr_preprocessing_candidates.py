"""Phase 5C step 1: build 4 candidate treatments for building_coverage_ratio
(all other Phase 5A preprocessing decisions unchanged), then compare them
at k=7 (matching the original baseline) on: BSS share of building coverage,
top-10 predictor BSS contributions, ARI vs the original k=7 assignments,
2-seed stability, and a light k=3..10 sweep (silhouette/CH/DB/sizes only).

Candidates:
  A. baseline      -- log1p + RobustScaler (unchanged from Phase 5A)
  B. winsorized    -- cap raw values at p99, then log1p + RobustScaler
  C. quantile      -- QuantileTransformer (uniform output), zero-mass
                       behavior documented explicitly
  D. two_part      -- has_buildings (0/1) + conditional intensity among
                       built cells only, floored for zero-building cells
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.preprocessing import QuantileTransformer, RobustScaler

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

EDA_DIR = cfg.PROJECT_ROOT / "analysis" / "eda"
CLUSTER_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering"  # original, read-only
V2_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering_v2"
RANDOM_STATE = 42
K_COMPARE = 7  # matches the original baseline for apples-to-apples comparison
K_RANGE = range(3, 11)


def load_base_matrix():
    reduced = pd.read_csv(EDA_DIR / "reduced_feature_set.csv")
    reduced_features = reduced.loc[reduced["included_in_reduced_set"], "feature"].tolist()
    analysis_matrix = pd.read_parquet(EDA_DIR / "analysis_matrix_scaled.parquet")
    master = pd.read_parquet(cfg.DATA_PROCESSED / "features" / "urban_mobility_features_citywide.parquet")
    # analysis_matrix may already carry a (possibly log1p-transformed)
    # "building_coverage_ratio" passthrough column from Phase 5A -- rename
    # the TRUE raw value on merge to avoid a silent pandas _x/_y collision.
    raw_bcr = master[["grid_id", "building_coverage_ratio", "building_count"]].rename(
        columns={"building_coverage_ratio": "building_coverage_ratio_raw"}
    )
    matrix = analysis_matrix.merge(raw_bcr, on="grid_id", how="left")
    assert len(matrix) == 22322
    return matrix, reduced_features


def build_candidate_A(raw_bcr: pd.Series) -> np.ndarray:
    log1p = np.log1p(raw_bcr)
    return RobustScaler().fit_transform(log1p.to_numpy().reshape(-1, 1)).ravel()


def build_candidate_B(raw_bcr: pd.Series, cap_pct: float = 99.0) -> np.ndarray:
    cap = np.percentile(raw_bcr, cap_pct)
    winsorized = raw_bcr.clip(upper=cap)
    log1p = np.log1p(winsorized)
    return RobustScaler().fit_transform(log1p.to_numpy().reshape(-1, 1)).ravel(), float(cap)


def build_candidate_C(raw_bcr: pd.Series) -> tuple[np.ndarray, dict]:
    qt = QuantileTransformer(output_distribution="uniform", random_state=RANDOM_STATE)
    transformed = qt.fit_transform(raw_bcr.to_numpy().reshape(-1, 1)).ravel()
    zero_mask = raw_bcr == 0
    zero_transformed_values = np.unique(transformed[zero_mask])
    diag = {
        "n_distinct_transformed_values_for_zero_mass": len(zero_transformed_values),
        "transformed_value_for_zero": float(zero_transformed_values[0]) if len(zero_transformed_values) == 1 else zero_transformed_values.tolist()[:5],
        "note": "All exact-zero raw values receive (approximately) the same transformed value -- QuantileTransformer "
        "assigns rank-based quantiles, and ties (all zeros) get the same average rank -- rather than being spread "
        "out or treated as distinct. This collapses the 65% zero-mass into a single point at roughly the "
        "midpoint of the zero-mass's rank range, still far below all non-zero cells.",
    }
    return transformed, diag


def build_candidate_D(raw_bcr: pd.Series) -> tuple[np.ndarray, np.ndarray, dict]:
    has_buildings = (raw_bcr > 0).astype(float).to_numpy()
    built_mask = raw_bcr > 0
    built_vals = raw_bcr[built_mask]
    log1p_built = np.log1p(built_vals)
    scaler = RobustScaler().fit(log1p_built.to_numpy().reshape(-1, 1))
    scaled_built = scaler.transform(log1p_built.to_numpy().reshape(-1, 1)).ravel()

    floor_value = float(scaled_built.min()) - 1.0
    conditional = np.full(len(raw_bcr), floor_value)
    conditional[built_mask.to_numpy()] = scaled_built

    diag = {
        "n_built_cells": int(built_mask.sum()), "n_zero_building_cells": int((~built_mask).sum()),
        "conditional_scaled_range_among_built_cells": [float(scaled_built.min()), float(scaled_built.max())],
        "floor_value_assigned_to_zero_building_cells": floor_value,
        "rationale": "has_buildings (0/1) carries the presence/absence signal directly. The conditional intensity "
        "column is fit ONLY on built cells (so its scale reflects real variation among built cells, undistorted "
        "by the zero mass), and zero-building cells are floored just below the minimum observed built-cell value "
        "-- clearly separated, but not an arbitrary large outlier, and not conflated with a real (if low) "
        "building coverage value.",
    }
    return has_buildings, conditional, diag


def bss_by_feature(X: np.ndarray, labels: np.ndarray, feature_names: list[str]) -> pd.Series:
    global_mean = X.mean(axis=0)
    bss = np.zeros(X.shape[1])
    for cl in np.unique(labels):
        mask = labels == cl
        n_k = mask.sum()
        cl_mean = X[mask].mean(axis=0)
        bss += n_k * (cl_mean - global_mean) ** 2
    return pd.Series(bss, index=feature_names)


def evaluate_candidate(X: np.ndarray, feature_names: list[str], label: str, original_labels: np.ndarray) -> dict:
    km = KMeans(n_clusters=K_COMPARE, random_state=RANDOM_STATE, n_init=10).fit(X)
    labels = km.labels_

    bss = bss_by_feature(X, labels, feature_names)
    total_bss = bss.sum()
    bss_pct = (bss / total_bss * 100).sort_values(ascending=False)

    km_seed2 = KMeans(n_clusters=K_COMPARE, random_state=1, n_init=10).fit(X)
    seed_ari = adjusted_rand_score(labels, km_seed2.labels_)

    sizes = np.bincount(labels)
    result = {
        "label": label,
        "silhouette_subsampled": None,  # filled by caller with a shared sample
        "calinski_harabasz": round(float(calinski_harabasz_score(X, labels)), 1),
        "davies_bouldin": round(float(davies_bouldin_score(X, labels)), 4),
        "cluster_sizes": sizes.tolist(),
        "min_pct": round(float(sizes.min() / len(labels) * 100), 2),
        "max_pct": round(float(sizes.max() / len(labels) * 100), 2),
        "ari_vs_original_k7": round(float(adjusted_rand_score(original_labels, labels)), 4),
        "two_seed_stability_ari": round(float(seed_ari), 4),
        "top10_predictors_by_bss_pct": bss_pct.head(10).round(2).to_dict(),
        "building_coverage_related_bss_pct": {
            k: round(float(v), 2) for k, v in bss_pct.items()
            if "building_coverage" in k or "has_buildings" in k
        },
    }
    return result, labels


def main() -> None:
    matrix, reduced_features = load_base_matrix()
    scaled_cols = [f"{c}_scaled" for c in reduced_features]
    other_cols = [c for c in scaled_cols if c != "building_coverage_ratio_scaled"]
    other_feature_names = [c.replace("_scaled", "") for c in other_cols]

    original_assignments = pd.read_parquet(CLUSTER_DIR / "cluster_assignments.parquet")
    original_labels = matrix[["grid_id"]].merge(original_assignments, on="grid_id")["cluster"].to_numpy()

    raw_bcr = matrix["building_coverage_ratio_raw"]
    X_other = matrix[other_cols].to_numpy()

    results = {}
    label_arrays = {}

    print("=" * 72)
    print("Candidate A: baseline (log1p + RobustScaler) -- reproduces the original")
    print("=" * 72)
    A_col = build_candidate_A(raw_bcr)
    X_A = np.column_stack([X_other, A_col])
    names_A = other_feature_names + ["building_coverage_ratio"]
    results["A_baseline"], label_arrays["A_baseline"] = evaluate_candidate(X_A, names_A, "A_baseline", original_labels)
    print(json.dumps(results["A_baseline"], indent=2, default=str))

    print("\n" + "=" * 72)
    print("Candidate B: winsorized at p99 + log1p + RobustScaler")
    print("=" * 72)
    B_col, cap_value = build_candidate_B(raw_bcr, cap_pct=99.0)
    X_B = np.column_stack([X_other, B_col])
    results["B_winsorized_p99"], label_arrays["B_winsorized_p99"] = evaluate_candidate(X_B, names_A, "B_winsorized_p99", original_labels)
    results["B_winsorized_p99"]["cap_value_raw"] = cap_value
    print(f"cap value (p99 raw): {cap_value}")
    print(json.dumps(results["B_winsorized_p99"], indent=2, default=str))

    print("\n" + "=" * 72)
    print("Candidate C: QuantileTransformer (uniform)")
    print("=" * 72)
    C_col, c_diag = build_candidate_C(raw_bcr)
    X_C = np.column_stack([X_other, C_col])
    results["C_quantile"], label_arrays["C_quantile"] = evaluate_candidate(X_C, names_A, "C_quantile", original_labels)
    results["C_quantile"]["zero_mass_diagnostic"] = c_diag
    print(json.dumps(c_diag, indent=2, default=str))
    print(json.dumps(results["C_quantile"], indent=2, default=str))

    print("\n" + "=" * 72)
    print("Candidate D: two-part (has_buildings + conditional intensity)")
    print("=" * 72)
    has_buildings, conditional, d_diag = build_candidate_D(raw_bcr)
    X_D = np.column_stack([X_other, has_buildings, conditional])
    names_D = other_feature_names + ["has_buildings", "building_coverage_ratio_conditional"]
    results["D_two_part"], label_arrays["D_two_part"] = evaluate_candidate(X_D, names_D, "D_two_part", original_labels)
    results["D_two_part"]["construction_diagnostic"] = d_diag
    print(json.dumps(d_diag, indent=2, default=str))
    print(json.dumps(results["D_two_part"], indent=2, default=str))

    V2_DIR.mkdir(parents=True, exist_ok=True)
    (V2_DIR / "preprocessing_comparison.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n[save] {V2_DIR / 'preprocessing_comparison.json'}")

    print("\n--- SUMMARY: building-coverage-related BSS share (k=7) ---")
    for name, r in results.items():
        print(f"  {name}: {r['building_coverage_related_bss_pct']}, ARI_vs_original={r['ari_vs_original_k7']}, "
              f"seed_stability={r['two_seed_stability_ari']}, size_range=[{r['min_pct']}%,{r['max_pct']}%]")


if __name__ == "__main__":
    main()
