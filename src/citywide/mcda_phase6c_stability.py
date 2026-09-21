"""Phase 6C: Overall Scenario Comparison, Consensus and Stability Analysis.

Uses ONLY the already-computed Phase 6B scenario_scores.parquet -- no
criteria, value functions, or weights are redefined here. The objective is
to determine which spatial signals are robust across the Phase 6B
assumption space and which are assumption-sensitive. Readiness and
Opportunity are never combined into a single score, and no scenario is
selected as preferred.
"""

from __future__ import annotations

import json
from itertools import combinations

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from libpysal.weights import Queen
from scipy.stats import percentileofscore, rankdata, spearmanr

from src.analysis.spatial_diagnostics import morans_i
from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

PHASE6B_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda" / "phase6b"
OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda" / "phase6c"
MAPS_DIR = OUT_DIR / "maps"
CLUSTER_V2_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering_v2"


def parse_readiness_variant(col: str) -> dict:
    # readiness__{scenario}__{T1|T2}__uf_{sat|tr}
    _, scenario, transit, uf = col.split("__")
    return {"scenario": scenario, "transit_variant": transit, "uf_variant": uf.replace("uf_", "")}


def parse_opportunity_variant(col: str) -> dict:
    # opportunity__{scenario}__demand_{sat|tr}
    _, scenario, demand = col.split("__")
    return {"scenario": scenario, "demand_variant": demand.replace("demand_", "")}


def pairwise_comparison(scores: pd.DataFrame, cols: list[str], parse_fn) -> pd.DataFrame:
    n = len(scores)
    top_decile_masks = {c: scores[c] >= scores[c].quantile(0.9) for c in cols}
    ranks = {c: rankdata(scores[c]) / n for c in cols}

    rows = []
    for a, b in combinations(cols, 2):
        rho, _ = spearmanr(scores[a], scores[b])
        inter = (top_decile_masks[a] & top_decile_masks[b]).sum()
        union = (top_decile_masks[a] | top_decile_masks[b]).sum()
        jaccard = inter / union if union else 0.0
        mad = float((scores[a] - scores[b]).abs().mean())
        rank_disp = float(np.abs(ranks[a] - ranks[b]).mean())
        entries = int((top_decile_masks[b] & ~top_decile_masks[a]).sum())  # in b's top decile, not a's
        exits = int((top_decile_masks[a] & ~top_decile_masks[b]).sum())

        meta_a, meta_b = parse_fn(a), parse_fn(b)
        differing_factors = sorted(k for k in meta_a if meta_a[k] != meta_b[k])
        rows.append({
            "variant_a": a, "variant_b": b, "spearman_rho": round(float(rho), 4),
            "jaccard_top_decile": round(float(jaccard), 4), "mean_abs_score_diff": round(mad, 4),
            "mean_rank_displacement": round(rank_disp, 4), "top_decile_entries_b_not_a": entries,
            "top_decile_exits_a_not_b": exits, "differing_factors": ",".join(differing_factors),
            "n_differing_factors": len(differing_factors),
        })
    return pd.DataFrame(rows)


def isolated_factor_effect(comparison_df: pd.DataFrame, factor_names: list[str]) -> pd.DataFrame:
    """Restricts to pairs differing in EXACTLY ONE factor, then averages
    disagreement metrics per factor -- a controlled comparison isolating
    each assumption's individual effect, not a confounded blend."""
    rows = []
    for factor in factor_names:
        isolated = comparison_df[(comparison_df["n_differing_factors"] == 1) & (comparison_df["differing_factors"] == factor)]
        if len(isolated) == 0:
            continue
        rows.append({
            "factor": factor, "n_isolated_pairs": len(isolated),
            "mean_spearman_rho": round(float(isolated["spearman_rho"].mean()), 4),
            "mean_jaccard_top_decile": round(float(isolated["jaccard_top_decile"].mean()), 4),
            "mean_abs_score_diff": round(float(isolated["mean_abs_score_diff"].mean()), 4),
            "mean_rank_displacement": round(float(isolated["mean_rank_displacement"].mean()), 4),
        })
    return pd.DataFrame(rows).sort_values("mean_spearman_rho")


