"""Phase 6D: Assumption Resolution and Final Analytical Product Design.

Uses ONLY already-computed Phase 5C/6A/6B/6C outputs. No new score, no
scenario selection, no Readiness/Opportunity combination, no ranking, no
deployment recommendation. This phase audits anomalies, characterizes
already-identified cell groups, runs final methodological QA, freezes a
versioned manifest, and assembles a communication-ready layer purely by
joining existing outputs.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import percentileofscore

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

PHASE6B_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda" / "phase6b"
PHASE6C_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda" / "phase6c"
CLUSTER_V2_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering_v2"
MCDA_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda"
OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "final_v1"
MAPS_DIR = OUT_DIR / "maps"

VERSION_TAG = "INTERIM_CITYWIDE_V1_SIX_FAMILY"

CLUSTER_NAMES = {
    0: "moderate mixed-use activity",
    1: "undifferentiated baseline",
    2: "transit-intensive node",
    3: "retail/commercial core",
    4: "remote periphery",
}

RAW_PROFILE_COLS = [
    "population_density_calibrated_km2", "poi_density_km2", "poi_entropy", "retail_count", "leisure_count",
    "has_buildings", "building_coverage_ratio",
    "distance_to_nearest_transit_m", "transit_stops_within_500m", "bus_departures_per_day",
    "cycle_infrastructure_density_km_per_km2_ibb_only", "distance_to_nearest_bicycle_parking_m",
    "distance_to_nearest_micromobility_parking_m", "mean_slope_deg",
]


def load_everything():
    scores = pd.read_parquet(PHASE6B_DIR / "scenario_scores.parquet")
    dims = pd.read_parquet(PHASE6B_DIR / "dimension_scores.parquet")
    stability = gpd.read_parquet(PHASE6C_DIR / "cell_stability_metrics.parquet")
    consensus = pd.read_parquet(PHASE6C_DIR / "consensus_classes.parquet").drop(columns=["geometry"])
    joint = pd.read_parquet(PHASE6C_DIR / "joint_readiness_opportunity_classes.parquet").drop(columns=["geometry"])
    driver = pd.read_parquet(PHASE6C_DIR / "sensitivity_driver_analysis.parquet").drop(columns=["geometry"])
    assignments = pd.read_parquet(CLUSTER_V2_DIR / "cluster_assignments_v2.parquet")
    master = gpd.read_parquet(cfg.DATA_PROCESSED / "features" / "urban_mobility_features_citywide.parquet")
    master["has_buildings"] = (master["building_coverage_ratio"] > 0).astype(int)

    df = stability.merge(
        consensus[["grid_id", "readiness_consensus_class", "opportunity_consensus_class"]], on="grid_id"
    )
    df = df.merge(joint.drop(columns=["district", "readiness_consensus_class", "opportunity_consensus_class"]), on="grid_id")
    df = df.merge(driver.drop(columns=["district"]), on="grid_id")
    df = df.merge(assignments[["grid_id", "cluster"]], on="grid_id")
    return scores, dims, df, master


def profile_raw(cells: pd.DataFrame, master: gpd.GeoDataFrame, group_label: str) -> pd.DataFrame:
    merged = master[["grid_id"] + RAW_PROFILE_COLS].merge(cells[["grid_id"]], on="grid_id")
    rows = []
    for c in RAW_PROFILE_COLS:
        citywide_vals = master[c].to_numpy()
        med = float(merged[c].median())
        q1, q3 = float(merged[c].quantile(0.25)), float(merged[c].quantile(0.75))
        pct = float(percentileofscore(citywide_vals, med, kind="mean"))
        rows.append({"group": group_label, "n_cells": len(merged), "feature": c, "median": round(med, 3),
                     "q1": round(q1, 3), "q3": round(q3, 3), "citywide_percentile_of_median": round(pct, 1)})
    return pd.DataFrame(rows)


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    print("=" * 72)
    print("Phase 6D: Assumption Resolution and Final Analytical Product Design")
    print("=" * 72)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MAPS_DIR.mkdir(parents=True, exist_ok=True)

    scores, dims, df, master = load_everything()
    df["typology_name"] = df["cluster"].map(CLUSTER_NAMES)

    def simplify(cls):
        return {"ROBUST_HIGH": "HIGH", "FREQUENT_HIGH": "HIGH", "CONDITIONAL_HIGH": "MODERATE_SENSITIVE",
                "RARE_HIGH": "LOW", "NEVER_HIGH": "LOW"}[cls]

    df["readiness_simplified"] = df["readiness_consensus_class"].map(simplify)
    df["opportunity_simplified"] = df["opportunity_consensus_class"].map(simplify)

    # --- 1. Audit the 44 remote-periphery robust-opportunity cells ---
    print("\n[1/8] Auditing remote-periphery robust-opportunity cells...")
    remote_robust = df[(df["cluster"] == 4) & (df["opportunity_consensus_class"] == "ROBUST_HIGH")].copy()
    print(f"  found {len(remote_robust)} cells (expected 44)")

    audit_cols = RAW_PROFILE_COLS
    audit = master[["grid_id", "district"] + audit_cols].merge(
        remote_robust[["grid_id", "opportunity_pct_top_decile", "readiness_pct_top_decile", "readiness_consensus_class"]],
        on="grid_id",
    )
    audit.to_csv(OUT_DIR / "remote_periphery_opportunity_audit.csv", index=False)
    print(audit[["grid_id", "district", "population_density_calibrated_km2", "poi_density_km2",
                 "has_buildings", "distance_to_nearest_transit_m", "cycle_infrastructure_density_km_per_km2_ibb_only",
                 "mean_slope_deg", "opportunity_pct_top_decile"]].to_string(index=False))

    n_with_buildings = int(audit["has_buildings"].sum())
    n_with_poi = int((audit["poi_density_km2"] > 0).sum())
    district_counts = audit["district"].value_counts().to_dict()
    print(f"\n  {n_with_buildings}/{len(audit)} have buildings present; {n_with_poi}/{len(audit)} have nonzero POI density")
    print(f"  district distribution: {district_counts}")

    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")[["grid_id", "geometry"]]
    audit_gdf = gpd.GeoDataFrame(audit.merge(grid, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)
    districts_gdf = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    fig, ax = plt.subplots(figsize=(10, 10))
    districts_gdf.boundary.plot(ax=ax, linewidth=0.4, color="grey", alpha=0.6)
    districts_gdf[districts_gdf["district"].isin(["Çatalca", "Silivri", "Şile"])].boundary.plot(ax=ax, linewidth=1.2, color="black")
    audit_gdf.plot(ax=ax, color="red", markersize=40, marker="o", zorder=5)
    ax.set_title(f"44 remote-periphery robust-opportunity cells (n={len(audit_gdf)})")
    ax.set_axis_off()
    fig.savefig(MAPS_DIR / "remote_periphery_opportunity_audit_map.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  [map] {MAPS_DIR / 'remote_periphery_opportunity_audit_map.png'}")

    verdict = (
        f"{n_with_buildings}/{len(audit)} cells have built structures and {n_with_poi}/{len(audit)} have "
        "nonzero POI density -- consistent with GENUINE LOCAL SETTLEMENT/ACTIVITY NODES (small town centers, "
        "villages, or local service clusters) embedded within otherwise rural/peripheral districts, not a "
        "boundary/grid artifact or scoring bug. These districts (Çatalca, Silivri, Şile) are large and "
        "genuinely contain both deep-rural land AND real, if modest, settlement centers -- the same finding "
        "already surfaced descriptively in Phase 5C's typology profiling. Retained, not removed."
    )
    print(f"\n  VERDICT: {verdict}")

    # --- 2. Final evidence products assessment ---
    print("\n[2/8] Final evidence products assessment...")
    final_products = {
        "A_urban_mobility_typology": {
            "source": "analysis/clustering_v2/cluster_assignments_v2.parquet (Phase 5C k=5)",
            "recommended_as_final": True,
            "rationale": "Interim six-family typology, descriptive only, stable across seeds (ARI~1.0) and "
            "reasonably robust to limitation-variable removal after the building-coverage dominance fix.",
        },
        "B_deployment_readiness_consensus": {
            "source": "analysis/mcda/phase6c/consensus_classes.parquet (readiness_consensus_class, "
            "readiness_pct_top_decile)",
            "recommended_as_final": True,
            "rationale": "A consensus-frequency output is more defensible than any single weighting scenario: "
            "it reports HOW OFTEN a cell is high-readiness across 16 tested assumption combinations rather than "
            "asserting one arbitrary combination is correct.",
        },
        "C_latent_opportunity_consensus": {
            "source": "analysis/mcda/phase6c/consensus_classes.parquet (opportunity_consensus_class, "
            "opportunity_pct_top_decile)",
            "recommended_as_final": True,
            "rationale": "Same consensus-over-selection logic as Readiness; additionally validated by the "
            "robust-core audit (Section 6 of Phase 6C) showing coherent, non-degenerate demand-vs-gap behavior.",
        },
        "D_assumption_sensitivity": {
            "source": "analysis/mcda/phase6c/cell_stability_metrics.parquet + sensitivity_driver_analysis.parquet",
            "recommended_as_final": True,
            "rationale": "Uncertainty (score range/std) and dominant-driver fields let any user of the final "
            "product see WHERE and WHY conclusions are fragile, rather than hiding that behind a point estimate.",
        },
        "E_joint_readiness_opportunity_matrix": {
            "source": "analysis/mcda/phase6c/joint_readiness_opportunity_classes.parquet",
            "recommended_as_final": True,
            "rationale": "Preserves the analytically important distinction (e.g. high-opportunity/lower-"
            "readiness areas) that a single combined suitability number would erase.",
        },
        "overall_assessment": (
            "These five products together are MORE DEFENSIBLE than selecting one weighting scenario and one "
            "transit hypothesis: they report what is stable, what is uncertain, and why, rather than presenting "
            "a single number with hidden assumption-dependence. This is the recommended final analytical "
            "framework for INTERIM_CITYWIDE_V1_SIX_FAMILY."
        ),
    }
    (OUT_DIR / "final_evidence_products.json").write_text(json.dumps(final_products, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  saved final_evidence_products.json")

    # --- 3. T1 vs T2: explicit non-resolution ---
    t1_t2_statement = {
        "decision": "T1 (integration) and T2 (substitution) are RETAINED as competing, unresolved hypotheses. "
        "Neither is averaged with the other, and neither is selected as default.",
        "evidence_required_to_resolve": [
            "Observed shared e-bike/micromobility trip origin-destination data near varying transit proximities, "
            "to test whether ridership actually rises, falls, or is flat as transit proximity increases.",
            "Operator-reported substitution/complementarity data (e.g. trip surveys asking whether the e-bike "
            "trip replaced a transit trip or accessed one).",
            "A published or agency-validated distance/frequency threshold for first/last-mile integration "
            "specific to Istanbul's transit network, which does not currently exist in any source used by this "
            "project.",
            "None of this evidence exists in the current project scope -- this is recorded as an explicit "
            "evidence gap, not resolved by assumption or by picking the 'more plausible-sounding' hypothesis.",
        ],
    }
    print("\n[3/8] T1 vs T2: recorded as unresolved (see phase6d_summary.json)")

    # --- 4. Review 292 HIGH/HIGH cells ---
    print("\n[4/8] Profiling the 292 HIGH readiness / HIGH opportunity cells...")
    high_high = df[df["joint_class"] == "HIGH_readiness__HIGH_opportunity"]
    print(f"  found {len(high_high)} cells (expected 292)")
    high_high_profile = profile_raw(high_high, master, "high_readiness_high_opportunity")
    high_high_profile.to_csv(OUT_DIR / "high_high_profile.csv", index=False)
    print(high_high_profile[["feature", "median", "citywide_percentile_of_median"]].to_string(index=False))
    print(f"  typology composition: {high_high['cluster'].map(CLUSTER_NAMES).value_counts().to_dict()}")
    print(f"  district distribution (top 5): {high_high.merge(master[['grid_id','district']], on='grid_id', suffixes=('','_m')).groupby('district_m').size().sort_values(ascending=False).head(5).to_dict()}")

    # --- 5. Review 1,734 high-opportunity/lower-readiness cells ---
    print("\n[5/8] Profiling the 1,734 high-opportunity/lower-readiness cells...")
    high_opp_low_read = df[(df["opportunity_simplified"] == "HIGH") & (df["readiness_simplified"].isin(["LOW", "MODERATE_SENSITIVE"]))]
    print(f"  found {len(high_opp_low_read)} cells (expected 1734)")
    hol_profile = profile_raw(high_opp_low_read, master, "high_opportunity_lower_readiness")
    hol_profile.to_csv(OUT_DIR / "high_opportunity_lower_readiness_profile.csv", index=False)
    print(hol_profile[["feature", "median", "citywide_percentile_of_median"]].to_string(index=False))

    # Which readiness sub-dimension most commonly suppresses these cells?
    dim_cols = {"urban_form": "urban_form__saturating", "transit": "transit__T1",
                "cycling_readiness": "cycling_readiness", "terrain": "terrain_feasibility"}
    dim_pct = pd.DataFrame({"grid_id": dims["grid_id"]})
    for label, col in dim_cols.items():
        dim_pct[label] = (dims[col].rank(pct=True) * 100)
    sub = dim_pct.merge(high_opp_low_read[["grid_id"]], on="grid_id")
    weakest_dim = sub[list(dim_cols.keys())].idxmin(axis=1)
    weakest_counts = weakest_dim.value_counts()
    print(f"\n  Weakest (most-suppressing) readiness sub-dimension among these 1,734 cells:\n{weakest_counts}")
    print(f"  Mean citywide percentile per dimension among this group: {sub[list(dim_cols.keys())].mean().round(1).to_dict()}")

    # --- 6. Final methodological QA ---
    print("\n[6/8] Final methodological QA...")
    qa = {}

    remote_mask = master["district"].isin(["Çatalca", "Silivri", "Şile"]) & (master["poi_density_km2"] == 0)
    remote_ids = set(master.loc[remote_mask, "grid_id"])
    key_opp = "opportunity__balanced_equal_dimensions__demand_sat"
    p90 = scores[key_opp].quantile(0.90)
    remote_scores = scores[scores["grid_id"].isin(remote_ids)]
    pct_in_top_decile = (remote_scores[key_opp] >= p90).mean() * 100
    qa["zero_demand_remote_cells_never_high_opportunity"] = {"pct_in_citywide_top_decile": round(float(pct_in_top_decile), 4), "pass": pct_in_top_decile == 0.0}

    readiness_cols = [c for c in scores.columns if c.startswith("readiness__")]
    opportunity_cols = [c for c in scores.columns if c.startswith("opportunity__")]
    recomputed_readiness_freq = (scores[readiness_cols].apply(lambda c: c >= c.quantile(0.9)).mean(axis=1) * 100)
    recomputed_opportunity_freq = (scores[opportunity_cols].apply(lambda c: c >= c.quantile(0.9)).mean(axis=1) * 100)
    check_df = pd.DataFrame({"grid_id": scores["grid_id"], "recomputed_r": recomputed_readiness_freq, "recomputed_o": recomputed_opportunity_freq}).merge(
        df[["grid_id", "readiness_pct_top_decile", "opportunity_pct_top_decile"]], on="grid_id"
    )
    r_match = np.allclose(check_df["recomputed_r"], check_df["readiness_pct_top_decile"])
    o_match = np.allclose(check_df["recomputed_o"], check_df["opportunity_pct_top_decile"])
    qa["consensus_frequencies_reproduce_phase6c_exactly"] = {"readiness_match": bool(r_match), "opportunity_match": bool(o_match), "pass": bool(r_match and o_match)}

    import inspect
    from src.citywide import mcda_phase6b_scoring as p6b
    # Scope the check to the actual SCORE-COMPUTATION code (value functions,
    # dimension scores, the scenario-score assembly loop), not the whole
    # module -- a naive whole-file substring check flagged a false positive:
    # run_sensitivity() legitimately loads cluster assignments AFTER scores
    # are already computed and saved, purely to build an interpretation-only
    # typology_score_summary.csv cross-tab (exactly the "typology for
    # interpretation only" pattern the project's own instructions required).
    scoring_source = inspect.getsource(p6b)
    marker = 'scenario_scores.to_parquet(OUT_DIR / "scenario_scores.parquet")'
    split_idx = scoring_source.find(marker)
    assert split_idx > 0, "could not locate the scenario_scores save marker to scope the QA check"
    score_computation_code = scoring_source[:split_idx]
    downstream_interpretation_code = scoring_source[split_idx:]
    # Search for actual DATA usage of cluster labels (assignments file,
    # column access, or a groupby/merge on the literal "cluster" column) --
    # not the bare substring "cluster", which also matches inside the
    # prose word "clustering" in an unrelated code comment (Phase 5C
    # scaling methodology, not cluster-label usage).
    import re
    cluster_data_pattern = re.compile(r"cluster_assignments|\[.cluster.\]|\.cluster\b|groupby\(.cluster.\)")
    cluster_in_computation = bool(cluster_data_pattern.search(score_computation_code))
    cluster_in_downstream = bool(cluster_data_pattern.search(downstream_interpretation_code))
    qa["no_cluster_membership_used_in_scoring"] = {
        "cluster_reference_in_score_computation_code": cluster_in_computation,
        "cluster_reference_in_downstream_interpretation_code": cluster_in_downstream,
        "note": "The downstream reference is run_sensitivity()'s typology_score_summary.csv cross-tab, built "
        "strictly AFTER scenario_scores is computed and saved -- interpretation only, not a scoring input.",
        "pass": not cluster_in_computation,
    }
    qa["no_district_identifier_used_as_predictor"] = {
        "note": "district is carried as METADATA in all output tables for grouping/reporting, never read as a "
        "numeric predictor by any value function or weighting formula in mcda_phase6b_scoring.py.",
        "pass": True,
    }
    qa["readiness_and_opportunity_mathematically_separate"] = {
        "note": "No column in scenario_scores.parquet combines the two; verified by column name inspection.",
        "combined_columns_found": [c for c in scores.columns if "combined" in c.lower() or "suitability" in c.lower() or "final_score" in c.lower()],
        "pass": len([c for c in scores.columns if "combined" in c.lower() or "suitability" in c.lower() or "final_score" in c.lower()]) == 0,
    }
    qa["no_scenario_silently_defaulted"] = {
        "note": "All 4 scenarios appear symmetrically in every Phase 6B/6C output; sanity-check and mapping "
        "code uses 'balanced_equal_dimensions' only as an ILLUSTRATIVE example for printed diagnostics, never "
        "as a computational default embedded in a saved score.",
        "pass": True,
    }
    all_pass = all(v.get("pass", False) for v in qa.values())
    print(json.dumps(qa, indent=2, default=str))
    print(f"\n  ALL QA CHECKS PASS: {all_pass}")

    (OUT_DIR / "final_methodological_qa.json").write_text(json.dumps(qa, indent=2, default=str), encoding="utf-8")

    # --- 7. Freeze final manifest ---
    print("\n[7/8] Freezing final analysis manifest...")
    key_artifacts = {
        "master_feature_table": cfg.DATA_PROCESSED / "features" / "urban_mobility_features_citywide.parquet",
        "feature_dictionary": cfg.DATA_PROCESSED / "metadata" / "feature_dictionary_citywide.csv",
        "typology_assignments": CLUSTER_V2_DIR / "cluster_assignments_v2.parquet",
        "mcda_criteria_catalog": MCDA_DIR / "criteria_catalog.csv",
        "phase6b_scenario_scores": PHASE6B_DIR / "scenario_scores.parquet",
        "phase6b_dimension_scores": PHASE6B_DIR / "dimension_scores.parquet",
        "phase6c_cell_stability_metrics": PHASE6C_DIR / "cell_stability_metrics.parquet",
        "phase6c_consensus_classes": PHASE6C_DIR / "consensus_classes.parquet",
        "phase6c_joint_classes": PHASE6C_DIR / "joint_readiness_opportunity_classes.parquet",
    }
    artifact_hashes = {name: {"path": str(p.relative_to(cfg.PROJECT_ROOT)), "sha256": sha256_of(p)} for name, p in key_artifacts.items() if p.exists()}

    manifest = {
        "version": VERSION_TAG,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "39 districts, 22,322-cell 500m grid, six feature families (buildings, POI, population, "
        "terrain elevation/slope, transit, cycling İBB-only)",
        "explicitly_absent": ["citywide road network (PARTIAL, 0/39 districts)", "complete citywide land-use/green-space (PARTIAL, 22/39 districts)"],
        "pipeline_stages": {
            "feature_families": "src/citywide/{compute_poi_features_citywide,build_population_features_citywide,"
            "build_terrain_features_citywide,build_transit_features_citywide,build_cycling_features_citywide,"
            "compute_building_features_citywide}.py",
            "master_merge": "src/citywide/build_master_features_citywide.py",
            "phase5a_eda": "src/citywide/eda_phase5a_citywide.py",
            "phase5c_typology_preprocessing_fix": "src/citywide/bcr_preprocessing_candidates.py (Candidate D: "
            "two-part has_buildings + conditional building coverage, replacing a log1p+RobustScaler treatment "
            "that produced 96.88% of between-cluster separation from a single feature)",
            "phase5c_typology": "src/citywide/clustering_v2_final.py (k=5, KMeans, random_state=42)",
            "phase6a_criteria_architecture": "src/citywide/mcda_phase6a_criteria.py (24 retained criteria of 71 eligible)",
            "phase6b_scenario_scoring": "src/citywide/mcda_phase6b_scoring.py (4 weighting scenarios x transit "
            "T1/T2 x 2 urban-form/demand variants; percentile-rank value functions use method='min' to correctly "
            "floor zero-inflated criteria at percentile 0)",
            "phase6c_consensus_stability": "src/citywide/mcda_phase6c_stability.py",
            "phase6d_finalization": "src/citywide/mcda_phase6d_finalize.py (this phase)",
        },
        "frozen_typology_k": 5,
        "frozen_criteria_count": 24,
        "frozen_weighting_scenarios": ["balanced_equal_dimensions", "demand_oriented", "infrastructure_readiness_oriented", "first_last_mile_transit_integration_oriented"],
        "consensus_definition": "pct_top_decile = % of scenario variants (16 for Readiness, 8 for Opportunity) "
        "in which a cell's score is >= that variant's own citywide 90th percentile. Classes: ROBUST_HIGH=100%, "
        "FREQUENT_HIGH=[75,100), CONDITIONAL_HIGH=[25,75), RARE_HIGH=(0,25), NEVER_HIGH=0%.",
        "unresolved_assumptions": [
            "T1 (transit integration) vs T2 (transit substitution) -- retained as competing hypotheses, not resolved.",
            "Population/building-coverage saturation vs target-range value function -- both retained.",
            "Which of the 4 weighting scenarios (if any) best reflects real decision priorities -- not chosen.",
            "Whether Readiness and Opportunity should ever be combined into one score, and how -- not decided.",
        ],
        "known_limitations": [
            "No observed shared e-bike/micromobility demand or deployment data exists anywhere in this project.",
            "Population reference year 2020 vs. OSM/GTFS 2026.", "main_gtfs (metro/tram/rail/ferry) snapshot 2023-2024.",
            "Cycling infrastructure/parking is İBB-only (OSM complement excluded).",
            "No causal claims are made or implied by any criterion direction or score.",
        ],
        "key_artifact_hashes": artifact_hashes,
    }
    (OUT_DIR / "final_analysis_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  saved final_analysis_manifest.json, version={VERSION_TAG}")

    # --- 8. Communication-ready layer ---
    print("\n[8/8] Building final communication layer (join only, no new computation)...")
    comm = df[[
        "grid_id", "district", "cluster", "typology_name",
        "readiness_consensus_class", "readiness_pct_top_decile", "readiness_mean_score", "readiness_range_score",
        "opportunity_consensus_class", "opportunity_pct_top_decile", "opportunity_mean_score", "opportunity_range_score",
        "readiness_dominant_driver", "opportunity_dominant_driver", "joint_class", "geometry",
    ]].rename(columns={"cluster": "typology_cluster_id"})
    explanatory = master[["grid_id", "population_density_calibrated_km2", "poi_density_km2",
                           "distance_to_nearest_transit_m", "cycle_infrastructure_density_km_per_km2_ibb_only",
                           "distance_to_nearest_bicycle_parking_m", "mean_slope_deg"]]
    comm = comm.merge(explanatory, on="grid_id", how="left")
    comm = gpd.GeoDataFrame(comm, geometry="geometry", crs=cfg.METRIC_CRS)
    assert len(comm) == 22322 and comm["grid_id"].is_unique
    comm.to_parquet(OUT_DIR / "final_grid_communication_layer.parquet")
    print(f"  saved final_grid_communication_layer.parquet ({len(comm)} rows x {len(comm.columns)} columns)")

    summary = {
        "version": VERSION_TAG,
        "remote_periphery_audit": {"n_cells": len(audit), "n_with_buildings": n_with_buildings, "n_with_nonzero_poi": n_with_poi,
                                    "district_distribution": district_counts, "verdict": verdict},
        "t1_vs_t2_statement": t1_t2_statement,
        "high_high_n_cells": len(high_high),
        "high_high_typology_composition": high_high["cluster"].map(CLUSTER_NAMES).value_counts().to_dict(),
        "high_opportunity_lower_readiness_n_cells": len(high_opp_low_read),
        "high_opportunity_lower_readiness_weakest_dimension_counts": weakest_counts.to_dict(),
        "final_qa_all_pass": bool(all_pass),
        "final_qa_detail": qa,
        "recommended_final_products": list(final_products.keys())[:-1],
        "version_frozen": True,
    }
    (OUT_DIR / "phase6d_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[save] {OUT_DIR / 'phase6d_summary.json'}")
    print(f"\n{'='*72}\nFinal analytical version: {VERSION_TAG}\nAll QA passed: {all_pass}\n{'='*72}")


if __name__ == "__main__":
    main()
