"""Phase 12, Sections 14 + 17-19: district-profile data structure,
dashboard information architecture (8 pages), shared filter spec, and
chart registry. Specification/aggregation over already-frozen fields --
no new analytical computation.
"""

from __future__ import annotations

import json

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

ROOT = cfg.PROJECT_ROOT
OUT_DIR = ROOT / "analysis" / "framework_synthesis"
DASH_DIR = OUT_DIR / "dashboard"
REG_DIR = OUT_DIR / "registries"


def main() -> None:
    print("=" * 72)
    print("Phase 12 Sections 14, 17-19: district profiles, dashboard IA, filters, charts")
    print("=" * 72)

    print("\n[Section 14] District profile data structure...")
    df = pd.read_parquet(DASH_DIR / "dashboard_grid.parquet")
    profiles = []
    for dist, g in df.groupby("district"):
        pop_total = float(g["calibrated_population_2020"].sum())
        typ_comp = (g.groupby("typology_cluster")["calibrated_population_2020"].sum() / pop_total * 100).round(2).to_dict() if pop_total else {}
        walk_gap_counts = g.loc[g["everyday_gap_type"] != "NO_REQUIRED_GAP", "everyday_gap_type"].value_counts().head(3).to_dict()
        closure_counts = g["cycling_gap_closure"].value_counts().to_dict()
        transit_quality = g["transit_data_quality"].mode()
        transit_quality_val = transit_quality.iloc[0] if len(transit_quality) else None
        transit_reliable_pop = float(g.loc[g["transit_data_quality"] == "GOOD_COVERAGE", "calibrated_population_2020"].sum())
        profiles.append({
            "district": dist, "n_cells": len(g), "population_total": round(pop_total, 1),
            "typology_composition_pct_population": json.dumps({str(k): v for k, v in typ_comp.items()}),
            "population_complete_walk_15": round(float(g.loc[g["complete_walk_15"] == True, "calibrated_population_2020"].sum()), 1),
            "common_everyday_gap_types": json.dumps(walk_gap_counts),
            "population_cycling_closes_everyday_gap": round(float(g.loc[g["active_mobility_intervention"].isin(
                ["CYCLING_CLOSES_EVERYDAY_GAP", "CYCLING_CLOSES_BOTH"]), "calibrated_population_2020"].sum()), 1),
            "common_cycling_closure_types": json.dumps(closure_counts),
            "transit_data_quality_class": transit_quality_val,
            "population_in_good_transit_coverage_cells": round(transit_reliable_pop, 1),
            "ebike_readiness_mean": round(float(g["ebike_readiness"].mean()), 4),
            "ebike_opportunity_mean": round(float(g["ebike_opportunity"].mean()), 4),
            "pct_cells_walking_quality_reliable": round(float(g["walking_quality"].isin(["RELIABLE", "RELIABLE_SEPARATE_COMPONENT"]).mean() * 100), 2),
            "pct_cells_cycling_quality_reliable": round(float(g["cycling_quality"].isin(["RELIABLE", "RELIABLE_SEPARATE_COMPONENT"]).mean() * 100), 2),
        })
    profiles_df = pd.DataFrame(profiles).sort_values("district")
    profiles_df.to_parquet(OUT_DIR / "district_profiles.parquet")
    print(f"  {len(profiles_df)} district profiles built (explicitly NOT ranked -- alphabetical order only)")
    print(f"[save] {OUT_DIR / 'district_profiles.parquet'}")

    print("\n[Section 17] Dashboard information architecture (8 pages)...")
    pages = [
        {"page_id": "01_OVERVIEW", "title": "Overview",
         "user_question": "What is this framework and what are its headline findings?",
         "headline_kpis": ["WALK_02 (82.49% complete walking access)", "CYC_01 (95.6% complete cycling access)", "GAP_02 (2.10M cycling closure)"],
         "main_map": "MAP_01 (Urban Mobility Typology)", "secondary_charts": ["population_access_5_10_15", "walking_vs_cycling_population"],
         "filters": ["District", "Urban typology"], "tooltip_content": "grid_id, district, population, typology",
         "methodological_warning": "All figures are modeled network accessibility, not observed travel behavior."},
        {"page_id": "02_URBAN_TYPOLOGY", "title": "Urban Typology",
         "user_question": "What kind of urban environments exist across Istanbul?",
         "headline_kpis": ["URB_03 (typology)"], "main_map": "MAP_01", "secondary_charts": ["accessibility_by_typology"],
         "filters": ["District", "Urban typology"], "tooltip_content": "typology_cluster, population, population_density",
         "methodological_warning": "Typology is descriptive, not causal, and never entered any routing/accessibility computation."},
        {"page_id": "03_15MIN_ISTANBUL", "title": "15-Minute Istanbul",
         "user_question": "What everyday needs can residents potentially reach by walking?",
         "headline_kpis": ["WALK_01", "WALK_02"], "main_map": "MAP_02", "secondary_charts": ["population_access_5_10_15", "gap_composition"],
         "filters": ["District", "Required service", "Time threshold", "Quality level"], "tooltip_content": "See MAP_02 spec",
         "methodological_warning": "NaN nearest-time means unreachable within the 15-minute search horizon, not 'very far'. Do not call this 'living in a 15-minute city'."},
        {"page_id": "04_CYCLING_GAIN", "title": "Cycling Gain",
         "user_question": "Where does cycling materially expand accessibility compared with walking?",
         "headline_kpis": ["CYC_01", "CYC_02", "GAP_02"], "main_map": "MAP_05", "secondary_charts": ["walking_vs_cycling_population", "cycling_closure_composition"],
         "filters": ["District", "Urban typology", "Accessibility-gap type", "Cycling closure type", "Quality level"],
         "tooltip_content": "See MAP_05 spec", "methodological_warning": "Modeled potential at a constant 15km/h baseline speed; not validated mode-choice or observed behavior."},
        {"page_id": "05_TRANSIT_CONNECTION", "title": "Transit Connection",
         "user_question": "Where can cycling expand access to public transport?",
         "headline_kpis": ["TR_05"], "main_map": "MAP_06 / MAP_07 (toggle General vs Fixed-Guideway)",
         "secondary_charts": ["transit_catchment_gain"], "filters": ["District", "Transit system", "Time threshold", "Quality level"],
         "tooltip_content": "See MAP_06/07 spec", "methodological_warning": "NO_FEED_COVERAGE != NO_TRANSIT_SERVICE. Use QUALITY-AWARE figures for any citywide claim."},
        {"page_id": "06_ACCESSIBILITY_GAPS", "title": "Accessibility Gaps",
         "user_question": "Where do mapped accessibility gaps remain, and how many people are associated with them?",
         "headline_kpis": ["GAP_01", "H06", "H07"], "main_map": "MAP_08", "secondary_charts": ["gap_composition", "district_profile_composition"],
         "filters": ["District", "Accessibility-gap type", "Cycling closure type", "Quality level"], "tooltip_content": "See MAP_08 spec",
         "methodological_warning": "Use neutral 'accessibility gap' language only -- never 'service desert', 'mobility poverty', or 'underserved community'."},
        {"page_id": "07_EBIKE", "title": "E-bike",
         "user_question": "Where is e-bike deployment potential highest, and does it align with measured accessibility gains?",
         "headline_kpis": ["EBK_01", "EBK_02", "H08"], "main_map": "MAP_09 / MAP_10 (toggle) + MAP_11 (convergence)",
         "secondary_charts": ["ebike_convergence_matrix"], "filters": ["District", "E-bike class", "Urban typology"],
         "tooltip_content": "See MAP_09/10/11 spec", "methodological_warning": "Cross-application convergence is descriptive co-location, NOT validation of either application."},
        {"page_id": "08_DATA_METHODS", "title": "Data & Methods",
         "user_question": "How was this built, what are its sources, and where should results not be over-interpreted?",
         "headline_kpis": [], "main_map": "MAP_12 (Data/Network Confidence)", "secondary_charts": [],
         "filters": ["Quality level"], "tooltip_content": "See MAP_12 spec",
         "methodological_warning": "This page hosts the full methodology_registry and claims_registry -- the authoritative source for all interpretation limits."},
    ]
    (DASH_DIR / "dashboard_information_architecture.json").write_text(
        json.dumps({"pages": pages, "design_principle": "Question-driven, not feature-driven. The user never needs "
                    "to know which internal 'Phase' produced a page's data."}, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"  {len(pages)} pages specified")
    print(f"[save] {DASH_DIR / 'dashboard_information_architecture.json'}")

    print("\n[Section 18] Shared filter specification...")
    filters = {
        "District": {"applies_to_pages": ["01", "02", "03", "04", "05", "06", "07"], "values_source": "dashboard_grid.district (39 districts)"},
        "Urban typology": {"applies_to_pages": ["01", "02", "04", "07"], "values_source": "dashboard_grid.typology_cluster (0-4)"},
        "Mode": {"applies_to_pages": ["03", "04", "05"], "values": ["Walking", "Cycling"]},
        "Time threshold": {"applies_to_pages": ["03", "05"], "values": ["5 min", "10 min", "15 min"]},
        "Required service": {"applies_to_pages": ["03"], "values": ["Food", "Healthcare", "Education"]},
        "Accessibility-gap type": {"applies_to_pages": ["04", "06"], "values_source": "dashboard_grid.everyday_gap_type (9 classes)"},
        "Cycling closure type": {"applies_to_pages": ["04", "06"], "values_source": "dashboard_grid.cycling_gap_closure (5 classes)"},
        "Transit system": {"applies_to_pages": ["05"], "values": ["General Transit", "Fixed-Guideway/High-Capacity"]},
        "E-bike class": {"applies_to_pages": ["07"], "values_source": "ebike_readiness_robustness / ebike_opportunity_robustness (5 classes each)"},
        "Quality level": {"applies_to_pages": ["03", "04", "05", "06", "08"], "values": ["HIGH_CONFIDENCE", "NETWORK_LIMITATION", "TRANSIT_DATA_LIMITATION", "MULTIPLE_LIMITATIONS"]},
        "not_created": ["a universal 'score' filter (no composite score exists)", "a 'priority' filter (no priority ranking exists)"],
    }
    (DASH_DIR / "dashboard_filter_spec.json").write_text(json.dumps(filters, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  {len(filters)-1} filters specified")
    print(f"[save] {DASH_DIR / 'dashboard_filter_spec.json'}")

    print("\n[Section 19] Chart registry...")
    charts = [
        dict(chart_id="CHART_01", title="Population Access at 5/10/15 Minutes", question="How does population accessibility grow with search time?",
             data_source="analysis/applications/first_last_mile_transit/accessibility_gain_5_10_15.csv (pattern) + 15min_city/validation/accessibility_growth_5_10_15.csv",
             x_dimension="threshold_min (5/10/15)", y_dimension="pct_population_accessible", aggregation="population-weighted, per required category + complete access",
             population_weighted_or_cell_based="population-weighted", quality_mask="RELIABLE cells recommended for headline framing",
             interpretation_warning="Growth curve is smooth (validated in Phase 8.1) -- no artificial cliff at 15min."),
        dict(chart_id="CHART_02", title="Walking vs Cycling Population Accessibility", question="How much does cycling expand accessibility relative to walking?",
             data_source="analysis/applications/cycling_accessibility/accessibility_gain_5_10_15.csv",
             x_dimension="threshold_min", y_dimension="walking_pct_population vs cycling_pct_population", aggregation="population-weighted, per required category + complete access",
             population_weighted_or_cell_based="population-weighted", quality_mask="None applied in the frozen source (RAW); quality-aware variant available.",
             interpretation_warning="Modeled potential, not observed mode shift."),
        dict(chart_id="CHART_03", title="Everyday-Needs Gap Composition", question="What type of accessibility gap is most common, and for how many people?",
             data_source="analysis/applications/accessibility_gap_intelligence/everyday_needs_gap_summary.csv",
             x_dimension="everyday_gap_class", y_dimension="population", aggregation="sum",
             population_weighted_or_cell_based="population", quality_mask="UNKNOWN_OR_QUALITY_LIMITED shown as its own bar, not excluded.",
             interpretation_warning="Neutral 'accessibility gap' language only."),
        dict(chart_id="CHART_04", title="Cycling Closure Composition", question="Of cells with a walking gap, how much does cycling close?",
             data_source="analysis/applications/accessibility_gap_intelligence/cycling_gap_closure_summary.csv",
             x_dimension="closure_status", y_dimension="population", aggregation="sum",
             population_weighted_or_cell_based="population", quality_mask="CYCLING_RESULT_UNCERTAIN shown as its own bar.",
             interpretation_warning="Descriptive network measurement, not a behavioral prediction."),
        dict(chart_id="CHART_05", title="Accessibility by Urban Typology", question="Do different urban regimes show different accessibility profiles?",
             data_source="analysis/applications/accessibility_gap_intelligence/typology_accessibility_gap_summary.csv",
             x_dimension="cluster", y_dimension="pct_everyday_* / pct_transit_* / pct_intervention_* (selectable)", aggregation="share within cluster",
             population_weighted_or_cell_based="cell-based (share of cluster's cells)", quality_mask="Cluster composition includes uncertain cells as their own share.",
             interpretation_warning="Typology association is descriptive, not causal."),
        dict(chart_id="CHART_06", title="Transit Catchment Gain", question="How much does cycling expand the transit catchment, by system?",
             data_source="analysis/applications/first_last_mile_transit/transit_accessibility_gain_5_10_15.csv",
             x_dimension="system (GENERAL / FIXED)", y_dimension="pct_population (CYCLE_ONLY_TRANSIT_GAIN)", aggregation="population-weighted",
             population_weighted_or_cell_based="population-weighted", quality_mask="Report RAW and QUALITY-AWARE side by side -- do not show RAW alone as headline.",
             interpretation_warning="RAW citywide figures are heavily influenced by feed-coverage gaps (Silivri/Catalca etc.) -- see Phase 10 Section 18.D."),
        dict(chart_id="CHART_07", title="E-bike Convergence Matrix", question="Does cycling's measured accessibility gain co-occur with high e-bike Readiness/Opportunity?",
             data_source="analysis/applications/accessibility_gap_intelligence/ebike_gap_convergence.json",
             x_dimension="intervention_class (CLOSES_EVERYDAY / CLOSES_TRANSIT / CLOSES_BOTH)", y_dimension="pct_top_quartile_ebike_readiness / opportunity",
             aggregation="share within group", population_weighted_or_cell_based="cell-based",
             quality_mask="None additional beyond the frozen e-bike application's own QA.",
             interpretation_warning="CROSS-APPLICATION CONVERGENCE, explicitly not validation."),
        dict(chart_id="CHART_08", title="District Profile Composition", question="What does a selected district's accessibility profile look like?",
             data_source="analysis/framework_synthesis/district_profiles.parquet",
             x_dimension="domain (walking/cycling/transit/e-bike)", y_dimension="population or pct, per domain", aggregation="district-level sum/mean",
             population_weighted_or_cell_based="population (walking/cycling/transit), cell-mean (e-bike)",
             quality_mask="transit shown as INSUFFICIENT_TRANSIT_DATA_FOR_INTERPRETATION where applicable.",
             interpretation_warning="Districts are NEVER ranked against each other in this chart."),
    ]
    chart_df = pd.DataFrame(charts)
    chart_df.to_csv(REG_DIR / "chart_registry.csv", index=False)
    print(f"  {len(chart_df)} charts specified")
    print(f"[save] {REG_DIR / 'chart_registry.csv'}")


if __name__ == "__main__":
    main()
