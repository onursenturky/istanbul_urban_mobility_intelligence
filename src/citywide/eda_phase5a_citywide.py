"""Phase 5A: Citywide Exploratory Spatial Analysis and Feature Screening.

Goal: understand the structure of the citywide feature space and produce a
defensible, reduced predictor set for later spatial typology/clustering and
scenario-based suitability analysis. This phase does NOT compute a
suitability score, run PCA, or cluster anything -- it is screening only.

Reads:
  data/processed/citywide/features/urban_mobility_features_citywide.parquet
  data/processed/citywide/metadata/feature_dictionary_citywide.csv

The original master table is never modified. All screening artifacts are
written under analysis/eda/.
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.preprocessing import RobustScaler

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

MASTER_PATH = cfg.DATA_PROCESSED / "features" / "urban_mobility_features_citywide.parquet"
DICT_PATH = cfg.DATA_PROCESSED / "metadata" / "feature_dictionary_citywide.csv"
EDA_DIR = cfg.PROJECT_ROOT / "analysis" / "eda"
MAPS_DIR = EDA_DIR / "maps"

# Features that must never be treated as "redundant" with something else
# regardless of citywide correlation, because they are conceptually
# irreplaceable -- either for an e-bike/micromobility-focused study, or
# because they represent a structurally/functionally distinct transit mode
# whose network role differs even where its distance surface correlates
# with another mode's (both effects are driven by shared urban-density
# confounding: dense central areas tend to have everything close by).
#
# Per explicit semantic review (2026-09-19): metro (high-capacity urban
# rail), ferry (geographically distinctive -- Bosphorus/Marmara corridors
# with no substitute), and metrobüs (BRT corridor, a different operating
# concept from rail) are retained unconditionally. Tram and conventional
# rail are ALSO retained here rather than unilaterally dropped: the
# instruction allows removing them only if a documented semantic-loss
# justification is given, and no such justification is asserted -- both
# stay distinct, with their high correlation to the other three modes
# documented (not hidden) as a candidate for a FUTURE, separately-justified
# reduction, not decided in this pass.
NEVER_REDUNDANT = {
    "distance_to_nearest_bicycle_parking_m",
    "distance_to_nearest_micromobility_parking_m",
    "distance_to_nearest_metro_m",
    "distance_to_nearest_ferry_m",
    "distance_to_nearest_metrobus_m",
    "distance_to_nearest_tram_m",
    "distance_to_nearest_rail_m",
}

HIGH_CORR_THRESHOLD = 0.90
SKEW_LOG_THRESHOLD = 1.0
NEAR_ZERO_VARIANCE_CV_THRESHOLD = 0.05  # std/mean below this on a non-sparse feature is suspicious
EXTREME_SKEW_THRESHOLD = 3.0
VERY_SPARSE_ZERO_PCT_THRESHOLD = 90.0


def load_eligible_predictors() -> tuple[gpd.GeoDataFrame, pd.DataFrame, list[str]]:
    master = gpd.read_parquet(MASTER_PATH)
    feat_dict = pd.read_csv(DICT_PATH)

    eligible_names = feat_dict.loc[
        feat_dict["classification"].isin(["READY", "READY_WITH_LIMITATION"]), "feature_name"
    ].tolist()
    # Defensive: keep only columns that are actually numeric in the master
    # table (status sentinels are already excluded via classification, but
    # this guards against any future dictionary/table drift).
    eligible_names = [c for c in eligible_names if c in master.columns and pd.api.types.is_numeric_dtype(master[c])]
    return master, feat_dict, eligible_names


def handle_mean_building_footprint(master: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """mean_building_footprint_m2 is 0-filled by the upstream pipeline for
    cells with building_count=0 -- the mean of an empty set is
    mathematically undefined, not zero. A raw zero here would (a) pull the
    feature's mean/std toward zero, corrupting its descriptive stats and any
    correlation involving it, and (b) get scaled/clustered as if "buildings
    here average 0 m^2", which is not a real measurement.

    Decision: derive an explicit validity mask
    (has_buildings = building_count > 0) and an analysis copy,
    mean_building_footprint_m2_valid_only, with the placeholder zeros
    replaced by NaN. The RAW column and the master table are never
    modified. All downstream EDA (descriptive stats, correlation,
    transformation, scaling) uses mean_building_footprint_m2_valid_only,
    computed only over the ~34% of cells with at least one building.
    """
    df = master.copy()
    df["has_buildings"] = df["building_count"] > 0
    df["mean_building_footprint_m2_valid_only"] = df["mean_building_footprint_m2"].where(df["has_buildings"])
    return df


def descriptive_audit(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    rows = []
    n_total = len(df)
    for c in cols:
        vals = df[c]
        valid = vals.dropna()
        n_valid = len(valid)
        if n_valid == 0:
            continue
        zero_pct = float((valid == 0).mean() * 100)
        std = float(valid.std())
        mean = float(valid.mean())
        skew = float(stats.skew(valid)) if valid.nunique() > 1 else 0.0
        n_unique = int(valid.nunique())
        q1, q3 = valid.quantile(0.25), valid.quantile(0.75)
        iqr = float(q3 - q1)

        extreme_skew = abs(skew) > EXTREME_SKEW_THRESHOLD
        near_zero_variance = (abs(mean) > 1e-9) and (std / abs(mean) < NEAR_ZERO_VARIANCE_CV_THRESHOLD) and zero_pct < 50
        very_sparse = zero_pct > VERY_SPARSE_ZERO_PCT_THRESHOLD
        n_missing = n_total - n_valid

        rows.append({
            "feature": c, "n_valid": n_valid, "n_missing": n_missing,
            "min": float(valid.min()), "p5": float(valid.quantile(0.05)), "p25": float(q1),
            "median": float(valid.median()), "p75": float(q3), "p95": float(valid.quantile(0.95)),
            "max": float(valid.max()), "mean": mean, "std": std, "iqr": iqr,
            "zero_prevalence_pct": round(zero_pct, 2), "skewness": round(skew, 3), "n_unique": n_unique,
            "flag_extreme_skew": extreme_skew, "flag_near_zero_variance": near_zero_variance,
            "flag_very_sparse": very_sparse,
        })
    return pd.DataFrame(rows)


def correlation_analysis(df: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    corr = df[cols].corr(method="spearman", min_periods=30)
    pairs = []
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            r = corr.loc[a, b]
            if pd.notna(r) and abs(r) >= HIGH_CORR_THRESHOLD:
                pairs.append({"feature_a": a, "feature_b": b, "spearman_rho": round(float(r), 4)})
    pairs_df = pd.DataFrame(pairs).sort_values("spearman_rho", key=abs, ascending=False) if pairs else pd.DataFrame(columns=["feature_a", "feature_b", "spearman_rho"])
    return corr, pairs_df


def build_redundancy_recommendations(high_corr_pairs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Groups highly-correlated pairs into clusters (via union-find on the
    pair graph) and recommends ONE representative per group, using feature
    semantics/interpretability -- not correlation strength alone.

    Pairs involving a NEVER_REDUNDANT feature are excluded from the
    union-find grouping entirely (that feature is never folded into another
    group's "drop" list) but are still reported separately, documenting the
    correlation without recommending removal -- transitive chaining across
    a large correlation graph otherwise produces semantically incoherent
    groups (verified case: bicycle/micromobility-parking distance chained
    transitively through several transit-mode distances into a group whose
    auto-picked representative was tram-station distance, which measures a
    different infrastructure type entirely)."""
    never_redundant_notes = high_corr_pairs[
        high_corr_pairs["feature_a"].isin(NEVER_REDUNDANT) | high_corr_pairs["feature_b"].isin(NEVER_REDUNDANT)
    ].copy()
    if len(never_redundant_notes):
        never_redundant_notes["note"] = (
            "Correlation involves a feature in NEVER_REDUNDANT (conceptually irreplaceable for an "
            "e-bike-focused study); both features retained regardless of correlation strength -- this "
            "reflects shared urban-density confounding, not true redundancy."
        )
    high_corr_pairs = high_corr_pairs[
        ~high_corr_pairs["feature_a"].isin(NEVER_REDUNDANT) & ~high_corr_pairs["feature_b"].isin(NEVER_REDUNDANT)
    ]

    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for _, row in high_corr_pairs.iterrows():
        union(row["feature_a"], row["feature_b"])

    groups: dict[str, list[str]] = {}
    for name in parent:
        groups.setdefault(find(name), []).append(name)

    # Semantic preference order: prefer density/ratio over raw count, prefer
    # calibrated over raw population, prefer a single representative summary
    # stat over multiple summaries of the same distribution, prefer
    # distance-to-nearest over within-radius counts for accessibility
    # (finer-grained, continuous), prefer the current-feed transit measure
    # over the mixed-currency one where both appear.
    preference_keywords = [
        "population_density_calibrated_km2", "population_calibrated",
        "cycle_infrastructure_density_km_per_km2_ibb_only",
        "poi_density_km2", "mean_slope_deg", "mean_elevation_m",
        "distance_to_nearest_transit_m",
        # Prefer general/pooled (any-mode) measures over a single-mode subset,
        # and prefer direct service-intensity (departures) over raw route
        # count -- both corrections made after reviewing an initial run where
        # the shortest-name fallback picked the narrower variable in each case.
        "transit_stops_within_500m", "bus_departures_per_day",
        "building_coverage_ratio",
    ]

    rows = []
    for group_id, members in groups.items():
        if len(members) < 2:
            continue
        rep = next((m for m in preference_keywords if m in members), None)
        if rep is None:
            # fall back: prefer a "density" or "ratio" or "calibrated" named
            # column, else the shortest name (usually the most aggregate one)
            scored = sorted(members, key=lambda m: (
                0 if ("density" in m or "ratio" in m or "calibrated" in m) else 1, len(m)
            ))
            rep = scored[0]
        rows.append({
            "redundancy_group_id": group_id,
            "members": ", ".join(sorted(members)),
            "n_members": len(members),
            "recommended_representative": rep,
            "recommended_to_drop": ", ".join(sorted(m for m in members if m != rep)),
            "rationale": "High Spearman correlation (|rho|>=0.90) among these features; "
            f"'{rep}' retained as the most interpretable/normalized representative of this group "
            "based on feature semantics, not correlation strength alone.",
        })
    return pd.DataFrame(rows), never_redundant_notes


