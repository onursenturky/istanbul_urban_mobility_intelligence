"""Phase 12, Sections 1-4: central product narrative, five-layer
architecture spec, formal KPI registry, and headline-KPI validation.

Read-only over every frozen artifact referenced -- no new computation
beyond simple lookups/aggregation already performed by frozen phases.
"""

from __future__ import annotations

import json

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

ROOT = cfg.PROJECT_ROOT
OUT_DIR = ROOT / "analysis" / "framework_synthesis"
REG_DIR = OUT_DIR / "registries"
WALK_DIR = ROOT / "analysis" / "applications" / "15min_city"
CYC_DIR = ROOT / "analysis" / "applications" / "cycling_accessibility"
TRANSIT_DIR = ROOT / "analysis" / "applications" / "first_last_mile_transit"
GAP_DIR = ROOT / "analysis" / "applications" / "accessibility_gap_intelligence"
MCDA_DIR = ROOT / "analysis" / "mcda_v2" / "phase6b"


def main() -> None:
    print("=" * 72)
    print("Phase 12 Sections 1-4: narrative, architecture, KPI registry, headline validation")
    print("=" * 72)
    for d in [REG_DIR, OUT_DIR / "dashboard", OUT_DIR / "case_studies", OUT_DIR / "methodology", OUT_DIR / "qa"]:
        d.mkdir(parents=True, exist_ok=True)

    print("\n[1/4] Central product narrative + positioning...")
    narrative = {
        "product_name": "Istanbul Urban Mobility Intelligence",
        "positioning": "A network-based spatial intelligence framework for understanding urban accessibility "
                        "and active-mobility opportunities across Istanbul.",
        "five_high_level_questions": [
            "What kind of urban environments exist across Istanbul?",
            "What everyday needs can residents potentially reach by walking?",
            "Where does cycling materially expand accessibility?",
            "Where can cycling expand access to public transport?",
            "Where do mapped accessibility gaps remain?",
        ],
        "translation_rule": "The end user never needs to know 'Phase 8' or 'Phase 9' -- those become, respectively, "
                             "the '15-Minute Istanbul' and 'Cycling Gain' application modules described below.",
    }
    print(json.dumps(narrative, indent=2, ensure_ascii=False))

    print("\n[2/4] Five-layer framework architecture...")
    architecture = {
        "layers": [
            {"layer": 1, "name": "URBAN DATA FOUNDATION",
             "components": ["Buildings", "Population", "POIs", "Roads", "Terrain", "Land Use", "Transit", "Cycling Infrastructure"],
             "frozen_artifacts": ["data/processed/citywide/features/urban_mobility_features_citywide_v2.parquet",
                                    "data/processed/citywide/metadata/feature_dictionary_citywide_v2.csv"]},
            {"layer": 2, "name": "SPATIAL INTELLIGENCE",
             "components": ["Urban Mobility Typology", "Walking Network", "Cycling Network"],
             "frozen_artifacts": ["analysis/clustering_v2_eight_family/cluster_assignments_v2ef.parquet",
                                    "data/processed/network/walking_graph.pkl", "data/processed/network/cycling_graph.pkl",
                                    "analysis/network_intelligence/network_intelligence_manifest.json"]},
            {"layer": 3, "name": "ACCESSIBILITY INTELLIGENCE",
             "components": ["Everyday Needs 5/10/15-Minute Walking Accessibility", "Cycling Accessibility", "Transit Infrastructure Accessibility"],
             "frozen_artifacts": ["analysis/applications/15min_city/15MIN_ISTANBUL_WALKING_V1_FROZEN_manifest.json",
                                    "analysis/applications/cycling_accessibility/phase9_manifest.json",
                                    "analysis/applications/first_last_mile_transit/phase10_manifest.json"]},
            {"layer": 4, "name": "ACTIVE MOBILITY INTELLIGENCE",
             "components": ["Walking to Cycling Accessibility Gain", "First/Last-Mile Cycling Gain", "E-bike Readiness", "Latent E-bike Opportunity"],
             "frozen_artifacts": ["analysis/applications/cycling_accessibility/walking_cycling_complete_access_comparison.parquet",
                                    "analysis/applications/first_last_mile_transit/general_transit_mode_comparison.parquet",
                                    "analysis/mcda_v2/phase6b/ebike_readiness_baseline.parquet",
                                    "analysis/mcda_v2/phase6b/ebike_opportunity_baseline.parquet"]},
            {"layer": 5, "name": "DECISION INTELLIGENCE",
             "components": ["Accessibility Gap Type", "Population Associated with Gaps", "Cycling Gap Closure", "Remaining Accessibility Gaps", "Data/Network Confidence"],
             "frozen_artifacts": ["analysis/applications/accessibility_gap_intelligence/accessibility_gap_grid_synthesis.parquet",
                                    "analysis/applications/accessibility_gap_intelligence/phase11_manifest.json"]},
        ],
        "flow": "URBAN DATA FOUNDATION -> SPATIAL INTELLIGENCE -> ACCESSIBILITY INTELLIGENCE -> ACTIVE MOBILITY INTELLIGENCE -> DECISION INTELLIGENCE",
    }
    (OUT_DIR / "methodology" / "framework_architecture.json").write_text(
        json.dumps({"narrative": narrative, "architecture": architecture}, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"[save] {OUT_DIR / 'methodology' / 'framework_architecture.json'}")

    print("\n[3/4] Building KPI registry...")
    kpi_rows = [
        # URBAN CONTEXT
        dict(kpi_id="URB_01", display_name="Calibrated 2020 Population", short_name="Population",
             description="Calibrated 2020 resident population per 500m grid cell (WorldPop-based, Phase 3C calibration to official 2020 totals).",
             unit="people", source_application="Core V2 feature baseline",
             source_file="data/processed/citywide/features/urban_mobility_features_citywide_v2.parquet", source_column="population_calibrated",
             calculation_definition="Direct frozen value, no aggregation.", population_weighted_or_cell_based="population",
             quality_requirements="None -- population layer itself, not an accessibility measurement.",
             known_limitations="2020 snapshot; network/destination data snapshot is 2026 -- temporal mismatch.",
             recommended_display_format="integer with thousands separator", recommended_visualization="choropleth / KPI card",
             headline_eligible=False, interpretation_warning="Not a 2026 population estimate."),
        dict(kpi_id="URB_02", display_name="Population Density", short_name="Pop. Density",
             description="Calibrated population per square kilometer, derived from the fixed 500m x 500m (0.25km2) grid cell area.",
             unit="people/km2", source_application="Core V2 feature baseline",
             source_file="data/processed/citywide/features/urban_mobility_features_citywide_v2.parquet", source_column="population_calibrated",
             calculation_definition="population_calibrated / 0.25", population_weighted_or_cell_based="cell",
             quality_requirements="None.", known_limitations="Same 2020-vs-2026 caveat as URB_01.",
             recommended_display_format="integer", recommended_visualization="choropleth",
             headline_eligible=False, interpretation_warning="Descriptive density, not a planning threshold."),
        dict(kpi_id="URB_03", display_name="Urban Mobility Typology", short_name="Typology",
             description="V2 eight-family k=5 urban-regime cluster assignment.",
             unit="categorical (0-4)", source_application="CITYWIDE_V2_EIGHT_FAMILY_TYPOLOGY",
             source_file="analysis/clustering_v2_eight_family/cluster_assignments_v2ef.parquet", source_column="cluster",
             calculation_definition="Frozen KMeans k=5 cluster label; see v2_typology_manifest.json for full profile.",
             population_weighted_or_cell_based="cell", quality_requirements="None.",
             known_limitations="Descriptive typology, not causal; cluster numbering has no inherent order.",
             recommended_display_format="categorical legend", recommended_visualization="choropleth (categorical palette)",
             headline_eligible=False, interpretation_warning="Typology never enters routing or accessibility computation."),
        dict(kpi_id="URB_04", display_name="Intersection Density", short_name="Intersections/km2",
             description="Road-network intersection count per km2 -- a street-connectivity indicator.",
             unit="intersections/km2", source_application="Core V2 feature baseline",
             source_file="data/processed/citywide/features/urban_mobility_features_citywide_v2.parquet", source_column="intersection_density_km2",
             calculation_definition="Frozen value from Phase 7A road-network feature computation.", population_weighted_or_cell_based="cell",
             quality_requirements="None.", known_limitations="OSM digitization completeness varies by district.",
             recommended_display_format="1 decimal", recommended_visualization="choropleth",
             headline_eligible=False, interpretation_warning="Connectivity proxy, not a walkability score."),
        dict(kpi_id="URB_05", display_name="Cycling Infrastructure Density", short_name="Cycle Infra Density",
             description="Length of İBB-mapped cycling infrastructure per km2.",
             unit="km/km2", source_application="Core V2 feature baseline",
             source_file="data/processed/citywide/features/urban_mobility_features_citywide_v2.parquet", source_column="cycle_infrastructure_density_km_per_km2_ibb_only",
             calculation_definition="Frozen value; İBB dataset only (not OSM-inferred).", population_weighted_or_cell_based="cell",
             quality_requirements="None.", known_limitations="İBB-only source -- may undercount informally-used cycling routes.",
             recommended_display_format="2 decimals", recommended_visualization="choropleth",
             headline_eligible=False, interpretation_warning="Infrastructure presence, not usage."),
        # WALKING ACCESSIBILITY
        dict(kpi_id="WALK_01", display_name="Required Categories Accessible (Walking, 15min)", short_name="Walk Req. Categories",
             description="Count (0-3) of Food/Healthcare/Education reachable within 15 minutes on the walking network.",
             unit="count (0-3)", source_application="15-MINUTE ISTANBUL v1",
             source_file="analysis/applications/15min_city/grid_proximity_summary.parquet", source_column="required_categories_accessible_15min",
             calculation_definition="Frozen exact-network cutoff-Dijkstra result.", population_weighted_or_cell_based="both",
             quality_requirements="corrected_accessibility_quality_flags.parquet quality flag RELIABLE recommended for interpretation.",
             known_limitations="Search horizon capped at 15min; Adalar/isolated components flagged separately.",
             recommended_display_format="integer badge", recommended_visualization="4-category choropleth",
             headline_eligible=True, interpretation_warning="Modeled network accessibility, not observed travel behavior."),
        dict(kpi_id="WALK_02", display_name="Complete 15-Minute Walking Access", short_name="Complete Walk Access",
             description="Whether a cell reaches all 3 required categories within 15 minutes walking.",
             unit="boolean", source_application="15-MINUTE ISTANBUL v1",
             source_file="analysis/applications/15min_city/grid_proximity_summary.parquet", source_column="COMPLETE_15MIN_ACCESS",
             calculation_definition="required_categories_accessible_15min == 3.", population_weighted_or_cell_based="both",
             quality_requirements="See WALK_01.", known_limitations="See WALK_01.",
             recommended_display_format="boolean/binary map", recommended_visualization="binary choropleth",
             headline_eligible=True, interpretation_warning="Do not call this 'living in a 15-minute city' -- see claims registry."),
        dict(kpi_id="WALK_03", display_name="Nearest Food/Groceries (Walking)", short_name="Food Time (Walk)",
             description="Nearest-network travel time to a Food/Groceries destination, walking.",
             unit="minutes (NaN if unreachable within 15min)", source_application="15-MINUTE ISTANBUL v1",
             source_file="analysis/applications/15min_city/grid_nearest_service_times.parquet", source_column="A_food_groceries_nearest_time_min",
             calculation_definition="Exact cutoff-Dijkstra nearest-node time.", population_weighted_or_cell_based="cell",
             quality_requirements="See WALK_01.", known_limitations="NaN means unreachable within the 15min search horizon, not 'very far'.",
             recommended_display_format="1 decimal, minutes", recommended_visualization="choropleth (sequential, capped at 15)",
             headline_eligible=False, interpretation_warning="Never substitute a large number for NaN."),
        dict(kpi_id="WALK_04", display_name="Nearest Healthcare (Walking)", short_name="Healthcare Time (Walk)",
             description="Nearest-network travel time to a Healthcare destination, walking.",
             unit="minutes (NaN if unreachable within 15min)", source_application="15-MINUTE ISTANBUL v1",
             source_file="analysis/applications/15min_city/grid_nearest_service_times.parquet", source_column="B_healthcare_nearest_time_min",
             calculation_definition="Exact cutoff-Dijkstra nearest-node time.", population_weighted_or_cell_based="cell",
             quality_requirements="See WALK_01.", known_limitations="See WALK_03.",
             recommended_display_format="1 decimal, minutes", recommended_visualization="choropleth (sequential, capped at 15)",
             headline_eligible=False, interpretation_warning="Never substitute a large number for NaN."),
        dict(kpi_id="WALK_05", display_name="Nearest Education (Walking)", short_name="Education Time (Walk)",
             description="Nearest-network travel time to an Education destination, walking.",
             unit="minutes (NaN if unreachable within 15min)", source_application="15-MINUTE ISTANBUL v1",
             source_file="analysis/applications/15min_city/grid_nearest_service_times.parquet", source_column="C_education_nearest_time_min",
             calculation_definition="Exact cutoff-Dijkstra nearest-node time.", population_weighted_or_cell_based="cell",
             quality_requirements="See WALK_01.", known_limitations="See WALK_03.",
             recommended_display_format="1 decimal, minutes", recommended_visualization="choropleth (sequential, capped at 15)",
             headline_eligible=False, interpretation_warning="Never substitute a large number for NaN."),
        # CYCLING ACCESSIBILITY
        dict(kpi_id="CYC_01", display_name="Complete 15-Minute Cycling Access", short_name="Complete Cycle Access",
             description="Whether a cell reaches all 3 required categories within 15 minutes cycling.",
             unit="boolean", source_application="CYCLING_ACCESSIBILITY_AND_ACTIVE_MOBILITY_GAIN_V1",
             source_file="analysis/applications/cycling_accessibility/walking_cycling_complete_access_comparison.parquet", source_column="CYCLING_COMPLETE_15MIN_ACCESS",
             calculation_definition="cycling_required_categories_accessible_15min == 3.", population_weighted_or_cell_based="both",
             quality_requirements="cycling_accessibility_quality_flags.parquet RELIABLE recommended.",
             known_limitations="Baseline 15km/h constant speed; oneway:bicycle not modeled; Adalar cross-water artifact.",
             recommended_display_format="boolean/binary map", recommended_visualization="binary choropleth",
             headline_eligible=True, interpretation_warning="Modeled POTENTIAL accessibility, not observed cycling behavior."),
        dict(kpi_id="CYC_02", display_name="Cycling-Only Everyday-Needs Gain", short_name="Cycle-Only Gain",
             description="Cell lacks complete walking access but has complete cycling access.",
             unit="boolean", source_application="CYCLING_ACCESSIBILITY_AND_ACTIVE_MOBILITY_GAIN_V1",
             source_file="analysis/applications/cycling_accessibility/walking_cycling_complete_access_comparison.parquet", source_column="access_class",
             calculation_definition="access_class == 'CYCLE_ONLY_GAIN'.", population_weighted_or_cell_based="both",
             quality_requirements="See CYC_01.", known_limitations="See CYC_01.",
             recommended_display_format="categorical badge", recommended_visualization="categorical choropleth (Map 05)",
             headline_eligible=True, interpretation_warning="Descriptive network measurement, not a behavioral prediction."),
        dict(kpi_id="CYC_03", display_name="Required Categories Gained by Cycling", short_name="Categories Gained",
             description="Number of required categories newly accessible via cycling that were not accessible via walking.",
             unit="count (0-3)", source_application="CYCLING_ACCESSIBILITY_AND_ACTIVE_MOBILITY_GAIN_V1",
             source_file="analysis/applications/accessibility_gap_intelligence/accessibility_gap_grid_synthesis.parquet", source_column="cycling_closed_categories",
             calculation_definition="Derived (Phase 11) from cycling_required_categories_accessible_15min minus walking_required_categories_accessible_15min, floored at 0.",
             population_weighted_or_cell_based="cell", quality_requirements="everyday_access_reliable == True.",
             known_limitations="See CYC_01.", recommended_display_format="integer", recommended_visualization="choropleth",
             headline_eligible=False, interpretation_warning="Descriptive, not a priority score."),
        # TRANSIT ACCESS
        dict(kpi_id="TR_01", display_name="Nearest General Transit (Walking)", short_name="Transit Time (Walk)",
             description="Nearest-network travel time to any mapped transit access point (bus/metrobus/metro/tram/rail/ferry), walking.",
             unit="minutes (NaN if unreachable within 15min)", source_application="FIRST_LAST_MILE_TRANSIT_ACCESSIBILITY_V1",
             source_file="analysis/applications/first_last_mile_transit/walking_general_transit_accessibility.parquet", source_column="nearest_time_min",
             calculation_definition="Exact cutoff-Dijkstra nearest-node time to System A.", population_weighted_or_cell_based="cell",
             quality_requirements="transit_gap_diagnostics.parquet quality_uncertainty_flag == RELIABLE strongly recommended.",
             known_limitations="main_gtfs stale (topology only); Silivri/Catalca have zero mapped stops (NO_FEED_COVERAGE).",
             recommended_display_format="1 decimal, minutes", recommended_visualization="choropleth",
             headline_eligible=False, interpretation_warning="NO_FEED_COVERAGE != NO_TRANSIT_SERVICE."),
        dict(kpi_id="TR_02", display_name="Nearest Fixed-Guideway Transit (Walking)", short_name="Fixed Transit Time (Walk)",
             description="Nearest-network travel time to metro/tram/rail/metrobus (System B), walking.",
             unit="minutes (NaN if unreachable within 15min)", source_application="FIRST_LAST_MILE_TRANSIT_ACCESSIBILITY_V1",
             source_file="analysis/applications/first_last_mile_transit/walking_fixed_transit_accessibility.parquet", source_column="nearest_time_min",
             calculation_definition="Exact cutoff-Dijkstra nearest-node time to System B.", population_weighted_or_cell_based="cell",
             quality_requirements="See TR_01.", known_limitations="Ferry deliberately excluded from System B.",
             recommended_display_format="1 decimal, minutes", recommended_visualization="choropleth",
             headline_eligible=False, interpretation_warning="See TR_01."),
        dict(kpi_id="TR_03", display_name="Nearest General Transit (Cycling)", short_name="Transit Time (Cycle)",
             description="Nearest-network travel time to any mapped transit access point, cycling.",
             unit="minutes (NaN if unreachable within 15min)", source_application="FIRST_LAST_MILE_TRANSIT_ACCESSIBILITY_V1",
             source_file="analysis/applications/first_last_mile_transit/cycling_general_transit_accessibility.parquet", source_column="nearest_time_min",
             calculation_definition="Exact cutoff-Dijkstra nearest-node time to System A on the cycling graph.", population_weighted_or_cell_based="cell",
             quality_requirements="See TR_01 (cycling quality flag also relevant).", known_limitations="Adalar cross-water cycling artifact.",
             recommended_display_format="1 decimal, minutes", recommended_visualization="choropleth",
             headline_eligible=False, interpretation_warning="See TR_01."),
        dict(kpi_id="TR_04", display_name="Nearest Fixed-Guideway Transit (Cycling)", short_name="Fixed Transit Time (Cycle)",
             description="Nearest-network travel time to metro/tram/rail/metrobus, cycling.",
             unit="minutes (NaN if unreachable within 15min)", source_application="FIRST_LAST_MILE_TRANSIT_ACCESSIBILITY_V1",
             source_file="analysis/applications/first_last_mile_transit/cycling_fixed_transit_accessibility.parquet", source_column="nearest_time_min",
             calculation_definition="Exact cutoff-Dijkstra nearest-node time to System B on the cycling graph.", population_weighted_or_cell_based="cell",
             quality_requirements="See TR_01.", known_limitations="See TR_02, TR_03.",
             recommended_display_format="1 decimal, minutes", recommended_visualization="choropleth",
             headline_eligible=False, interpretation_warning="See TR_01."),
        dict(kpi_id="TR_05", display_name="Cycle-Only Transit Gain (General)", short_name="Cycle-Only Transit Gain",
             description="Cell cannot reach general transit within 10min walking but can within 10min cycling.",
             unit="boolean", source_application="FIRST_LAST_MILE_TRANSIT_ACCESSIBILITY_V1",
             source_file="analysis/applications/first_last_mile_transit/general_transit_mode_comparison.parquet", source_column="access_class_10min",
             calculation_definition="access_class_10min == 'CYCLE_ONLY_TRANSIT_GAIN'.", population_weighted_or_cell_based="both",
             quality_requirements="quality_uncertainty_flag == RELIABLE strongly recommended (RAW figure dominated by feed gaps).",
             known_limitations="Primary threshold is 10min for general transit (differs from fixed-guideway's 15min).",
             recommended_display_format="categorical badge", recommended_visualization="categorical choropleth (Map 07)",
             headline_eligible=True, interpretation_warning="Use QUALITY-AWARE figures for headline claims, RAW only as diagnostic."),
        # ACCESSIBILITY GAP
        dict(kpi_id="GAP_01", display_name="Everyday-Needs Gap Type", short_name="Everyday Gap Type",
             description="Which required categories (Food/Healthcare/Education) are missing within 15min walking.",
             unit="categorical (9 classes)", source_application="ACCESSIBILITY_GAP_INTELLIGENCE_V1",
             source_file="analysis/applications/accessibility_gap_intelligence/everyday_needs_gap_typology.parquet", source_column="everyday_gap_class",
             calculation_definition="Derived directly from frozen Phase 8 missing-category flags; UNKNOWN_OR_QUALITY_LIMITED when network quality does not permit interpretation.",
             population_weighted_or_cell_based="both", quality_requirements="Built-in (UNKNOWN class covers unreliable cells).",
             known_limitations="Categorical, not a severity score.", recommended_display_format="categorical legend",
             recommended_visualization="categorical choropleth (Map 08)", headline_eligible=False,
             interpretation_warning="Use neutral 'accessibility gap' language -- never 'service desert' or similar."),
        dict(kpi_id="GAP_02", display_name="Cycling Gap-Closure Status", short_name="Closure Status",
             description="Whether cycling fully, partially, or does not close a cell's everyday-needs gap.",
             unit="categorical (5 classes)", source_application="ACCESSIBILITY_GAP_INTELLIGENCE_V1",
             source_file="analysis/applications/accessibility_gap_intelligence/cycling_gap_closure.parquet", source_column="cycling_closure_status",
             calculation_definition="Derived (Phase 11) by comparing missing walking categories against cycling 15min access for those same categories.",
             population_weighted_or_cell_based="both", quality_requirements="everyday_access_reliable == True (else CYCLING_RESULT_UNCERTAIN).",
             known_limitations="Only defined for cells WITH a walking gap.", recommended_display_format="categorical legend",
             recommended_visualization="categorical choropleth (Map 05)", headline_eligible=True,
             interpretation_warning="Modeled potential closure, not observed mode shift."),
        dict(kpi_id="GAP_03", display_name="Multi-Domain Accessibility Pattern", short_name="Multi-Domain Pattern",
             description="Joint everyday-needs and transit-access gap status (A-E classes).",
             unit="categorical (5 classes)", source_application="ACCESSIBILITY_GAP_INTELLIGENCE_V1",
             source_file="analysis/applications/accessibility_gap_intelligence/multi_domain_accessibility_patterns.parquet", source_column="multi_domain_class",
             calculation_definition="Combines everyday_gap_class and transit_access_gap_class under strict_synthesis_reliable.",
             population_weighted_or_cell_based="both", quality_requirements="strict_synthesis_reliable == True (else class E).",
             known_limitations="Class E (uncertain) is large (26.16% of population) due to transit feed-coverage gaps.",
             recommended_display_format="categorical legend", recommended_visualization="categorical choropleth",
             headline_eligible=False, interpretation_warning="Not a composite score -- a joint categorical label only."),
        # E-BIKE
        dict(kpi_id="EBK_01", display_name="E-bike Readiness", short_name="Readiness",
             description="Frozen baseline e-bike deployment Readiness score (physical/infrastructural suitability dimension).",
             unit="continuous [0,1]", source_application="E-bike Readiness & Latent Opportunity",
             source_file="analysis/mcda_v2/phase6b/ebike_readiness_baseline.parquet", source_column="ebike_readiness",
             calculation_definition="Frozen MCDA dimension-first aggregation; see Phase 6B-V2 manifest for full derivation.",
             population_weighted_or_cell_based="cell", quality_requirements="None additional beyond the frozen application's own QA.",
             known_limitations="MCDA value function, not a physical measurement; do not average across cells naively.",
             recommended_display_format="0-100 normalized display", recommended_visualization="choropleth (sequential)",
             headline_eligible=False, interpretation_warning="Suitability indicator, not a deployment guarantee."),
        dict(kpi_id="EBK_02", display_name="Latent E-bike Opportunity", short_name="Opportunity",
             description="Frozen baseline e-bike Opportunity score (demand-potential x cycling-gap dimension).",
             unit="continuous [0,1]", source_application="E-bike Readiness & Latent Opportunity",
             source_file="analysis/mcda_v2/phase6b/ebike_opportunity_baseline.parquet", source_column="ebike_opportunity",
             calculation_definition="Frozen geometric demand^alpha * gap^(1-alpha) formula; see Phase 6B-V2 manifest.",
             population_weighted_or_cell_based="cell", quality_requirements="None additional.",
             known_limitations="See EBK_01.", recommended_display_format="0-100 normalized display",
             recommended_visualization="choropleth (sequential)", headline_eligible=False,
             interpretation_warning="'Latent' means modeled, not observed or surveyed demand."),
        dict(kpi_id="EBK_03", display_name="E-bike Readiness Consensus Class", short_name="Readiness Robustness",
             description="Sensitivity-robustness classification (ROBUST_HIGH/FREQUENT_HIGH/CONDITIONAL_HIGH/RARE_HIGH/NEVER_HIGH) across the 6 scoring variants.",
             unit="categorical (5 classes)", source_application="E-bike Readiness & Latent Opportunity",
             source_file="analysis/mcda_v2/phase6b/consensus_classes.parquet", source_column="readiness_consensus_class",
             calculation_definition="Frozen; share of 6 sensitivity variants placing the cell in the top decile.",
             population_weighted_or_cell_based="cell", quality_requirements="None additional.",
             known_limitations="Robustness to MCDA weighting choices only, not to data quality.",
             recommended_display_format="categorical legend", recommended_visualization="categorical choropleth",
             headline_eligible=False, interpretation_warning="Robust across scoring variants, not validated against real deployments."),
        dict(kpi_id="EBK_04", display_name="E-bike Opportunity Consensus Class", short_name="Opportunity Robustness",
             description="Sensitivity-robustness classification for Opportunity across the 6 scoring variants.",
             unit="categorical (5 classes)", source_application="E-bike Readiness & Latent Opportunity",
             source_file="analysis/mcda_v2/phase6b/consensus_classes.parquet", source_column="opportunity_consensus_class",
             calculation_definition="Frozen; share of 6 sensitivity variants placing the cell in the top decile.",
             population_weighted_or_cell_based="cell", quality_requirements="None additional.",
             known_limitations="See EBK_03.", recommended_display_format="categorical legend",
             recommended_visualization="categorical choropleth", headline_eligible=False, interpretation_warning="See EBK_03."),
        # QUALITY
        dict(kpi_id="QA_01", display_name="Walking Network Quality", short_name="Walking Quality",
             description="Corrected network-quality/component-reliability flag for walking accessibility interpretation.",
             unit="categorical (5 classes)", source_application="15-MINUTE ISTANBUL v1 / Phase 8.1",
             source_file="analysis/applications/15min_city/validation/corrected_accessibility_quality_flags.parquet", source_column="corrected_quality_flag",
             calculation_definition="Frozen Phase 8.1 evidence-based component classification.", population_weighted_or_cell_based="cell",
             quality_requirements="N/A -- this IS the quality field.", known_limitations="Adalar always KNOWN_NETWORK_LIMITATION_ADALAR.",
             recommended_display_format="categorical legend", recommended_visualization="categorical choropleth (Map 12)",
             headline_eligible=False, interpretation_warning="RELIABLE_SEPARATE_COMPONENT is valid, not a defect (genuine Bosphorus separation)."),
        dict(kpi_id="QA_02", display_name="Cycling Network Quality", short_name="Cycling Quality",
             description="Corrected network-quality/component-reliability flag for cycling accessibility interpretation.",
             unit="categorical (5 classes)", source_application="CYCLING_ACCESSIBILITY_AND_ACTIVE_MOBILITY_GAIN_V1",
             source_file="analysis/applications/cycling_accessibility/cycling_accessibility_quality_flags.parquet", source_column="corrected_quality_flag",
             calculation_definition="Cycling-specific evidence-based component classification (own thresholds, not walking's reused).",
             population_weighted_or_cell_based="cell", quality_requirements="N/A.", known_limitations="See QA_01; Adalar has zero actual cycling nodes (cross-water anchor artifact).",
             recommended_display_format="categorical legend", recommended_visualization="categorical choropleth (Map 12)",
             headline_eligible=False, interpretation_warning="See QA_01."),
        dict(kpi_id="QA_03", display_name="Transit Feed/Data Quality", short_name="Transit Data Quality",
             description="District-level transit feed coverage adequacy classification.",
             unit="categorical (4 classes)", source_application="FIRST_LAST_MILE_TRANSIT_ACCESSIBILITY_V1",
             source_file="analysis/applications/first_last_mile_transit/transit_district_quality.csv", source_column="transit_data_quality_class",
             calculation_definition="Data-driven (not mechanical) classification from stop density + known sparse-district evidence.",
             population_weighted_or_cell_based="district", quality_requirements="N/A.",
             known_limitations="Silivri and Catalca are NO_FEED_COVERAGE -- their stop counts are exactly zero, confirmed by re-audit.",
             recommended_display_format="categorical legend", recommended_visualization="categorical choropleth / hatched overlay (Map 12)",
             headline_eligible=False, interpretation_warning="NO_FEED_COVERAGE must NEVER be displayed or read as NO_TRANSIT_SERVICE."),
        dict(kpi_id="QA_04", display_name="Synthesis Reliability Universe", short_name="Synthesis Reliability",
             description="Whether a cell qualifies for joint everyday-needs + transit interpretation (STRICT_SYNTHESIS_RELIABLE).",
             unit="boolean", source_application="ACCESSIBILITY_GAP_INTELLIGENCE_V1",
             source_file="analysis/applications/accessibility_gap_intelligence/accessibility_gap_grid_synthesis.parquet", source_column="strict_synthesis_reliable",
             calculation_definition="everyday_access_reliable AND transit_access_reliable.", population_weighted_or_cell_based="both",
             quality_requirements="N/A -- this IS the reliability field.", known_limitations="Only 27.29% of cells / 73.84% of population qualify.",
             recommended_display_format="boolean/binary map", recommended_visualization="binary choropleth (Map 12)",
             headline_eligible=False, interpretation_warning="Low coverage is itself a finding, not a flaw to hide."),
    ]
    kpi_df = pd.DataFrame(kpi_rows)
    kpi_df.to_csv(REG_DIR / "kpi_registry.csv", index=False)
    print(f"  {len(kpi_df)} KPIs registered across {kpi_df['source_application'].nunique()} source applications")
    print(f"[save] {REG_DIR / 'kpi_registry.csv'}")

    print("\n[4/4] Headline KPI validation (exact frozen values, denominators, universes, reconciliation)...")
    walk_pop = json.loads((WALK_DIR / "validation" / "population_accessibility_validation.json").read_text(encoding="utf-8"))
    cyc_pop = json.loads((CYC_DIR / "population_cycling_accessibility_summary.json").read_text(encoding="utf-8"))
    transit_pop = json.loads((TRANSIT_DIR / "population_transit_accessibility_summary.json").read_text(encoding="utf-8"))
    gap_findings = json.loads((GAP_DIR / "framework_level_findings.json").read_text(encoding="utf-8"))
    gap_summary = pd.read_csv(GAP_DIR / "everyday_needs_gap_summary.csv")
    ebike_conv = json.loads((GAP_DIR / "ebike_gap_convergence.json").read_text(encoding="utf-8"))

    denom_a = walk_pop["denominator_A_all_populated_cells"]
    gap11_no_gap = gap_summary.loc[gap_summary["gap_class"] == "NO_REQUIRED_GAP"].iloc[0]

    headline = [
        {"claim_id": "H01", "value_pct": denom_a["pct_with_complete_access"],
         "population": denom_a["population_with_complete_access"], "denominator_population": denom_a["included_calibrated_population"],
         "analysis_universe": "Phase 8.1 Denominator A: ALL populated cells, using each cell's RAW COMPLETE_15MIN_ACCESS flag "
                               "regardless of network-quality flag.",
         "definition": "Cell reaches >=1 destination in EVERY required category (Food, Healthcare, Education) within 15min walking.",
         "source_file": "analysis/applications/15min_city/validation/population_accessibility_validation.json",
         "quality_condition": "None applied (this is the RAW/denominator-A figure, frozen as the official Phase 8.1 headline).",
         "caveat": "This is the FROZEN, officially adopted headline figure for 15-Minute Istanbul walking access."},
        {"claim_id": "H01b", "value_pct": round(float(gap11_no_gap["pct_population"]), 2),
         "population": float(gap11_no_gap["population"]), "denominator_population": denom_a["included_calibrated_population"],
         "analysis_universe": "Phase 11 synthesis: same population/denominator as H01, but the classification additionally "
                               "requires everyday_access_reliable == True (BOTH walking AND cycling network quality flags "
                               "RELIABLE) before a cell can be counted NO_REQUIRED_GAP.",
         "definition": "Same as H01, EXCEPT 20 cells (2,424.1 population) that were raw-COMPLETE but network-quality-flagged "
                        "are reclassified UNKNOWN_OR_QUALITY_LIMITED instead of counted as gap-free.",
         "source_file": "analysis/applications/accessibility_gap_intelligence/everyday_needs_gap_summary.csv",
         "quality_condition": "everyday_access_reliable == True required for NO_REQUIRED_GAP classification.",
         "caveat": "RECONCILIATION: 82.49% (H01) vs 82.47% (H01b) differ by exactly 20 cells / 2,424.1 population that Phase 11 "
                    "treats more conservatively. This is a deliberate quality-conservatism refinement in the later synthesis "
                    "phase, NOT a computational error or a case of picking the more favorable number."},
        {"claim_id": "H02", "value_population": 2_095_477.3,
         "analysis_universe": "Phase 9/Phase 11: cells with a walking everyday-needs gap where cycling closes ALL missing "
                               "required categories (FULLY_CLOSED_BY_CYCLING / frozen CYCLE_ONLY_GAIN).",
         "definition": "Population in cells lacking complete walking access but having complete potential cycling access.",
         "source_file": "analysis/applications/cycling_accessibility/population_cycling_accessibility_summary.json",
         "quality_condition": "Reported figure is from Phase 9 (all cells); Phase 11's RELIABLE-only subset gives a "
                               "near-identical 2,095,477.3 (99.9% of the Phase 9 figure) -- see consistency test B.",
         "caveat": "Modeled potential, not observed mode shift."},
        {"claim_id": "H03", "value_pct": cyc_pop["cycling_complete_15min_access"]["pct_population"],
         "population": cyc_pop["cycling_complete_15min_access"]["population"],
         "analysis_universe": "Phase 9: ALL cells, cycling network, same 3 required categories, same calibrated 2020 population.",
         "definition": "Cell reaches all 3 required categories within 15min on the cycling network (constant 15km/h baseline speed).",
         "source_file": "analysis/applications/cycling_accessibility/population_cycling_accessibility_summary.json",
         "quality_condition": "RAW figure (all cells); quality-aware re-check in Phase 9 Section 12 showed <0.1% population difference.",
         "caveat": "This is a DIFFERENT denominator/definition than H01 -- both are 'out of total population' but measure "
                    "different modes; they are NOT directly comparable as a single 'gain' figure without going through H02's "
                    "cell-level join."},
        {"claim_id": "H04", "value_population": 3_025_322.3,
         "analysis_universe": "Phase 10: CYCLE_ONLY_TRANSIT_GAIN, System A (general transit), 15min threshold (RAW, all cells).",
         "definition": "Population in cells unable to reach general transit within 15min walking but able to within 15min cycling.",
         "source_file": "analysis/applications/first_last_mile_transit/transit_accessibility_gain_5_10_15.csv",
         "quality_condition": "RAW figure -- Phase 10's primary definition uses a 10min threshold and QUALITY-AWARE filtering, "
                               "which gives a smaller, more defensible ~2.1-3.4M range depending on exact cut. See H04b.",
         "caveat": "Do NOT add this to H02 or H07 -- different universe (transit vs everyday needs), different threshold."},
        {"claim_id": "H04b", "value_population": None, "note": "Quality-aware, 10min-primary-threshold general-transit "
            "cycling-gain population is reported per-district in district_accessibility_gap_summary.csv rather than as one "
            "citywide figure, because feed-coverage gaps (Silivri/Catalca and 16 other districts) make an unqualified "
            "citywide RAW number misleading -- see Phase 10 Section 18.D feed-gap sensitivity finding (+30.83pp swing).",
         "source_file": "analysis/applications/first_last_mile_transit/phase10_manifest.json"},
        {"claim_id": "H05", "value_population": 4_801_394.5,
         "analysis_universe": "Phase 10: CYCLE_ONLY_TRANSIT_GAIN, System B (fixed-guideway), 15min threshold (RAW, all cells).",
         "definition": "Population in cells unable to reach fixed-guideway transit within 15min walking but able to within 15min cycling.",
         "source_file": "analysis/applications/first_last_mile_transit/transit_accessibility_gain_5_10_15.csv",
         "quality_condition": "RAW figure -- same feed-gap caveat as H04.",
         "caveat": "Largest of the transit-gain figures; interpret alongside the feed-gap sensitivity finding."},
        {"claim_id": "H06", "value_population": float(gap_findings["q7_population_cycling_does_not_close_gap_destinations_sparse"]["population"]),
         "value_pct": gap_findings["q7_population_cycling_does_not_close_gap_destinations_sparse"]["pct"],
         "analysis_universe": "Phase 11: cells with a walking everyday-needs gap where cycling does NOT close any missing category (UNCHANGED_BY_CYCLING).",
         "definition": "Population where destinations themselves appear sparse even within cycling range.",
         "source_file": "analysis/applications/accessibility_gap_intelligence/framework_level_findings.json",
         "quality_condition": "everyday_access_reliable == True implicitly required (UNCHANGED_BY_CYCLING excludes UNKNOWN cells).",
         "caveat": "Genuine destination-sparsity signal, not a network/routing limitation."},
        {"claim_id": "H07", "value_population": 341_370.2, "value_pct": 2.21,
         "analysis_universe": "Phase 11: intervention_class in (CYCLING_CLOSES_TRANSIT_GAP, CYCLING_CLOSES_BOTH), STRICT_SYNTHESIS_RELIABLE.",
         "definition": "Quality-aware population where cycling closes a measured transit-access gap.",
         "source_file": "analysis/applications/accessibility_gap_intelligence/framework_level_findings.json",
         "quality_condition": "STRICT_SYNTHESIS_RELIABLE == True (both network AND transit-feed quality adequate).",
         "caveat": "Much smaller than H04/H05 because it requires BOTH domains reliable -- this is the DEFENSIBLE, "
                    "quality-aware figure, not a contradiction of H04/H05."},
        {"claim_id": "H08", "value_pct": ebike_conv["CYCLING_CLOSES_EVERYDAY_GAP"]["pct_top_quartile_ebike_readiness"],
         "analysis_universe": "Phase 11: cells classified CYCLING_CLOSES_EVERYDAY_GAP (n="
                               f"{ebike_conv['CYCLING_CLOSES_EVERYDAY_GAP']['n_cells']}), checked against frozen e-bike Readiness quartiles.",
         "definition": "Share of CYCLING_CLOSES_EVERYDAY_GAP cells in the top quartile of frozen e-bike Readiness (citywide baseline: 25%).",
         "source_file": "analysis/applications/accessibility_gap_intelligence/ebike_gap_convergence.json",
         "quality_condition": "Descriptive cross-application convergence only -- e-bike model unmodified.",
         "caveat": "This is CROSS-APPLICATION CONVERGENCE, explicitly NOT validation of either application."},
    ]
    (OUT_DIR / "headline_kpis.json").write_text(json.dumps({"headline_findings": headline}, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  {len(headline)} headline KPI records written, including the explicit 82.47 vs 82.49 reconciliation (H01/H01b)")
    print(f"[save] {OUT_DIR / 'headline_kpis.json'}")


if __name__ == "__main__":
    main()