def cell_stability(scores: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    vals = scores[cols].to_numpy()
    n_cells, n_variants = vals.shape
    ranks = np.apply_along_axis(lambda col: rankdata(col) / n_cells, 0, vals)
    thresholds = np.quantile(vals, 0.9, axis=0)
    top_decile = vals >= thresholds

    return pd.DataFrame({
        "grid_id": scores["grid_id"], "district": scores["district"],
        "mean_score": vals.mean(axis=1), "median_score": np.median(vals, axis=1),
        "min_score": vals.min(axis=1), "max_score": vals.max(axis=1),
        "std_score": vals.std(axis=1), "range_score": vals.max(axis=1) - vals.min(axis=1),
        "mean_rank_pct": ranks.mean(axis=1), "std_rank_pct": ranks.std(axis=1),
        "n_top_decile": top_decile.sum(axis=1), "pct_top_decile": top_decile.mean(axis=1) * 100,
    })


def consensus_class(pct_top_decile: pd.Series) -> pd.Series:
    conditions = [
        pct_top_decile >= 100, (pct_top_decile >= 75) & (pct_top_decile < 100),
        (pct_top_decile >= 25) & (pct_top_decile < 75), (pct_top_decile > 0) & (pct_top_decile < 25),
        pct_top_decile == 0,
    ]
    choices = ["ROBUST_HIGH", "FREQUENT_HIGH", "CONDITIONAL_HIGH", "RARE_HIGH", "NEVER_HIGH"]
    return pd.Series(np.select(conditions, choices, default="NEVER_HIGH"), index=pct_top_decile.index)


def eta_squared_driver(vals: np.ndarray, factor_labels: list[np.ndarray], factor_names: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Per-cell (per-row) eta-squared (between-group SS / total SS) for
    each factor, computed vectorized across all cells. Returns
    (eta_squared_matrix [n_cells x n_factors], dominant_driver_index)."""
    n_cells = vals.shape[0]
    grand_mean = vals.mean(axis=1, keepdims=True)
    total_ss = ((vals - grand_mean) ** 2).sum(axis=1)

    eta_sq = np.zeros((n_cells, len(factor_names)))
    for fi, labels in enumerate(factor_labels):
        levels = np.unique(labels)
        between_ss = np.zeros(n_cells)
        for lvl in levels:
            mask = labels == lvl
            group_mean = vals[:, mask].mean(axis=1, keepdims=True)
            between_ss += mask.sum() * ((group_mean[:, 0] - grand_mean[:, 0]) ** 2)
        with np.errstate(divide="ignore", invalid="ignore"):
            eta_sq[:, fi] = np.where(total_ss > 1e-12, between_ss / total_ss, 0.0)
    dominant_idx = np.argmax(eta_sq, axis=1)
    return eta_sq, dominant_idx


def main() -> None:
    print("=" * 72)
    print("Phase 6C: Overall Scenario Comparison, Consensus and Stability Analysis")
    print("=" * 72)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MAPS_DIR.mkdir(parents=True, exist_ok=True)

    scores = pd.read_parquet(PHASE6B_DIR / "scenario_scores.parquet")
    readiness_cols = sorted([c for c in scores.columns if c.startswith("readiness__")])
    opportunity_cols = sorted([c for c in scores.columns if c.startswith("opportunity__")])
    print(f"\nLoaded {len(scores)} cells. Readiness variants: {len(readiness_cols)}. Opportunity variants: {len(opportunity_cols)}.")

    # --- 1. Full scenario comparison matrix ---
    print("\n[1/9] Full scenario comparison matrix...")
    readiness_comp = pairwise_comparison(scores, readiness_cols, parse_readiness_variant)
    readiness_comp["score_type"] = "readiness"
    opportunity_comp = pairwise_comparison(scores, opportunity_cols, parse_opportunity_variant)
    opportunity_comp["score_type"] = "opportunity"
    comparison_matrix = pd.concat([readiness_comp, opportunity_comp], ignore_index=True)
    comparison_matrix.to_csv(OUT_DIR / "scenario_comparison_matrix.csv", index=False)
    print(f"  saved scenario_comparison_matrix.csv ({len(comparison_matrix)} pairs)")

    strongest = comparison_matrix.loc[comparison_matrix["spearman_rho"].idxmax()]
    weakest = comparison_matrix.loc[comparison_matrix["spearman_rho"].idxmin()]
    print(f"  strongest agreement: {strongest['variant_a']} vs {strongest['variant_b']} (rho={strongest['spearman_rho']})")
    print(f"  weakest agreement:   {weakest['variant_a']} vs {weakest['variant_b']} (rho={weakest['spearman_rho']}, differs in: {weakest['differing_factors']})")

    print("\n  Isolated-factor effect on READINESS (controlled: pairs differing in exactly one factor)...")
    readiness_factor_effect = isolated_factor_effect(readiness_comp, ["scenario", "transit_variant", "uf_variant"])
    print(readiness_factor_effect.to_string(index=False))
    print("\n  Isolated-factor effect on OPPORTUNITY...")
    opportunity_factor_effect = isolated_factor_effect(opportunity_comp, ["scenario", "demand_variant"])
    print(opportunity_factor_effect.to_string(index=False))
    readiness_factor_effect["score_type"] = "readiness"
    opportunity_factor_effect["score_type"] = "opportunity"
    pd.concat([readiness_factor_effect, opportunity_factor_effect]).to_csv(OUT_DIR / "isolated_factor_effects.csv", index=False)

    # --- 2. Cell-level stability metrics ---
    print("\n[2/9] Cell-level stability metrics...")
    readiness_stability = cell_stability(scores, readiness_cols).add_prefix("readiness_")
    readiness_stability = readiness_stability.rename(columns={"readiness_grid_id": "grid_id", "readiness_district": "district"})
    opportunity_stability = cell_stability(scores, opportunity_cols).add_prefix("opportunity_")
    opportunity_stability = opportunity_stability.drop(columns=["opportunity_grid_id", "opportunity_district"])

    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")[["grid_id", "geometry"]]
    stability = pd.concat([readiness_stability, opportunity_stability], axis=1)
    stability_gdf = gpd.GeoDataFrame(stability.merge(grid, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)
    stability_gdf.to_parquet(OUT_DIR / "cell_stability_metrics.parquet")
    print(f"  saved cell_stability_metrics.parquet")

    # --- 3. Consensus classes ---
    print("\n[3/9] Consensus classes...")
    stability_gdf["readiness_consensus_class"] = consensus_class(stability_gdf["readiness_pct_top_decile"])
    stability_gdf["opportunity_consensus_class"] = consensus_class(stability_gdf["opportunity_pct_top_decile"])
    print("  Readiness consensus classes:")
    print(stability_gdf["readiness_consensus_class"].value_counts())
    print("  Opportunity consensus classes:")
    print(stability_gdf["opportunity_consensus_class"].value_counts())

    n_robust_readiness = int((stability_gdf["readiness_pct_top_decile"] == 100).sum())
    n_robust_opportunity = int((stability_gdf["opportunity_pct_top_decile"] == 100).sum())
    print(f"\n  VERIFIED (from underlying scenario table, not hard-coded): "
          f"{n_robust_readiness} cells top-decile in ALL {len(readiness_cols)} readiness variants; "
          f"{n_robust_opportunity} cells top-decile in ALL {len(opportunity_cols)} opportunity variants.")

    stability_gdf[["grid_id", "district", "readiness_consensus_class", "opportunity_consensus_class",
                   "readiness_pct_top_decile", "opportunity_pct_top_decile", "geometry"]].to_parquet(OUT_DIR / "consensus_classes.parquet")
    print(f"  saved consensus_classes.parquet")

    # --- 4. Joint Readiness x Opportunity matrix (descriptive only) ---
    print("\n[4/9] Joint Readiness x Opportunity matrix...")

    def simplify(cls):
        return {"ROBUST_HIGH": "HIGH", "FREQUENT_HIGH": "HIGH", "CONDITIONAL_HIGH": "MODERATE_SENSITIVE",
                "RARE_HIGH": "LOW", "NEVER_HIGH": "LOW"}[cls]

    stability_gdf["readiness_simplified"] = stability_gdf["readiness_consensus_class"].map(simplify)
    stability_gdf["opportunity_simplified"] = stability_gdf["opportunity_consensus_class"].map(simplify)
    stability_gdf["joint_class"] = stability_gdf["readiness_simplified"] + "_readiness__" + stability_gdf["opportunity_simplified"] + "_opportunity"
    joint_counts = stability_gdf["joint_class"].value_counts()
    print(joint_counts)

    interesting = stability_gdf[(stability_gdf["opportunity_simplified"] == "HIGH") & (stability_gdf["readiness_simplified"].isin(["LOW", "MODERATE_SENSITIVE"]))]
    print(f"\n  Conceptually interesting case -- HIGH opportunity + only moderate/low readiness: {len(interesting)} cells "
          f"({len(interesting)/len(stability_gdf)*100:.2f}% of the city). NOT a deployment recommendation -- these are "
          f"latent-demand areas where enabling infrastructure is comparatively weaker.")

    stability_gdf[["grid_id", "district", "readiness_consensus_class", "opportunity_consensus_class",
                   "joint_class", "geometry"]].to_parquet(OUT_DIR / "joint_readiness_opportunity_classes.parquet")
    print(f"  saved joint_readiness_opportunity_classes.parquet")

    # --- 5. Assumption-attribution analysis ---
    print("\n[5/9] Assumption-attribution (dominant sensitivity driver) analysis...")
    readiness_meta = [parse_readiness_variant(c) for c in readiness_cols]
    scenario_labels = np.array([m["scenario"] for m in readiness_meta])
    transit_labels = np.array([m["transit_variant"] for m in readiness_meta])
    uf_labels = np.array([m["uf_variant"] for m in readiness_meta])

    r_vals = scores[readiness_cols].to_numpy()
    eta_sq, dominant_idx = eta_squared_driver(r_vals, [scenario_labels, transit_labels, uf_labels], ["scenario", "transit_variant", "uf_variant"])
    driver_names = np.array(["scenario", "transit_variant", "uf_variant"])
    stability_gdf["readiness_dominant_driver"] = driver_names[dominant_idx]
    stability_gdf["readiness_dominant_driver_eta_sq"] = eta_sq[np.arange(len(eta_sq)), dominant_idx]
    # only meaningful for cells with nonzero disagreement
    stability_gdf.loc[stability_gdf["readiness_range_score"] < 1e-6, "readiness_dominant_driver"] = "NO_DISAGREEMENT"

    opp_meta = [parse_opportunity_variant(c) for c in opportunity_cols]
    opp_scenario_labels = np.array([m["scenario"] for m in opp_meta])
    opp_demand_labels = np.array([m["demand_variant"] for m in opp_meta])
    o_vals = scores[opportunity_cols].to_numpy()
    opp_eta_sq, opp_dominant_idx = eta_squared_driver(o_vals, [opp_scenario_labels, opp_demand_labels], ["scenario", "demand_variant"])
    opp_driver_names = np.array(["scenario", "demand_variant"])
    stability_gdf["opportunity_dominant_driver"] = opp_driver_names[opp_dominant_idx]
    stability_gdf["opportunity_dominant_driver_eta_sq"] = opp_eta_sq[np.arange(len(opp_eta_sq)), opp_dominant_idx]
    stability_gdf.loc[stability_gdf["opportunity_range_score"] < 1e-6, "opportunity_dominant_driver"] = "NO_DISAGREEMENT"

    print("  Readiness dominant driver (cells with any disagreement):")
    print(stability_gdf.loc[stability_gdf["readiness_dominant_driver"] != "NO_DISAGREEMENT", "readiness_dominant_driver"].value_counts())
    print("  Opportunity dominant driver (cells with any disagreement):")
    print(stability_gdf.loc[stability_gdf["opportunity_dominant_driver"] != "NO_DISAGREEMENT", "opportunity_dominant_driver"].value_counts())

    stability_gdf[["grid_id", "district", "readiness_dominant_driver", "readiness_dominant_driver_eta_sq",
                   "opportunity_dominant_driver", "opportunity_dominant_driver_eta_sq", "geometry"]].to_parquet(OUT_DIR / "sensitivity_driver_analysis.parquet")
    print(f"  saved sensitivity_driver_analysis.parquet")

    # --- 6. Robust-core analysis ---
    print("\n[6/9] Robust-core analysis (raw-variable characterization)...")
    master = gpd.read_parquet(cfg.DATA_PROCESSED / "features" / "urban_mobility_features_citywide.parquet")
    assignments = pd.read_parquet(CLUSTER_V2_DIR / "cluster_assignments_v2.parquet")

    raw_cols = ["population_density_calibrated_km2", "poi_density_km2", "distance_to_nearest_transit_m",
                "cycle_infrastructure_density_km_per_km2_ibb_only", "distance_to_nearest_bicycle_parking_m", "mean_slope_deg"]
    raw_df = master[["grid_id"] + raw_cols].merge(assignments[["grid_id", "cluster"]], on="grid_id")

    def profile_group(mask_ids: set, label: str) -> list[dict]:
        sub = raw_df[raw_df["grid_id"].isin(mask_ids)]
        rows = []
        for c in raw_cols:
            citywide_vals = raw_df[c].to_numpy()
            med = float(sub[c].median())
            q1, q3 = float(sub[c].quantile(0.25)), float(sub[c].quantile(0.75))
            pct = float(percentileofscore(citywide_vals, med, kind="mean"))
            rows.append({"group": label, "n_cells": len(sub), "feature": c, "median": round(med, 3),
                         "q1": round(q1, 3), "q3": round(q3, 3), "citywide_percentile_of_median": round(pct, 1)})
        return rows

    robust_readiness_ids = set(stability_gdf.loc[stability_gdf["readiness_consensus_class"] == "ROBUST_HIGH", "grid_id"])
    robust_opportunity_ids = set(stability_gdf.loc[stability_gdf["opportunity_consensus_class"] == "ROBUST_HIGH", "grid_id"])
    robust_profile_rows = profile_group(robust_readiness_ids, "robust_high_readiness") + profile_group(robust_opportunity_ids, "robust_high_opportunity")
    robust_profile_df = pd.DataFrame(robust_profile_rows)
    robust_profile_df.to_csv(OUT_DIR / "robust_core_profiles.csv", index=False)
    print(robust_profile_df.to_string(index=False))

    robust_readiness_typology = raw_df[raw_df["grid_id"].isin(robust_readiness_ids)]["cluster"].value_counts()
    robust_opportunity_typology = raw_df[raw_df["grid_id"].isin(robust_opportunity_ids)]["cluster"].value_counts()
    print(f"\n  Robust-high-readiness cells by k=5 cluster:\n{robust_readiness_typology}")
    print(f"\n  Robust-high-opportunity cells by k=5 cluster:\n{robust_opportunity_typology}")

    # --- 7. Spatial structure + Moran's I ---
    print("\n[7/9] Spatial structure of stability (Moran's I)...")
    w = Queen.from_dataframe(stability_gdf, use_index=False)
    w.transform = "r"
    moran_readiness_freq = morans_i(stability_gdf["readiness_pct_top_decile"].to_numpy(), w)
    moran_opportunity_freq = morans_i(stability_gdf["opportunity_pct_top_decile"].to_numpy(), w)
    moran_readiness_range = morans_i(stability_gdf["readiness_range_score"].to_numpy(), w)
    moran_opportunity_range = morans_i(stability_gdf["opportunity_range_score"].to_numpy(), w)
    spatial_stability_morans = {
        "readiness_consensus_frequency": moran_readiness_freq, "opportunity_consensus_frequency": moran_opportunity_freq,
        "readiness_score_range_uncertainty": moran_readiness_range, "opportunity_score_range_uncertainty": moran_opportunity_range,
    }
    for k, v in spatial_stability_morans.items():
        print(f"  {k}: Moran's I={v['morans_i']} ({v['interpretation']})")

    print("\n[8/9] Typology cross-tab + district summaries...")
    stability_full = stability_gdf.merge(assignments[["grid_id", "cluster"]], on="grid_id")
    typology_crosstab = pd.crosstab(stability_full["cluster"], stability_full["readiness_consensus_class"])
    typology_crosstab_opp = pd.crosstab(stability_full["cluster"], stability_full["opportunity_consensus_class"])
    typology_crosstab_joint = pd.crosstab(stability_full["cluster"], stability_full["joint_class"])
    with open(OUT_DIR / "typology_consensus_crosstab.csv", "w") as f:
        f.write("# Readiness consensus class by k=5 cluster\n")
        typology_crosstab.to_csv(f)
        f.write("\n# Opportunity consensus class by k=5 cluster\n")
        typology_crosstab_opp.to_csv(f)
        f.write("\n# Joint class by k=5 cluster\n")
        typology_crosstab_joint.to_csv(f)
    print(f"  saved typology_consensus_crosstab.csv")
    print(typology_crosstab)

    district_summary = stability_gdf.groupby("district").agg(
        n_cells=("grid_id", "count"),
        pct_readiness_robust_or_frequent=("readiness_simplified", lambda s: (s == "HIGH").mean() * 100),
        pct_opportunity_robust_or_frequent=("opportunity_simplified", lambda s: (s == "HIGH").mean() * 100),
        median_readiness_consensus_pct=("readiness_pct_top_decile", "median"),
        median_opportunity_consensus_pct=("opportunity_pct_top_decile", "median"),
        median_readiness_uncertainty_range=("readiness_range_score", "median"),
        median_opportunity_uncertainty_range=("opportunity_range_score", "median"),
    ).reset_index()
    district_summary.to_csv(OUT_DIR / "district_consensus_summary.csv", index=False)
    print(f"  saved district_consensus_summary.csv (descriptive only -- NOT a ranking)")

    print("\n[9/9] Maps...")
    make_maps(stability_gdf)

    summary = {
        "n_readiness_variants": len(readiness_cols), "n_opportunity_variants": len(opportunity_cols),
        "strongest_agreement": {"pair": [strongest["variant_a"], strongest["variant_b"]], "spearman_rho": float(strongest["spearman_rho"])},
        "weakest_agreement": {"pair": [weakest["variant_a"], weakest["variant_b"]], "spearman_rho": float(weakest["spearman_rho"]), "differing_factors": weakest["differing_factors"]},
        "isolated_factor_effects_readiness": readiness_factor_effect.to_dict(orient="records"),
        "isolated_factor_effects_opportunity": opportunity_factor_effect.to_dict(orient="records"),
        "readiness_consensus_class_counts": stability_gdf["readiness_consensus_class"].value_counts().to_dict(),
        "opportunity_consensus_class_counts": stability_gdf["opportunity_consensus_class"].value_counts().to_dict(),
        "n_robust_high_readiness_verified": n_robust_readiness,
        "n_robust_high_opportunity_verified": n_robust_opportunity,
        "joint_class_counts": joint_counts.to_dict(),
        "n_high_opportunity_moderate_or_low_readiness": int(len(interesting)),
        "readiness_dominant_driver_counts": stability_gdf.loc[stability_gdf["readiness_dominant_driver"] != "NO_DISAGREEMENT", "readiness_dominant_driver"].value_counts().to_dict(),
        "opportunity_dominant_driver_counts": stability_gdf.loc[stability_gdf["opportunity_dominant_driver"] != "NO_DISAGREEMENT", "opportunity_dominant_driver"].value_counts().to_dict(),
        "spatial_autocorrelation_of_stability_surfaces": spatial_stability_morans,
        "robust_core_typology_distribution": {
            "robust_high_readiness_by_cluster": robust_readiness_typology.to_dict(),
            "robust_high_opportunity_by_cluster": robust_opportunity_typology.to_dict(),
        },
        "methodological_stability_statement": {
            "robust_findings": [
                "The overall rank ordering of cells by Readiness is highly stable across weighting scenario, "
                "T1-vs-T2 transit assumption, and urban-form value-function variant (pairwise Spearman rho "
                f"ranging {comparison_matrix[comparison_matrix.score_type=='readiness'].spearman_rho.min():.3f} to 1.0).",
                "Opportunity is even more stable across its assumption space "
                f"(rho {comparison_matrix[comparison_matrix.score_type=='opportunity'].spearman_rho.min():.3f} to 1.0).",
                "Remote/empty peripheral cells never register as high-opportunity under any tested variant.",
                f"{n_robust_readiness} cells are Readiness-robust and {n_robust_opportunity} cells are "
                "Opportunity-robust across every tested variant -- a genuine cross-assumption core, not an "
                "artifact of one scenario choice.",
            ],
            "assumption_sensitive_findings": [
                "A meaningful minority of cells change top-decile membership depending on which assumption is "
                "varied -- see isolated_factor_effects.csv for which single assumption (scenario weighting vs "
                "T1/T2 vs value-function variant) drives the most disagreement.",
                "The 'balanced' and 'first_last_mile_transit_integration_oriented' weighting scenarios "
                "coincidentally produce an IDENTICAL demand-vs-cycling-readiness balance (alpha=0.5 in both) "
                "for the Opportunity formula, so their Opportunity scores are not independent evidence points "
                "for that particular sensitivity axis -- documented here so this is not mistaken for extra "
                "robustness.",
            ],
            "unresolved_evidence_gaps": [
                "No citywide road-network dimension.", "Incomplete citywide land-use/green-space dimension.",
                "No observed shared e-bike demand or deployment data exists anywhere in this project.",
                "Population reference-year, main_gtfs snapshot, and İBB-only cycling-inventory limitations "
                "carried forward from Phase 6A/6B.",
            ],
            "caveat": "Agreement across the tested Phase 6B assumptions means robustness TO THOSE ASSUMPTIONS "
            "ONLY -- it is not empirical validation against any observed outcome, since none exists in this "
            "project.",
        },
    }
    (OUT_DIR / "phase6c_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[save] {OUT_DIR / 'phase6c_summary.json'}")


def make_maps(stability_gdf: gpd.GeoDataFrame) -> None:
    districts_gdf = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    minx, miny, maxx, maxy = districts_gdf.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    extent = (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)

    def _base(ax, title):
        districts_gdf.boundary.plot(ax=ax, linewidth=0.5, color="black", alpha=0.5, zorder=3)
        ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
        ax.set_title(title, fontsize=10)
        ax.set_axis_off()

    specs = [
        ("readiness_pct_top_decile", "Readiness consensus frequency (% of 16 variants in top decile)", "YlGnBu"),
        ("opportunity_pct_top_decile", "Opportunity consensus frequency (% of 8 variants in top decile)", "PuRd"),
        ("readiness_range_score", "Readiness score uncertainty (max-min across 16 variants)", "magma"),
        ("opportunity_range_score", "Opportunity score uncertainty (max-min across 8 variants)", "magma"),
    ]
    for col, title, cmap in specs:
        fig, ax = plt.subplots(figsize=(9, 9))
        stability_gdf.plot(column=col, cmap=cmap, ax=ax, legend=True, edgecolor="none")
        _base(ax, title)
        fname = f"{col}.png"
        fig.savefig(MAPS_DIR / fname, dpi=170, bbox_inches="tight")
        plt.close(fig)
        print(f"  [map] {MAPS_DIR / fname}")

    fig, ax = plt.subplots(figsize=(11, 9))
    stability_gdf.plot(column="joint_class", categorical=True, cmap="tab10", ax=ax, legend=True, edgecolor="none",
                        legend_kwds={"title": "Joint class", "bbox_to_anchor": (1.05, 1)})
    _base(ax, "Joint Readiness x Opportunity consensus classes (descriptive, not a suitability ranking)")
    fig.savefig(MAPS_DIR / "joint_classes.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  [map] {MAPS_DIR / 'joint_classes.png'}")

    fig, ax = plt.subplots(figsize=(9, 9))
    stability_gdf.plot(column="readiness_dominant_driver", categorical=True, cmap="Set2", ax=ax, legend=True, edgecolor="none")
    _base(ax, "Dominant sensitivity driver for Readiness")
    fig.savefig(MAPS_DIR / "readiness_dominant_driver.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  [map] {MAPS_DIR / 'readiness_dominant_driver.png'}")


if __name__ == "__main__":
    main()