def transformation_recommendations(desc: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in desc.iterrows():
        c = r["feature"]
        if r["min"] < 0:
            continue  # log1p not applicable to features with negative values (e.g. elevation, distances are non-negative though)
        if r["skewness"] <= SKEW_LOG_THRESHOLD:
            continue
        valid = df[c].dropna()
        transformed = np.log1p(valid.clip(lower=0))
        skew_after = float(stats.skew(transformed)) if transformed.nunique() > 1 else 0.0
        rows.append({
            "feature": c, "skew_raw": round(r["skewness"], 3), "skew_after_log1p": round(skew_after, 3),
            "zero_prevalence_pct": r["zero_prevalence_pct"],
            "recommendation": "log1p" if abs(skew_after) < abs(r["skewness"]) else "no_improvement_keep_raw",
            "rationale": "Right-skewed non-negative count/density variable; log1p compresses the long tail "
            "while preserving zero as zero, keeping the interpretation 'no infrastructure/activity here' intact.",
        })
    return pd.DataFrame(rows).sort_values("skew_raw", ascending=False)


def make_eda_maps(df: gpd.GeoDataFrame, districts_gdf: gpd.GeoDataFrame) -> list[str]:
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    minx, miny, maxx, maxy = districts_gdf.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    extent = (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)

    def _base(ax, title):
        districts_gdf.boundary.plot(ax=ax, linewidth=0.6, color="black", zorder=3, alpha=0.6)
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        ax.set_title(title, fontsize=11)
        ax.set_axis_off()

    specs = [
        ("population_density_calibrated_km2", "Calibrated population density (people/km^2)", "magma_r", "eda_population_density.png", 98),
        ("building_coverage_ratio", "Building coverage ratio (built footprint / land area)", "Oranges", "eda_building_intensity.png", 98),
        ("poi_density_km2", "POI / activity density (POIs per km^2)", "viridis", "eda_poi_activity_intensity.png", 98),
        ("distance_to_nearest_transit_m", "Distance to nearest transit stop (m)", "viridis_r", "eda_transit_accessibility.png", 98),
        ("mean_slope_deg", "Mean terrain slope (degrees)", "YlOrRd", "eda_terrain_slope.png", 100),
        ("cycle_infrastructure_density_km_per_km2_ibb_only", "İBB cycling infrastructure density (km/km^2)", "Blues", "eda_cycling_infrastructure.png", 100),
    ]
    saved = []
    for col, title, cmap, filename, pct_clip in specs:
        vmax = np.nanpercentile(df[col], pct_clip) if pct_clip < 100 else df[col].max()
        fig, ax = plt.subplots(figsize=(9, 9))
        df.plot(column=col, cmap=cmap, ax=ax, legend=True, edgecolor="none", vmin=0, vmax=vmax if vmax > 0 else None)
        _base(ax, title)
        out = MAPS_DIR / filename
        fig.savefig(out, dpi=180, bbox_inches="tight")
        plt.close(fig)
        saved.append(str(out))
        print(f"  [map] {out}")
    return saved


def district_diagnostics(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    agg = df.groupby("district")[cols].agg(["mean", "median"])
    agg.columns = [f"{c}_{stat}" for c, stat in agg.columns]
    return agg.reset_index()


def build_reduced_feature_set(
    eligible: list[str], redundancy: pd.DataFrame, desc: pd.DataFrame, feat_dict: pd.DataFrame
) -> pd.DataFrame:
    to_drop = set()
    for _, r in redundancy.iterrows():
        to_drop.update(m.strip() for m in r["recommended_to_drop"].split(","))

    # Additional semantic drops not necessarily caught by the 0.90 threshold
    # but clearly redundant or unsuitable for direct multivariate use:
    manual_drops = {
        "mean_building_footprint_m2": "Superseded by mean_building_footprint_m2_valid_only (masked version) for analysis; raw version carries undefined-mean placeholder zeros.",
        "mean_building_footprint_m2_valid_only": "43%+ structural missingness once correctly masked (only cells with buildings have a defined mean) -- too sparse for direct inclusion in a complete-case multivariate matrix; kept in descriptive/correlation audit only.",
    }

    rows = []
    for c in eligible:
        if c == "mean_building_footprint_m2":
            continue  # replaced by masked version, itself then dropped below -- never enters the reduced set
        reason_drop = None
        if c in NEVER_REDUNDANT:
            reason_drop = None  # always retained regardless of correlation with anything else
        elif c in to_drop:
            reason_drop = "Redundant: high Spearman correlation with a retained representative (see redundancy_recommendations.csv)"
        elif c in manual_drops:
            reason_drop = manual_drops[c]
        d = desc[desc["feature"] == c]
        if reason_drop is None and len(d) and d.iloc[0]["flag_near_zero_variance"]:
            reason_drop = "Near-zero variance relative to its mean (not sparse) -- unlikely to be discriminative"

        family = feat_dict.loc[feat_dict["feature_name"] == c, "feature_family"].iloc[0] if c in feat_dict["feature_name"].values else "unknown"
        classification = feat_dict.loc[feat_dict["feature_name"] == c, "classification"].iloc[0] if c in feat_dict["feature_name"].values else "unknown"
        rows.append({
            "feature": c, "family": family, "eligibility_classification": classification,
            "included_in_reduced_set": reason_drop is None,
            "exclusion_reason": reason_drop,
        })
    return pd.DataFrame(rows)


def main() -> None:
    print("=" * 72)
    print("Phase 5A: Citywide Exploratory Spatial Analysis and Feature Screening")
    print("=" * 72)

    EDA_DIR.mkdir(parents=True, exist_ok=True)
    master, feat_dict, eligible = load_eligible_predictors()
    print(f"\nLoaded master table: {len(master)} rows. Eligible (READY + READY_WITH_LIMITATION) numeric predictors: {len(eligible)}")

    df = handle_mean_building_footprint(master)
    analysis_cols = [c if c != "mean_building_footprint_m2" else "mean_building_footprint_m2_valid_only" for c in eligible]
    print(f"\n[preprocessing] mean_building_footprint_m2 -> mean_building_footprint_m2_valid_only "
          f"(NaN for {int((~df['has_buildings']).sum())} zero-building cells, "
          f"{(~df['has_buildings']).mean()*100:.1f}% of all cells)")

    print("\n[1/6] Descriptive audit...")
    desc = descriptive_audit(df, analysis_cols)
    desc.to_csv(EDA_DIR / "feature_descriptive_statistics.csv", index=False)
    print(f"  saved {EDA_DIR / 'feature_descriptive_statistics.csv'} ({len(desc)} features)")
    extreme_skew_feats = desc.loc[desc["flag_extreme_skew"], "feature"].tolist()
    sparse_feats = desc.loc[desc["flag_very_sparse"], "feature"].tolist()
    nzv_feats = desc.loc[desc["flag_near_zero_variance"], "feature"].tolist()
    print(f"  extreme skew (|skew|>{EXTREME_SKEW_THRESHOLD}): {len(extreme_skew_feats)}")
    print(f"  very sparse (>{VERY_SPARSE_ZERO_PCT_THRESHOLD}% zero): {len(sparse_feats)}")
    print(f"  near-zero variance: {nzv_feats}")

    print("\n[2/6] Spearman correlation...")
    corr, high_corr_pairs = correlation_analysis(df, analysis_cols)
    corr.to_csv(EDA_DIR / "feature_correlation_spearman.csv")
    print(f"  saved {EDA_DIR / 'feature_correlation_spearman.csv'} ({corr.shape[0]}x{corr.shape[1]})")
    print(f"  high-correlation pairs (|rho|>={HIGH_CORR_THRESHOLD}): {len(high_corr_pairs)}")

    print("\n[3/6] Redundancy recommendations...")
    redundancy, never_redundant_notes = build_redundancy_recommendations(high_corr_pairs)
    redundancy.to_csv(EDA_DIR / "redundancy_recommendations.csv", index=False)
    if len(never_redundant_notes):
        never_redundant_notes.to_csv(EDA_DIR / "redundancy_never_redundant_correlations.csv", index=False)
    print(f"  saved {EDA_DIR / 'redundancy_recommendations.csv'} ({len(redundancy)} groups)")
    print(f"  {len(never_redundant_notes)} high-correlation pair(s) involving NEVER_REDUNDANT features "
          f"documented separately, not folded into a group: {never_redundant_notes[['feature_a', 'feature_b', 'spearman_rho']].values.tolist() if len(never_redundant_notes) else []}")
    for _, r in redundancy.iterrows():
        print(f"    group {r['redundancy_group_id']}: keep [{r['recommended_representative']}], drop [{r['recommended_to_drop']}]")

    print("\n[4/6] Transformation recommendations...")
    transform_rec = transformation_recommendations(desc, df)
    transform_rec.to_csv(EDA_DIR / "transformation_recommendations.csv", index=False)
    print(f"  saved {EDA_DIR / 'transformation_recommendations.csv'} ({len(transform_rec)} features recommended for log1p)")

    print("\n[5/6] Spatial EDA maps...")
    districts_gdf = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    map_paths = make_eda_maps(df, districts_gdf)

    print("\n[6/6] District diagnostics + reduced feature set + scaled analysis matrix...")
    rep_cols_for_district_diag = [
        "population_density_calibrated_km2", "building_coverage_ratio", "poi_density_km2",
        "distance_to_nearest_transit_m", "mean_slope_deg", "cycle_infrastructure_density_km_per_km2_ibb_only",
    ]
    district_diag = district_diagnostics(df, rep_cols_for_district_diag)
    district_diag.to_csv(EDA_DIR / "district_diagnostic_summary.csv", index=False)
    print(f"  saved {EDA_DIR / 'district_diagnostic_summary.csv'} (descriptive only, NOT a ranking)")

    reduced = build_reduced_feature_set(analysis_cols, redundancy, desc, feat_dict)
    reduced.to_csv(EDA_DIR / "reduced_feature_set.csv", index=False)
    reduced_cols = reduced.loc[reduced["included_in_reduced_set"], "feature"].tolist()
    print(f"  saved {EDA_DIR / 'reduced_feature_set.csv'} -- {len(reduced_cols)}/{len(analysis_cols)} features retained")

    # Build the scaled analysis matrix: apply log1p to the recommended
    # features (within the reduced set only), then RobustScaler (median/IQR
    # -- appropriate given the heavy skew/outliers already documented)
    # across the full reduced set. Complete cases only (the reduced set was
    # explicitly chosen to exclude mean_building_footprint_m2_valid_only,
    # the only feature with structural missingness, so this matrix has zero
    # NaNs by construction).
    log_cols = set(transform_rec.loc[transform_rec["recommendation"] == "log1p", "feature"]) & set(reduced_cols)
    analysis_matrix = df[["grid_id", "district"] + reduced_cols].copy()
    for c in log_cols:
        analysis_matrix[c] = np.log1p(analysis_matrix[c].clip(lower=0))

    assert analysis_matrix[reduced_cols].isna().sum().sum() == 0, "reduced analysis matrix must have zero NaNs before scaling"

    scaler = RobustScaler()
    scaled_values = scaler.fit_transform(analysis_matrix[reduced_cols])
    scaled_df = pd.DataFrame(scaled_values, columns=[f"{c}_scaled" for c in reduced_cols], index=analysis_matrix.index)
    analysis_matrix = pd.concat([analysis_matrix, scaled_df], axis=1)
    analysis_matrix.to_parquet(EDA_DIR / "analysis_matrix_scaled.parquet")
    print(f"  saved {EDA_DIR / 'analysis_matrix_scaled.parquet'} ({len(analysis_matrix)} rows x {len(reduced_cols)} scaled features, log1p applied to {len(log_cols)} of them)")

    conceptual_dimensions = sorted(set(feat_dict.set_index("feature_name").reindex(reduced_cols)["feature_family"].dropna()))

    summary = {
        "n_master_rows": len(master),
        "n_total_predictor_columns_in_master": int(len(feat_dict)),
        "n_eligible_numeric_predictors": len(eligible),
        "eligible_predictor_names": eligible,
        "preprocessing_decisions": [
            "mean_building_footprint_m2: raw column left unchanged in the master table (0-filled placeholder for "
            "cells with building_count=0). For all EDA (descriptive stats, correlation, transformation, scaling), "
            "an explicit validity mask has_buildings=(building_count>0) was derived, and a masked analysis copy "
            "mean_building_footprint_m2_valid_only (NaN where has_buildings=False) was used instead of the raw "
            f"column. {int((~df['has_buildings']).sum())} cells ({(~df['has_buildings']).mean()*100:.1f}%) are "
            "masked as NaN. The masked version was ultimately EXCLUDED from the reduced/scaled analysis matrix "
            "because its missingness rate is too high for a complete-case multivariate matrix; it remains "
            "available in the descriptive-statistics and correlation outputs.",
        ],
        "n_extreme_skew_features": len(extreme_skew_feats), "extreme_skew_features": extreme_skew_feats,
        "n_very_sparse_features": len(sparse_feats), "very_sparse_features": sparse_feats,
        "n_near_zero_variance_features": len(nzv_feats), "near_zero_variance_features": nzv_feats,
        "n_high_correlation_pairs": len(high_corr_pairs),
        "n_redundancy_groups": len(redundancy),
        "n_features_recommended_log1p": int((transform_rec["recommendation"] == "log1p").sum()) if len(transform_rec) else 0,
        "n_reduced_feature_set": len(reduced_cols),
        "reduced_feature_set": reduced_cols,
        "conceptual_dimensions_in_reduced_set": conceptual_dimensions,
        "eda_maps_produced": map_paths,
        "district_diagnostic_note": "Descriptive only (mean/median per district for 6 representative dimensions) -- "
        "NOT a best/worst ranking for e-bike deployment.",
        "issues_to_resolve_before_clustering": [
            "Land-use (PARTIAL, 22/39 districts) and the full road network (PARTIAL, 0/39 districts) are not yet "
            "part of any feature family and remain entirely absent from this analysis -- clustering/typology run "
            "now would exclude green-space and road-grade dimensions used in the pilot's Phase 5 framework.",
            "Population, transit (main_gtfs modes), and all cycling _ibb_only features carry READY_WITH_LIMITATION "
            "caveats (temporal misalignment, İBB-only vs pilot's İBB+OSM definition) that should inform "
            "interpretation of any resulting typology, not just modeling mechanics.",
            "mean_building_footprint_m2 has no complete-case representation in this reduced set -- if building "
            "size (as opposed to coverage ratio) is later judged important, a dedicated imputation or two-part "
            "(presence + conditional size) treatment would be needed.",
        ],
    }
    summary_path = EDA_DIR / "eda_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[save] {summary_path}")

    print("\n--- SUMMARY ---")
    print(f"Eligible predictors: {len(eligible)}")
    print(f"Reduced predictor set: {len(reduced_cols)}")
    print(f"Conceptual dimensions represented: {conceptual_dimensions}")


if __name__ == "__main__":
    main()
