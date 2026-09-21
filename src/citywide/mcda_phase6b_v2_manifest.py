"""Phase 6B-V2: final manifest + summary. Consolidates all prior step
outputs; performs no new scoring computation, only hashing and assembly.
"""

from __future__ import annotations

import hashlib
import json

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.mcda_phase6b_v2_scoring import (
    BASELINE_DIMENSION_WEIGHTS, TERRAIN_WEIGHTS_NO_GRADE, TERRAIN_WEIGHTS_WITH_GRADE,
)
from src.citywide.mcda_phase6b_v2_sensitivity import WEIGHT_PERTURBATION_VECTOR
from src.utils import config as cfg

FEATURES_DIR = cfg.DATA_FEATURES
OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda_v2" / "phase6b"
VERSION_TAG = "EBIKE_APPLICATION_V2_BASELINE"

KEY_INPUTS = {
    "v2_master_feature_table": FEATURES_DIR / "urban_mobility_features_citywide_v2.parquet",
    "v2_feature_dictionary": cfg.DATA_PROCESSED / "metadata" / "feature_dictionary_citywide_v2.csv",
    "v2_typology_assignments": cfg.PROJECT_ROOT / "analysis" / "clustering_v2_eight_family" / "cluster_assignments_v2ef.parquet",
    "phase6a_v2_criteria_audit": cfg.PROJECT_ROOT / "analysis" / "mcda_v2" / "criteria_catalog_v2_audit.csv",
}


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(name):
    return json.loads((OUT_DIR / name).read_text(encoding="utf-8"))


