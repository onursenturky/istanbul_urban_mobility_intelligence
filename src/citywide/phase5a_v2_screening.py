"""Phase 5A-V2: feature screening and transformation design for the
CITYWIDE_V2_EIGHT_FAMILY_FEATURE_BASELINE.

Does NOT modify V1 or the frozen V2 baseline artifacts -- reads them only.
Produces a reduced/scaled predictor matrix for later V2 typology work, and
explicitly guards against the Phase 5C family-dominance failure mode
(building_coverage_ratio alone drove ~97% of BSS under plain log1p+
RobustScaler; the two-part has_buildings + conditional treatment cut that
to ~7%).

METHODOLOGY SUMMARY
--------------------
1. Starting pool: 94 V2 predictors minus the 5 EXCLUDE_FROM_MODEL columns = 89 eligible.
2. The 43 non-building features already retained in V1's frozen Phase 5C/Candidate-D
   matrix (analysis/eda/analysis_matrix_scaled.parquet + build_candidate_D) are
   reused UNCHANGED -- their raw values are byte-identical between V1 and V2
   (verified in Phase 7B), so their already-decided log1p/RobustScaler
   transforms carry over with no re-derivation needed. building_coverage_ratio
   is replaced by the SAME two-part treatment (has_buildings +
   building_coverage_ratio_conditional) already frozen in V1's typology.
3. 11 NEW predictors are added after explicit redundancy/coverage resolution
   (see ROAD_DECISIONS / LANDUSE_DECISIONS below and the printed audit).
4. V2's reduced matrix = V1's 45-feature Candidate-D matrix (unchanged) + 11
   new features = 56 total -- a strict superset, so any V1-vs-V2 typology
   difference can be attributed to genuinely new information, not
   accidental preprocessing drift.

Outputs (all under data/processed/citywide/):
  features/phase5a_v2_reduced_matrix_raw.parquet         -- human-readable raw values
  features/phase5a_v2_reduced_matrix_scaled.parquet       -- clustering-ready matrix
  metadata/phase5a_v2_transformation_audit.csv            -- per-eligible-predictor audit
  metadata/phase5a_v2_redundancy_decisions.json           -- documented decisions
  qa/phase5a_v2_family_bss_diagnostic.json                -- k=5 diagnostic BSS audit
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from sklearn.cluster import KMeans
from sklearn.preprocessing import RobustScaler

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.bcr_preprocessing_candidates import build_candidate_D
from src.utils import config as cfg

FEATURES_DIR = cfg.DATA_FEATURES
META_DIR = cfg.DATA_PROCESSED / "metadata"
QA_DIR = cfg.DATA_PROCESSED / "qa"
EDA_DIR = cfg.PROJECT_ROOT / "analysis" / "eda"

V2_MASTER_PATH = FEATURES_DIR / "urban_mobility_features_citywide_v2.parquet"
V2_DICT_PATH = META_DIR / "feature_dictionary_citywide_v2.csv"
V1_REDUCED_SET_PATH = EDA_DIR / "reduced_feature_set.csv"
V1_SCALED_MATRIX_PATH = EDA_DIR / "analysis_matrix_scaled.parquet"

DIAGNOSTIC_K = 5
RANDOM_STATE = 42

# --------------------------------------------------------------------------
# Family assignment for BSS reporting (matches V1 feature_dictionary family
# labels for carried-over features; new predictors assigned by concept).
# --------------------------------------------------------------------------
FAMILY_OF = {
    "has_buildings": "Buildings/Urban Form", "building_coverage_ratio_conditional": "Buildings/Urban Form",
    "major_road_length_m": "Roads", "local_road_length_m": "Roads", "road_density_km_per_km2": "Roads",
    "intersection_density_km2": "Roads", "cycle_accessible_road_density_km_per_km2": "Roads",
    "mean_absolute_road_grade_pct": "Terrain", "pct_road_length_grade_gt_8pct": "Terrain",
    "green_area_ratio": "Land-use/Green Space", "landuse_has_mapped_evidence": "Land-use/Green Space",
    "residential_share_conditional": "Land-use/Green Space", "industrial_share_conditional": "Land-use/Green Space",
}


def load_inputs():
    v2 = gpd.read_parquet(V2_MASTER_PATH)
    v2_dict = pd.read_csv(V2_DICT_PATH)
    v1_reduced = pd.read_csv(V1_REDUCED_SET_PATH)
    v1_scaled = pd.read_parquet(V1_SCALED_MATRIX_PATH)
    return v2, v2_dict, v1_reduced, v1_scaled


def eligible_pool(v2: pd.DataFrame, v2_dict: pd.DataFrame) -> tuple[list[str], list[str]]:
    id_geom_cols = {"grid_id", "district", "cell_area_m2", "land_area_m2", "geometry"}
    all_predictors = [c for c in v2.columns if c not in id_geom_cols]
    exclude = v2_dict.loc[v2_dict["classification"] == "EXCLUDE_FROM_MODEL", "feature_name"].tolist()
    eligible = [c for c in all_predictors if c not in exclude]
    return eligible, exclude


def skew(s: pd.Series) -> float:
    return float(scipy_stats.skew(s.to_numpy())) if s.nunique() > 1 else 0.0


def audit_row(name: str, s: pd.Series) -> dict:
    valid = s.dropna()
    n = len(valid)
    pct_zero = float((valid == 0).mean() * 100) if n else None
    p50 = float(valid.median()) if n else None
    p99 = float(valid.quantile(0.99)) if n else None
    q1, q3 = (float(valid.quantile(0.25)), float(valid.quantile(0.75))) if n else (None, None)
    nonzero = valid[valid != 0]
    nonzero_iqr = float(nonzero.quantile(0.75) - nonzero.quantile(0.25)) if len(nonzero) > 1 else None
    iqr = q3 - q1 if n else None
    if iqr:
        max_rs = float(((valid - p50) / iqr).abs().max())
    else:
        max_rs = None
    return {
        "feature": name, "n_valid": n, "pct_missing": round((1 - n / len(s)) * 100, 3) if len(s) else None,
        "pct_zero": round(pct_zero, 2) if pct_zero is not None else None,
        "skewness": round(skew(valid), 3) if n else None,
        "nonzero_iqr": round(nonzero_iqr, 6) if nonzero_iqr is not None else None,
        "p99_over_p50": round(p99 / p50, 3) if p50 not in (None, 0) else None,
        "max_robustscaler_magnitude": round(max_rs, 2) if max_rs is not None else None,
    }


def log1p_if_improves(s: pd.Series) -> tuple[pd.Series, bool]:
    raw_skew = skew(s)
    logged = np.log1p(s.clip(lower=0))
    logged_skew = skew(logged)
    if abs(logged_skew) < abs(raw_skew):
        return logged, True
    return s, False


def robust_scale(s: pd.Series) -> np.ndarray:
    return RobustScaler().fit_transform(s.to_numpy().reshape(-1, 1)).ravel()


def three_state_conditional(raw: pd.Series, evidence_mask: pd.Series) -> tuple[np.ndarray, dict]:
    """Three-state land-use coverage treatment, matching the exact three
    states the user specified: (1) no mapped land-use evidence at all,
    (2) mapped, zero category share, (3) mapped, nonzero category share.

    A first attempt fit log1p+RobustScaler on the whole 'evidence' subset
    (states 2+3 combined) and floored state 1 below it -- this reproduced
    the Phase 5C failure mode one level deeper: within 'evidence', the
    category share is ITSELF heavily zero-inflated (e.g. only 28% of
    evidence cells have nonzero industrial share), so the evidence-subset
    median/IQR collapsed toward zero and blew up the few real nonzero
    values into a single dominant axis (94% of diagnostic BSS). Fixed by
    nesting Candidate D's own zero/nonzero split INSIDE the evidence
    subset: log1p+RobustScaler is fit ONLY on evidence-AND-nonzero cells
    (state 3), with state 2 (evidence, zero) and state 1 (no evidence)
    each floored at their own distinct, ordered level below it -- state 2
    just below the real intensity values, state 1 further below that --
    so all three states remain distinguishable without any of them
    distorting the fitted scale of genuine nonzero variation.
    """
    evidence_nonzero_mask = evidence_mask & (raw > 0)
    evidence_zero_mask = evidence_mask & (raw == 0)
    no_evidence_mask = ~evidence_mask

    nz_vals = raw[evidence_nonzero_mask]
    logged, used_log = log1p_if_improves(nz_vals)
    scaled_nz = robust_scale(logged)

    floor_state2 = float(scaled_nz.min()) - 1.0   # mapped, zero share
    floor_state1 = floor_state2 - 1.0             # no mapped evidence at all

    out = np.full(len(raw), floor_state1)
    out[evidence_zero_mask.to_numpy()] = floor_state2
    out[evidence_nonzero_mask.to_numpy()] = scaled_nz

    diag = {
        "n_state1_no_evidence": int(no_evidence_mask.sum()),
        "n_state2_evidence_zero_share": int(evidence_zero_mask.sum()),
        "n_state3_evidence_nonzero_share": int(evidence_nonzero_mask.sum()),
        "log1p_applied_to_state3": used_log,
        "floor_state1_no_evidence": floor_state1, "floor_state2_evidence_zero": floor_state2,
        "scaled_range_state3": [float(scaled_nz.min()), float(scaled_nz.max())],
    }
    return out, diag


def main() -> None:
    print("=" * 72)
    print("Phase 5A-V2: feature screening and transformation design")
    print("=" * 72)

    v2, v2_dict, v1_reduced, v1_scaled = load_inputs()
    assert len(v2) == 22322

    # ---- 1. Starting eligible pool ----
    eligible, excluded = eligible_pool(v2, v2_dict)
    print(f"\n[1] Starting eligible predictors: {len(eligible)} (94 total - {len(excluded)} EXCLUDE_FROM_MODEL: {excluded})")

    # ---- 2. Carry over V1's frozen Candidate-D matrix unchanged ----
    v1_included = v1_reduced.loc[v1_reduced["included_in_reduced_set"], "feature"].tolist()
    v1_non_building = [c for c in v1_included if c != "building_coverage_ratio"]
    carried_scaled = v1_scaled.merge(v2[["grid_id"]], on="grid_id", how="right")
    carried_cols = {c: carried_scaled[f"{c}_scaled"].to_numpy() for c in v1_non_building}
    print(f"\n[2] Carried over UNCHANGED from V1's frozen Candidate-D matrix: {len(v1_non_building)} features")

    has_buildings, conditional, bcr_diag = build_candidate_D(v2["building_coverage_ratio"])
    print(f"    + building two-part (has_buildings, building_coverage_ratio_conditional): {bcr_diag['rationale'][:80]}...")

    # ---- 3. Road redundancy resolution ----
    print("\n[3] Road redundancy resolution:")
    road_decisions = {
        "road_length_m": "DROP -- rho=0.989 vs road_density_km_per_km2 (denominator-derived); density preferred (area-normalized, comparable across cells).",
        "walkable_road_length_m": "DROP -- rho=1.000 vs cycle_accessible_road_length_m citywide (differ only by the rare 'steps' class); carries no independent ranking information.",
        "intersection_count": "DROP -- rho=0.998 vs intersection_density_km2 (denominator-derived); density preferred.",
        "cycle_accessible_road_length_m": "RE-ENGINEERED to cycle_accessible_road_density_km_per_km2 (same km/km^2 convention as road_density_km_per_km2) -- raw form was rho=0.968 vs road_density_km_per_km2 (near-redundant, both track total network extent); retained in density form specifically for its Cycling Readiness relevance (which classes are legally cycle-accessible), not as a second general road-extent measure.",
        "major_road_length_m": "KEEP as-is (log1p) -- no density counterpart exists for this subclass; distinct functional-class concept.",
        "local_road_length_m": "KEEP as-is (log1p) -- no density counterpart; distinct functional-class concept.",
        "road_density_km_per_km2": "KEEP as PRIMARY overall road-network extent measure.",
        "intersection_density_km2": "KEEP as PRIMARY connectivity measure.",
    }
    for k, v in road_decisions.items():
        print(f"    {k}: {v}")

    v2["cycle_accessible_road_density_km_per_km2"] = v2["cycle_accessible_road_length_m"] / 1000 / (v2["land_area_m2"] / 1e6)

    road_features_raw = {
        "major_road_length_m": v2["major_road_length_m"],
        "local_road_length_m": v2["local_road_length_m"],
        "road_density_km_per_km2": v2["road_density_km_per_km2"],
        "intersection_density_km2": v2["intersection_density_km2"],
        "cycle_accessible_road_density_km_per_km2": v2["cycle_accessible_road_density_km_per_km2"],
    }

    # ---- Road grade (grade internal redundancy: mean vs median rho=0.890, mean vs gt5 rho=0.803, gt5 vs gt8 rho=0.704) ----
    print("\n    Road-grade internal: KEEP mean_absolute_road_grade_pct + pct_road_length_grade_gt_8pct "
          "(parallel to V1's slope treatment: central-tendency + one extreme-threshold-share bin); "
          "DROP median_absolute_road_grade_pct (rho=0.890 vs mean, near-duplicate central-tendency) and "
          "pct_road_length_grade_gt_5pct (rho=0.803 vs mean, 0.704 vs gt_8pct -- overlapping threshold-share concept).")
    grade_features_raw = {
        "mean_absolute_road_grade_pct": v2["mean_absolute_road_grade_pct"],
        "pct_road_length_grade_gt_8pct": v2["pct_road_length_grade_gt_8pct"],
    }

    # ---- 4. Cycling-overlap redundancy ----
    print("\n[4] Cycling-overlap: PRIMARY representation remains cycle_infrastructure_density_km_per_km2_ibb_only "
          "(already in V1's frozen matrix, well-behaved, no missing-data complexity). pct_road_network_with_"
          "cycle_infrastructure (rho=0.989 vs the primary) is NOT added to the clustering matrix -- kept as a "
          "separate sensitivity/alternative-representation column only (95.3% zero, NaN for roadless cells, and "
          "near-duplicate signal to the already-retained feature).")

    # ---- 5/6. Land-use ----
    print("\n[5/6] Land-use: green_area_ratio kept as a simple continuous feature (rho=-0.28 vs "
          "landuse_data_coverage_pct -- NOT confounded with tagging coverage the way residential is; 25.6% zero, "
          "skew 0.14, no scaling-risk flags). green_area_m2 DROPPED (rho=0.99 vs green_area_ratio, "
          "denominator-derived; ratio preferred for cross-cell comparability).")
    green_logged, green_log_used = log1p_if_improves(v2["green_area_ratio"])
    green_scaled = robust_scale(green_logged)

    print("    residential_area_ratio & industrial_area_ratio: coverage-aware two-part treatment -- ONE shared "
          "landuse_has_mapped_evidence indicator (landuse_data_coverage_pct > 0) distinguishes 'no mapped "
          "land-use evidence' from 'mapped' cells; a category-specific conditional share is fit (log1p+"
          "RobustScaler) ONLY on mapped cells, so a mapped-zero share and a mapped-nonzero share both appear in "
          "their true, undistorted position -- 'no evidence' cells are floored separately, never silently "
          "treated as a real zero share.")
    print("    commercial_area_ratio (96.25% zero) and retail_area_ratio (99.59% zero) EXCLUDED from the primary "
          "clustering matrix -- too degenerate even under a two-part treatment (residential/industrial's own "
          "'mapped, nonzero' subsets are 4,668 and 1,547 cells respectively; commercial/retail's would be far "
          "smaller and dominated by the coverage confound). Both preserved for descriptive-only interpretation.")

    evidence_mask = v2["landuse_data_coverage_pct"] > 0
    landuse_has_mapped_evidence = evidence_mask.astype(float).to_numpy()
    residential_conditional, res_diag = three_state_conditional(v2["residential_area_ratio"], evidence_mask)
    industrial_conditional, ind_diag = three_state_conditional(v2["industrial_area_ratio"], evidence_mask)
    print(f"    residential three-state counts: {res_diag['n_state1_no_evidence']} no-evidence / "
          f"{res_diag['n_state2_evidence_zero_share']} mapped-zero / {res_diag['n_state3_evidence_nonzero_share']} mapped-nonzero")
    print(f"    industrial three-state counts: {ind_diag['n_state1_no_evidence']} no-evidence / "
          f"{ind_diag['n_state2_evidence_zero_share']} mapped-zero / {ind_diag['n_state3_evidence_nonzero_share']} mapped-nonzero")

    # ---- Assemble RAW (human-readable) selected-predictor table ----
    raw_matrix = v2[["grid_id", "district"]].copy()
    for c in v1_non_building:
        raw_matrix[c] = v2[c] if c in v2.columns else np.nan
    raw_matrix["building_coverage_ratio"] = v2["building_coverage_ratio"]
    for c, s in road_features_raw.items():
        raw_matrix[c] = s
    for c, s in grade_features_raw.items():
        raw_matrix[c] = s
    raw_matrix["green_area_ratio"] = v2["green_area_ratio"]
    raw_matrix["landuse_has_mapped_evidence"] = landuse_has_mapped_evidence
    raw_matrix["residential_area_ratio"] = v2["residential_area_ratio"]
    raw_matrix["industrial_area_ratio"] = v2["industrial_area_ratio"]
    raw_matrix["landuse_data_coverage_pct"] = v2["landuse_data_coverage_pct"]
    # descriptive-only (not in scaled clustering matrix)
    descriptive_only = v2[["grid_id", "road_length_m", "walkable_road_length_m", "intersection_count",
                            "cycle_accessible_road_length_m", "median_absolute_road_grade_pct",
                            "pct_road_length_grade_gt_5pct", "green_area_m2", "commercial_area_ratio",
                            "retail_area_ratio", "pct_road_network_with_cycle_infrastructure"]].copy()

    # ---- 7. Transformation audit over the full 89-feature eligible pool ----
    print("\n[7] Transformation audit over all 89 eligible predictors...")
    audit_rows = []
    retained_final = list(carried_cols.keys()) + ["has_buildings", "building_coverage_ratio_conditional"] + \
        list(road_features_raw.keys()) + list(grade_features_raw.keys()) + \
        ["green_area_ratio", "landuse_has_mapped_evidence", "residential_share_conditional", "industrial_share_conditional"]
    dropped_redundant = {"road_length_m", "walkable_road_length_m", "intersection_count",
                          "cycle_accessible_road_length_m", "median_absolute_road_grade_pct",
                          "pct_road_length_grade_gt_5pct", "green_area_m2", "population_worldpop_raw",
                          "population_density_worldpop_raw_km2", "population_calibrated"}
    excluded_degenerate = {"commercial_area_ratio", "retail_area_ratio"}
    excluded_alt_representation = {"pct_road_network_with_cycle_infrastructure"}
    for feat in eligible:
        if feat not in v2.columns:
            continue
        row = audit_row(feat, v2[feat])
        if feat in ("major_road_length_m", "local_road_length_m", "mean_absolute_road_grade_pct",
                     "pct_road_length_grade_gt_8pct", "green_area_ratio"):
            decision = "RETAIN: log1p-if-improves-skew + RobustScaler"
        elif feat in ("road_density_km_per_km2", "intersection_density_km2"):
            decision = "RETAIN as PRIMARY normalized representation: log1p-if-improves-skew + RobustScaler"
        elif feat in ("residential_area_ratio", "industrial_area_ratio"):
            decision = "RETAIN via coverage-aware two-part (mapped-evidence + conditional share)"
        elif feat == "building_coverage_ratio":
            decision = "RETAIN via frozen V1 two-part (has_buildings + conditional intensity)"
        elif feat == "landuse_data_coverage_pct":
            decision = "USED ONLY to derive landuse_has_mapped_evidence; not itself a matrix column"
        elif feat in dropped_redundant:
            decision = "EXCLUDE: redundant (denominator-derived or near-exact duplicate) -- kept descriptive-only where applicable"
        elif feat in excluded_degenerate:
            decision = "EXCLUDE: degenerate zero-inflation even under two-part treatment -- descriptive-only"
        elif feat in excluded_alt_representation:
            decision = "EXCLUDE from primary matrix: near-duplicate of an already-retained representation -- kept as sensitivity-only"
        elif feat in v1_non_building:
            decision = "RETAIN: unchanged from V1's frozen Candidate-D matrix"
        else:
            decision = "RETAIN: unchanged from V1 (READY_WITH_LIMITATION honored)"
        row["decision"] = decision
        audit_rows.append(row)
    audit_df = pd.DataFrame(audit_rows)

    # ---- Assemble SCALED clustering matrix ----
    scaled = {c: carried_cols[c] for c in v1_non_building}
    scaled["has_buildings"] = has_buildings
    scaled["building_coverage_ratio_conditional"] = conditional
    for name, s in road_features_raw.items():
        logged, used = log1p_if_improves(s)
        scaled[name] = robust_scale(logged)
    for name, s in grade_features_raw.items():
        valid_mask = s.notna()
        logged, used = log1p_if_improves(s[valid_mask])
        sc = robust_scale(logged)
        floor_v = float(sc.min()) - 1.0
        full = np.full(len(s), floor_v)
        full[valid_mask.to_numpy()] = sc
        scaled[name] = full
    scaled["green_area_ratio"] = green_scaled
    scaled["landuse_has_mapped_evidence"] = landuse_has_mapped_evidence
    scaled["residential_share_conditional"] = residential_conditional
    scaled["industrial_share_conditional"] = industrial_conditional

    feature_names = list(scaled.keys())
    X = np.column_stack([scaled[f] for f in feature_names])
    assert not np.isnan(X).any(), "NaN survived into the final clustering matrix"
    print(f"\n    Final reduced/scaled matrix: {X.shape[0]} cells x {X.shape[1]} features "
          f"({len(v1_non_building)} carried + 2 building + {len(road_features_raw)} road + "
          f"{len(grade_features_raw)} grade + 4 landuse)")

    scaled_matrix_df = pd.DataFrame(X, columns=feature_names)
    scaled_matrix_df.insert(0, "grid_id", v2["grid_id"].to_numpy())

    # ---- 9. Diagnostic KMeans k=5 BSS audit ----
    print(f"\n[9] Diagnostic KMeans (k={DIAGNOSTIC_K}, for BSS-by-family measurement ONLY -- not a final clustering)...")
    km = KMeans(n_clusters=DIAGNOSTIC_K, random_state=RANDOM_STATE, n_init=10).fit(X)
    labels = km.labels_
    global_mean = X.mean(axis=0)
    bss = np.zeros(X.shape[1])
    for cl in np.unique(labels):
        mask = labels == cl
        cl_mean = X[mask].mean(axis=0)
        bss += mask.sum() * (cl_mean - global_mean) ** 2
    bss_series = pd.Series(bss, index=feature_names)
    total_bss = bss_series.sum()
    bss_pct = (bss_series / total_bss * 100)

    default_family = {**{c: None for c in v1_non_building}, **FAMILY_OF}
    v1_family_map = v1_reduced.set_index("feature")["family"].to_dict()
    family_lookup = {
        "hospital_count": "POI", "university_count": "POI", "school_count": "POI", "healthcare_count": "POI",
        "cafe_count": "POI", "restaurant_count": "POI", "bar_pub_count": "POI", "supermarket_count": "POI",
        "retail_count": "POI", "office_count": "POI", "tourism_count": "POI", "leisure_count": "POI",
        "poi_density_km2": "POI", "poi_entropy": "POI",
        "population_density_calibrated_km2": "Population",
        "mean_elevation_m": "Terrain", "mean_slope_deg": "Terrain", "pct_area_slope_3_6deg": "Terrain",
        "pct_area_slope_6_10deg": "Terrain",
        "cycle_infrastructure_density_km_per_km2_ibb_only": "Cycling",
        "protected_cycleway_density_km_per_km2_ibb_only": "Cycling",
        "distance_to_nearest_cycle_infrastructure_m_ibb_only": "Cycling",
        "distance_to_nearest_bicycle_parking_m": "Cycling", "bicycle_parking_count": "Cycling",
        "distance_to_nearest_micromobility_parking_m": "Cycling", "micromobility_parking_count": "Cycling",
    }
    for c in v1_non_building:
        if c not in family_lookup:
            family_lookup[c] = "Transit"  # remaining carried features are all transit distance/count metrics
    family_lookup.update(FAMILY_OF)

    family_bss = bss_pct.groupby(lambda f: family_lookup.get(f, "UNASSIGNED")).sum().sort_values(ascending=False)
    family_counts = pd.Series(feature_names).map(lambda f: family_lookup.get(f, "UNASSIGNED")).value_counts()
    family_bss_per_predictor = (family_bss / family_counts.reindex(family_bss.index)).round(3)

    top15 = bss_pct.sort_values(ascending=False).head(15)

    print("\n    Family BSS contribution (%):")
    for fam, pct in family_bss.items():
        print(f"      {fam}: {pct:.2f}%  (n_predictors={family_counts.get(fam, 0)}, per-predictor={family_bss_per_predictor.get(fam, float('nan')):.3f}%)")
    print("\n    Top 15 individual predictors by BSS%:")
    for feat, pct in top15.items():
        print(f"      {feat}: {pct:.2f}%")

    dominance_flag = "NONE" if top15.iloc[0] < 20 else f"REVIEW: {top15.index[0]} accounts for {top15.iloc[0]:.1f}% of BSS"

    # ---- Save everything ----
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    raw_out = raw_matrix.merge(descriptive_only, on="grid_id")
    raw_out.to_parquet(FEATURES_DIR / "phase5a_v2_reduced_matrix_raw.parquet")
    scaled_matrix_df.to_parquet(FEATURES_DIR / "phase5a_v2_reduced_matrix_scaled.parquet")
    audit_df.to_csv(META_DIR / "phase5a_v2_transformation_audit.csv", index=False)

    redundancy_decisions = {
        "road": road_decisions,
        "road_grade": "KEEP mean_absolute_road_grade_pct + pct_road_length_grade_gt_8pct; DROP median + gt_5pct (see printed rationale).",
        "cycling_overlap": "PRIMARY = cycle_infrastructure_density_km_per_km2_ibb_only (unchanged from V1); pct_road_network_with_cycle_infrastructure held out as sensitivity-only.",
        "landuse": {
            "green_area_ratio": "KEEP (simple, well-behaved; NOT coverage-confounded, rho=-0.28 vs landuse_data_coverage_pct).",
            "green_area_m2": "DROP (rho=0.99 vs green_area_ratio, denominator-derived).",
            "residential_area_ratio": "RETAIN via coverage-aware THREE-STATE treatment (no-evidence / mapped-zero / mapped-nonzero; rho=0.909 vs landuse_data_coverage_pct -- severe confound resolved by conditioning on mapped evidence AND nesting the zero/nonzero split inside it, which an earlier two-state attempt omitted, reproducing the Phase 5C dominance failure at 94% BSS before this fix).",
            "industrial_area_ratio": "RETAIN via coverage-aware THREE-STATE treatment (same as residential; rho=0.480 vs coverage -- weaker confound, same principled treatment applied for consistency).",
            "commercial_area_ratio": "EXCLUDE from primary matrix (96.25% zero) -- descriptive-only.",
            "retail_area_ratio": "EXCLUDE from primary matrix (99.59% zero, per instruction) -- descriptive-only.",
        },
        "building": "Reused frozen V1 Candidate D two-part treatment verbatim (has_buildings + building_coverage_ratio_conditional).",
    }
    (META_DIR / "phase5a_v2_redundancy_decisions.json").write_text(
        json.dumps(redundancy_decisions, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    bss_report = {
        "diagnostic_k": DIAGNOSTIC_K,
        "n_features_in_matrix": len(feature_names),
        "family_bss_pct": family_bss.round(3).to_dict(),
        "family_n_predictors": family_counts.to_dict(),
        "family_bss_per_predictor_pct": family_bss_per_predictor.to_dict(),
        "top15_individual_bss_pct": top15.round(3).to_dict(),
        "dominance_flag": dominance_flag,
        "cluster_sizes": np.bincount(labels).tolist(),
    }
    (QA_DIR / "phase5a_v2_family_bss_diagnostic.json").write_text(
        json.dumps(bss_report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"\n[save] {FEATURES_DIR / 'phase5a_v2_reduced_matrix_raw.parquet'}")
    print(f"[save] {FEATURES_DIR / 'phase5a_v2_reduced_matrix_scaled.parquet'}")
    print(f"[save] {META_DIR / 'phase5a_v2_transformation_audit.csv'}")
    print(f"[save] {META_DIR / 'phase5a_v2_redundancy_decisions.json'}")
    print(f"[save] {QA_DIR / 'phase5a_v2_family_bss_diagnostic.json'}")

    print("\n--- SUMMARY ---")
    print(f"Eligible: {len(eligible)}  Final reduced matrix: {len(feature_names)}  Dominance flag: {dominance_flag}")


if __name__ == "__main__":
    main()