def main() -> None:
    baseline_meta = load("baseline_scoring_meta.json")
    sensitivity_meta = load("sensitivity_meta.json")
    robustness_summary = load("robustness_summary.json")
    pathological_qa = load("pathological_case_qa.json")
    v1_v2_comparison = load("v1_v2_ebike_comparison.json")
    typology_summary = load("typology_posthoc_summary.json")

    manifest = {
        "version": VERSION_TAG,
        "generated_at_utc": "2026-09-19T23:00:00Z",
        "framework_context": "First application ('applications/ebike/' conceptually) built on the "
        "CITYWIDE_V2_EIGHT_FAMILY_FEATURE_BASELINE / CITYWIDE_V2_EIGHT_FAMILY_TYPOLOGY core data foundation. "
        "No new datasets, predictors, or typology changes were introduced in this phase.",
        "input_hashes": {name: {"path": str(p.relative_to(cfg.PROJECT_ROOT)), "sha256": sha256_of(p)} for name, p in KEY_INPUTS.items()},
        "conceptual_model": {
            "dimensions": list(BASELINE_DIMENSION_WEIGHTS.keys()),
            "dimension_weights_baseline": BASELINE_DIMENSION_WEIGHTS,
            "urban_form_dimension_deliberately_excluded": True,
            "readiness_definition": "Existing enabling urban/mobility conditions -- renormalized weighted mean of "
                                    "{Transit Accessibility, Cycling Readiness, Street Connectivity, Physical "
                                    "Feasibility}. Demand/Activity excluded.",
            "opportunity_definition": "demand_potential ** alpha * cycling_gap ** (1-alpha); alpha=0.5 at baseline "
                                      "(unchanged geometric form from V1); zero demand forces zero opportunity "
                                      "regardless of gap size.",
            "readiness_and_opportunity_never_combined": True,
            "typology_never_used_as_predictor": True,
        },
        "baseline_criteria": {
            "Demand/Activity": ["poi_density_km2", "poi_entropy", "retail_count", "leisure_count", "population_density_calibrated_km2"],
            "Transit Accessibility (REDUCED)": ["distance_to_nearest_transit_m", "transit_stops_within_500m", "bus_departures_per_day", "fixed_guideway_stations_within_1000m"],
            "Cycling Readiness (unchanged from V1)": ["cycle_infrastructure_density_km_per_km2_ibb_only", "protected_cycleway_density_km_per_km2_ibb_only", "distance_to_nearest_cycle_infrastructure_m_ibb_only", "distance_to_nearest_bicycle_parking_m", "distance_to_nearest_micromobility_parking_m"],
            "Street Connectivity (NEW)": ["intersection_density_km2", "local_road_length_m", "cycle_accessible_road_density_km_per_km2"],
            "Physical Feasibility (supplemented)": ["mean_slope_deg", "pct_area_slope_3_6deg", "pct_area_slope_6_10deg", "mean_absolute_road_grade_pct"],
        },
        "excluded_no_score": ["residential_area_ratio (and its three-state derivative)", "industrial_area_ratio (and its three-state derivative)",
                               "landuse_has_mapped_evidence", "green_area_ratio", "major_road_length_m", "road_density_km_per_km2",
                               "pct_road_length_grade_gt_8pct (secondary/sensitivity-only)",
                               "5 mode-specific transit distances (sensitivity-only)",
                               "pct_road_network_with_cycle_infrastructure (sensitivity-only)"],
        "terrain_weights": {"with_grade_baseline": TERRAIN_WEIGHTS_WITH_GRADE, "no_grade_sensitivity": TERRAIN_WEIGHTS_NO_GRADE},
        "sensitivity_variants": sensitivity_meta,
        "weight_perturbation_vector": WEIGHT_PERTURBATION_VECTOR,
        "robustness_summary": {
            "readiness_consensus_class_counts": robustness_summary["readiness_consensus_class_counts"],
            "opportunity_consensus_class_counts": robustness_summary["opportunity_consensus_class_counts"],
            "readiness_min_pairwise_spearman": robustness_summary["readiness_min_pairwise_spearman"],
            "opportunity_min_pairwise_spearman": robustness_summary["opportunity_min_pairwise_spearman"],
        },
        "pathological_case_qa_critical_check": pathological_qa["critical_check_remote_zero_demand_not_dominating_opportunity"],
        "v1_v2_comparison_headline": {
            "spearman_rho_readiness": v1_v2_comparison["spearman_rho_readiness"],
            "spearman_rho_opportunity": v1_v2_comparison["spearman_rho_opportunity"],
            "jaccard_top_decile_readiness": v1_v2_comparison["jaccard_top_decile_readiness"],
            "jaccard_top_decile_opportunity": v1_v2_comparison["jaccard_top_decile_opportunity"],
        },
        "assumptions_flagged_for_future_sensitivity": [
            "Grade thresholds (comfortable<=3%, floor by 10%) are REUSED from the pilot's raster-slope convention, "
            "not independently derived for road-anchored grade -- an assumption, not an empirical estimate.",
            "Terrain internal weights (0.40/0.30/0.20/0.10) are assumption-driven; no optimization was performed.",
            "Saturating-benefit shape (percentile_rank**0.5) for Street Connectivity and most other benefit "
            "criteria is a functional-form assumption, not an estimated behavioral response curve.",
            "The single WEIGHT_PERTURBATION vector tested is illustrative (one deterministic +/-20% tilt), not an "
            "exhaustive robustness search.",
            "Opportunity's V1-vs-V2 correlation is exactly 1.0 because none of its actual inputs (demand criteria, "
            "cycling criteria) changed between versions at alpha=0.5 in both -- this is an expected consistency "
            "result, not independent validation of the Opportunity construct itself.",
        ],
        "known_limitations_carried_forward": [
            "main_gtfs (metro/tram/rail/ferry) feed is static/topology-only, last modified 2023-2024, calendar "
            "expired -- station LOCATIONS used in distance/count criteria may not reflect post-2024 network "
            "changes; no ground truth was available to test this directly (documented, not corrected).",
            "OSM land-use tagging sparsity (~9.2% mean coverage) is why land-use composition and green-space "
            "area were excluded from or handled cautiously in scoring, per Phase 6A-V2.",
        ],
        "typology_posthoc": typology_summary,
        "output_paths": {
            "ebike_readiness_baseline": str(OUT_DIR / "ebike_readiness_baseline.parquet"),
            "ebike_opportunity_baseline": str(OUT_DIR / "ebike_opportunity_baseline.parquet"),
            "ebike_dimension_scores": str(OUT_DIR / "ebike_dimension_scores.parquet"),
            "sensitivity_variant_scores": str(OUT_DIR / "sensitivity_variant_scores.parquet"),
            "readiness_robustness": str(OUT_DIR / "readiness_robustness.parquet"),
            "opportunity_robustness": str(OUT_DIR / "opportunity_robustness.parquet"),
            "consensus_classes": str(OUT_DIR / "consensus_classes.parquet"),
            "sensitivity_summary": str(OUT_DIR / "sensitivity_summary.csv"),
            "pathological_case_qa": str(OUT_DIR / "pathological_case_qa.json"),
            "v1_v2_ebike_comparison": str(OUT_DIR / "v1_v2_ebike_comparison.json"),
            "typology_posthoc_summary": str(OUT_DIR / "typology_posthoc_summary.json"),
            "criterion_value_functions": str(OUT_DIR / "criterion_value_functions_v2.csv"),
        },
        "stop_condition": "STOPPED after validation and reporting -- no 15-minute-city analysis, isochrones, new "
                          "feature engineering, dashboards, new data acquisition, predictive ML, or cartographic "
                          "styling were performed.",
    }

    out_path = OUT_DIR / "phase6b_v2_manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {out_path}")

    summary = {
        "version": VERSION_TAG,
        "readiness_stats": baseline_meta["readiness_stats"],
        "opportunity_stats": baseline_meta["opportunity_stats"],
        "strongest_sensitivity_driver_readiness": sensitivity_meta["strongest_sensitivity_driver_readiness"]["variant"],
        "strongest_sensitivity_driver_opportunity": sensitivity_meta["strongest_sensitivity_driver_opportunity"]["variant"],
        "n_robust_high_readiness": robustness_summary["readiness_consensus_class_counts"].get("ROBUST_HIGH", 0),
        "n_robust_high_opportunity": robustness_summary["opportunity_consensus_class_counts"].get("ROBUST_HIGH", 0),
        "critical_pathological_check_passed": pathological_qa["critical_check_remote_zero_demand_not_dominating_opportunity"]["passed"],
        "v1_v2_readiness_correlation": v1_v2_comparison["spearman_rho_readiness"],
        "v1_v2_opportunity_correlation": v1_v2_comparison["spearman_rho_opportunity"],
    }
    (OUT_DIR / "phase6b_v2_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[save] {OUT_DIR / 'phase6b_v2_summary.json'}")


if __name__ == "__main__":
    main()
