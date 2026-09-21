"""Phase 6A-V2: MCDA criteria architecture revision.

Does NOT compute readiness/opportunity/scenario scores, consensus classes,
or rankings. Audits the 11 Phase 5A-V2 additions for decision relevance
against the frozen V1 24-criterion architecture (analysis/mcda/), and
proposes (without finalizing) a revised dimension/criteria/weighting
architecture. V1 MCDA artifacts are read-only inputs here, never modified.

Reasoning for each classification is semantic first (causal/conceptual
relevance to e-bike deployment readiness or latent opportunity),
statistical correlation second -- high clustering BSS or high correlation
alone never mechanically implies MCDA relevance or redundancy.

Outputs under analysis/mcda_v2/:
  criteria_catalog_v2_audit.csv       -- all 11 new candidates, classified
  v1_to_v2_criteria_change_log.csv    -- full V1->V2 change log (24 + 11)
  dimension_architecture_v2.json      -- Architecture A vs B comparison + recommendation
  value_function_proposals_v2.csv     -- candidate value functions for retained new criteria
  weighting_scenarios_v2_proposed.csv -- dimension-level scenario weights incl. Street Network
  transit_redundancy_audit.json       -- 9-criterion transit correlation audit + reduction proposal
  road_grade_terrain_redundancy_audit.json -- grade vs raster-slope correlation + decision
  phase6a_v2_summary.json             -- consolidated findings
"""

from __future__ import annotations

import json

import geopandas as gpd
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

MCDA_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda"
MCDA_V2_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda_v2"

TRANSIT_9 = [
    "distance_to_nearest_metro_m", "distance_to_nearest_tram_m", "distance_to_nearest_rail_m",
    "distance_to_nearest_ferry_m", "distance_to_nearest_metrobus_m", "distance_to_nearest_transit_m",
    "transit_stops_within_500m", "fixed_guideway_stations_within_1000m", "bus_departures_per_day",
]
GRADE_TERRAIN_COLS = ["mean_absolute_road_grade_pct", "pct_road_length_grade_gt_8pct",
                       "mean_slope_deg", "pct_area_slope_3_6deg", "pct_area_slope_6_10deg"]


def compute_redundancy_audits() -> tuple[dict, dict]:
    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet",
                          columns=["grid_id"] + TRANSIT_9 + GRADE_TERRAIN_COLS)

    transit_corr = v2[TRANSIT_9].corr(method="spearman")
    high_pairs = []
    for i, a in enumerate(TRANSIT_9):
        for b in TRANSIT_9[i + 1:]:
            rho = transit_corr.loc[a, b]
            if abs(rho) >= 0.90:
                high_pairs.append({"a": a, "b": b, "rho": round(float(rho), 3)})
    transit_audit = {
        "correlation_matrix": transit_corr.round(3).to_dict(),
        "pairs_rho_ge_0.90": high_pairs,
        "n_pairs_ge_0.90": len(high_pairs),
        "finding": (
            "9 of the 10 pairwise combinations among the 5 mode-specific distance criteria (metro, tram, rail, "
            "ferry, metrobus) are rho>=0.90 (range 0.90-0.97); the 10th (rail vs ferry) is 0.8999, effectively "
            "the same finding. This is not a statistical artifact: Istanbul's "
            "fixed-guideway transit modes are spatially bundled along the same dense urban corridors (historic "
            "peninsula, Bosphorus shore, main arterials), so a cell close to one mode is almost always close to "
            "all of them. distance_to_nearest_transit_m (the omnibus 'any mode' distance) correlates 0.65-0.79 "
            "with each -- expected, since it is effectively their running minimum -- but is not itself a "
            "duplicate of any single mode. transit_stops_within_500m (local stop density) and "
            "bus_departures_per_day (service frequency) correlate at 0.75 with each other but capture "
            "genuinely different concepts (access diversity vs level-of-service) and are far less redundant "
            "with the distance criteria (|rho|<=0.62). fixed_guideway_stations_within_1000m is only weakly-"
            "moderately correlated with everything else (0.23-0.46) -- a genuinely distinct 'high-capacity "
            "access within a wider radius' signal."
        ),
        "proposal": (
            "Reduce the 9 transit criteria to 4 for V2: KEEP distance_to_nearest_transit_m (omnibus proximity), "
            "transit_stops_within_500m (local access diversity), bus_departures_per_day (service level), "
            "fixed_guideway_stations_within_1000m (high-capacity access). MOVE the 5 mode-specific distance "
            "criteria (metro/tram/rail/ferry/metrobus) to SENSITIVITY-ONLY status -- available for a future "
            "mode-specific policy question, but not double- (quintuple-)counted in the primary architecture. "
            "This directly addresses the Phase 5B-V2 finding that removing the transit family collapses typology "
            "ARI to 0.427 (the single largest sensitivity of any family tested) by ensuring that sensitivity "
            "reflects one coherent concept measured a few complementary ways, not nine near-duplicates of the "
            "same 'near a transit corridor' signal outvoting every other dimension. This is proposed on semantic "
            "grounds (genuine corridor-bundling explanation) AND statistical grounds (rho>=0.90), not on "
            "clustering sensitivity alone, per instruction."
        ),
    }

    grade_corr = v2[GRADE_TERRAIN_COLS].corr(method="spearman")
    grade_audit = {
        "correlation_matrix": grade_corr.round(3).to_dict(),
        "key_correlations": {
            "mean_absolute_road_grade_pct__vs__mean_slope_deg": round(float(grade_corr.loc["mean_absolute_road_grade_pct", "mean_slope_deg"]), 3),
            "mean_absolute_road_grade_pct__vs__pct_area_slope_6_10deg": round(float(grade_corr.loc["mean_absolute_road_grade_pct", "pct_area_slope_6_10deg"]), 3),
            "pct_road_length_grade_gt_8pct__vs__pct_area_slope_6_10deg": round(float(grade_corr.loc["pct_road_length_grade_gt_8pct", "pct_area_slope_6_10deg"]), 3),
        },
        "finding": (
            "Road-grade and raster-slope criteria are MODERATELY correlated (0.22-0.48), not near-duplicates "
            "(well under the 0.90 redundancy threshold used throughout this project). They measure related but "
            "distinct things: raster DEM slope is a continuous surface covering the whole cell regardless of "
            "whether any road exists there, while road-grade is sampled ONLY at actual road-segment endpoints -- "
            "the exact surface a cyclist would traverse. Road-grade is NaN (not 0) for the 12.6% of cells with "
            "no road present at all, meaning raster slope remains the ONLY terrain-feasibility signal available "
            "for those cells."
        ),
        "decision": "OPTION B -- SUPPLEMENT, not replace. mean_absolute_road_grade_pct and "
        "pct_road_length_grade_gt_8pct enter the Terrain Feasibility dimension ALONGSIDE (not instead of) "
        "mean_slope_deg / pct_area_slope_3_6deg / pct_area_slope_6_10deg, with REDUCED individual weight "
        "relative to the 3 existing slope criteria to reflect (a) partial coverage (NaN for roadless cells, "
        "requiring an explicit missing-data-safe aggregation rule at scoring time) and (b) genuine but moderate "
        "conceptual overlap with the existing raster-slope signal. A full replacement (Option A) is rejected "
        "because it would silently lose all terrain-feasibility signal for roadless cells; contextual-only "
        "(Option D) is rejected because road-grade is demonstrably MORE causally direct for actual cycling "
        "paths than a rejected/sensitivity-only treatment would reflect.",
    }
    return transit_audit, grade_audit


def build_criteria_audit_v2() -> pd.DataFrame:
    rows = []

    def add(feature, dimension, disposition, direction, semantic_justification, bss_note):
        rows.append({"feature_name": feature, "dimension": dimension, "v2_disposition": disposition,
                     "direction": direction, "semantic_justification": semantic_justification,
                     "bss_independence_note": bss_note})

    add("road_density_km_per_km2", "Street Network/Connectivity (contextual)", "CONTEXTUAL_ONLY", "AMBIGUOUS",
        "Aggregates ALL highway classes (motorway down to service road) into one area-normalized figure, "
        "conflating motor-road abundance with fine-grained permeability. A cell dominated by one long motorway "
        "segment and a cell with a dense walkable grid can score similarly. No defensible single causal "
        "direction for e-bike readiness without decomposing by class -- which is exactly what "
        "intersection_density_km2 / local_road_length_m / cycle_accessible_road_density_km_per_km2 do instead.",
        "Ranked #7 individually in Phase 5A-V2 diagnostic BSS (3.77%) -- explicitly NOT used as evidence of "
        "decision relevance here; classification is driven entirely by the class-conflation problem above.")

    add("intersection_density_km2", "Street Network/Connectivity", "CANDIDATE_READINESS", "BENEFIT",
        "Direct, literature-standard proxy for street-network permeability (fine, well-connected grids have "
        "more junctions) -- distinct from and complementary to transit service. Evidence-backed causal "
        "mechanism: more route choice and shorter block lengths genuinely ease cycling/e-bike movement.",
        "High BSS (3rd-4th in most candidate-k profiles) is consistent with, but not the basis for, this "
        "classification -- the semantic case stands independent of clustering behavior.")

    add("major_road_length_m", "Street Network/Connectivity (contextual)", "CONTEXTUAL_ONLY", "AMBIGUOUS",
        "Motorway/trunk/primary/secondary length. These classes are largely legally closed to cyclists "
        "(NOT_CYCLE_ACCESSIBLE_HIGHWAY_CLASSES already excludes motorway/trunk) and function architecturally as "
        "severance barriers as often as connectivity assets. Assigning BENEFIT would wrongly reward barrier "
        "presence; assigning COST would wrongly penalize cells merely well-connected to the wider road hierarchy. "
        "No single defensible direction -- kept contextual/explanatory pending a dedicated barrier-effect study.",
        "Not used for classification.")

    add("local_road_length_m", "Street Network/Connectivity", "CANDIDATE_READINESS", "BENEFIT",
        "Tertiary/residential/living_street/unclassified/service/road -- the fine-grained, typically low-speed "
        "local network. Directly relevant to permeability and last-mile access; semantically the clearest "
        "'more local street network = more cycling-friendly access' case among the raw road-length features.",
        "Not used for classification.")

    add("cycle_accessible_road_density_km_per_km2", "Street Network/Connectivity", "CANDIDATE_READINESS", "BENEFIT",
        "Literally 'how much of the road network a cyclist may legally use, per unit area' -- the single most "
        "direct road-based Cycling Readiness proxy among the 11 additions; excludes motorway/trunk/steps by "
        "the same frozen definition used throughout this project.",
        "Not used for classification.")

    add("green_area_ratio", "Environmental/Land-use Context", "CONTEXTUAL_ONLY", "NON_MONOTONIC_UNRESOLVED",
        "Relationship to e-bike deployment is not monotonic or unambiguous: could reflect recreational cycling "
        "appeal (positive), low built-up demand context if the cell is mostly forest (neutral-to-negative for "
        "deployment), or simple urban-quality-of-life context unrelated to mobility. 'More green = better' is "
        "explicitly NOT assumed. Distinct from the ALREADY-SCORED leisure_count (POI-based leisure/recreation "
        "presence) -- must not be conflated with it. Held contextual pending a specific recreational-cycling-"
        "opportunity sub-question the project has not yet posed.",
        "Not used for classification.")

    add("residential_share_conditional", "Land-use/Green Space Context", "EXCLUDE_FROM_MCDA", "N/A",
        "This is a CLUSTERING preprocessing artifact (three-state floor-encoded value engineered specifically "
        "for KMeans distance geometry: no-evidence/mapped-zero/mapped-nonzero states separated by arbitrary "
        "offset constants). Its scale has no real-world cardinal meaning and cannot support a value function. "
        "Additionally, mean landuse_data_coverage_pct is only 9.2% and this feature correlates rho=0.909 with "
        "that coverage diagnostic -- a raw score built on it would substantially reward/penalize cells for "
        "OSM mapping completeness, not real residential land use.",
        "Not used for classification -- this exclusion holds regardless of BSS.")

    add("industrial_share_conditional", "Land-use/Green Space Context", "EXCLUDE_FROM_MCDA", "N/A",
        "Same preprocessing-artifact and coverage-reliability concerns as residential_share_conditional "
        "(rho=0.480 vs the coverage diagnostic -- weaker but still present). Excluded from scoring; the "
        "underlying raw industrial_area_ratio may be used for descriptive/contextual narrative only, never a "
        "scored criterion, given ~93% of cells show a structural (mapping-driven, not necessarily real) zero.",
        "Not used for classification.")

    add("landuse_has_mapped_evidence", "Land-use/Green Space Context", "EXCLUDE_FROM_MCDA", "N/A",
        "This is a DATA-COVERAGE diagnostic (whether any OSM land-use polygon was mapped at all), not a "
        "real-world urban characteristic. Scoring cells based on it would reward or penalize OSM community "
        "mapping completeness rather than any genuine deployment-relevant condition -- exactly the failure mode "
        "this phase's instructions explicitly warn against.",
        "Not used for classification.")

    add("mean_absolute_road_grade_pct", "Terrain Feasibility", "CANDIDATE_READINESS", "COST",
        "Directly measures physical grade on the ACTUAL navigable road network (vs. raster DEM slope "
        "everywhere) -- more causally proximate to real e-bike/cycling feasibility. See "
        "road_grade_terrain_redundancy_audit.json: moderate (0.476), non-duplicate correlation with "
        "mean_slope_deg justifies SUPPLEMENTING rather than replacing the existing Terrain criteria.",
        "Not used for classification.")

    add("pct_road_length_grade_gt_8pct", "Terrain Feasibility", "CANDIDATE_READINESS", "COST",
        "Share of a cell's road length that is genuinely steep (>8%) -- a road-anchored analogue of "
        "pct_area_slope_6_10deg, weakly correlated with it (0.221), so it is not a redundant duplicate; adds "
        "an extreme-steepness-share signal specific to the routes actually cyclable.",
        "Not used for classification.")

    return pd.DataFrame(rows)


def build_change_log(v1_catalog: pd.DataFrame, v2_audit: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in v1_catalog[v1_catalog["mcda_disposition"] == "RETAIN"].iterrows():
        if r["feature_name"] in TRANSIT_9[:5]:  # 5 mode-specific distances proposed for reduction
            rows.append({"v1_criterion": r["feature_name"], "v2_status": "SENSITIVITY_ONLY",
                         "v2_replacement_or_addition": "distance_to_nearest_transit_m (already-retained omnibus proxy)",
                         "reason": "rho>=0.90 with all 4 other mode-specific distances (transit_redundancy_audit.json) "
                                    "-- semantically bundled Istanbul transit corridors, not independent signals."})
        else:
            rows.append({"v1_criterion": r["feature_name"], "v2_status": "UNCHANGED",
                         "v2_replacement_or_addition": "-", "reason": "No new evidence changes this criterion."})
    for _, r in v2_audit.iterrows():
        rows.append({"v1_criterion": "(none -- new in V2)", "v2_status": f"NEWLY_ADDED ({r['v2_disposition']})",
                     "v2_replacement_or_addition": r["feature_name"], "reason": r["semantic_justification"][:200]})
    return pd.DataFrame(rows)


def main() -> None:
    print("=" * 72)
    print("Phase 6A-V2: MCDA criteria architecture revision")
    print("=" * 72)

    MCDA_V2_DIR.mkdir(parents=True, exist_ok=True)
    v1_catalog = pd.read_csv(MCDA_DIR / "criteria_catalog.csv")
    print(f"\n[1] V1 baseline: {len(v1_catalog[v1_catalog['mcda_disposition']=='RETAIN'])} retained criteria across "
          f"{v1_catalog[v1_catalog['mcda_disposition']=='RETAIN']['dimension'].nunique()} dimensions (reconstructed, unmodified).")

    print("\n[2] Redundancy audits (transit-internal, road-grade vs terrain-slope)...")
    transit_audit, grade_audit = compute_redundancy_audits()
    print(f"  transit: {transit_audit['n_pairs_ge_0.90']} of 36 pairs rho>=0.90 -- {transit_audit['proposal'][:100]}...")
    print(f"  road-grade vs terrain: decision = {grade_audit['decision'][:60]}...")
    (MCDA_V2_DIR / "transit_redundancy_audit.json").write_text(json.dumps(transit_audit, indent=2, default=str), encoding="utf-8")
    (MCDA_V2_DIR / "road_grade_terrain_redundancy_audit.json").write_text(json.dumps(grade_audit, indent=2, default=str), encoding="utf-8")

    print("\n[3] Auditing 11 V2 candidate criteria...")
    v2_audit = build_criteria_audit_v2()
    for _, r in v2_audit.iterrows():
        print(f"  {r['feature_name']}: {r['v2_disposition']} ({r['direction']})")
    v2_audit.to_csv(MCDA_V2_DIR / "criteria_catalog_v2_audit.csv", index=False)

    print("\n[4] V1 -> V2 change log...")
    change_log = build_change_log(v1_catalog, v2_audit)
    change_log.to_csv(MCDA_V2_DIR / "v1_to_v2_criteria_change_log.csv", index=False)
    print(f"  {len(change_log)} rows -- {(change_log['v2_status']=='UNCHANGED').sum()} unchanged, "
          f"{(change_log['v2_status']=='SENSITIVITY_ONLY').sum()} moved to sensitivity-only, "
          f"{change_log['v2_status'].str.startswith('NEWLY_ADDED').sum()} newly audited additions")

    print("\n[5] Dimension architecture comparison...")
    dimension_architecture = {
        "architecture_A_roads_in_mobility_transit": {
            "description": "Fold candidate road-readiness criteria (intersection_density_km2, "
            "local_road_length_m, cycle_accessible_road_density_km_per_km2) into the existing "
            "Mobility/Transit Context dimension.",
            "pros": ["No new dimension to calibrate", "Keeps 'how you get around' conceptually unified"],
            "cons": ["Conflates two mechanistically different things: public-transport service provision vs. "
                     "street-grid geometry for self-powered travel -- a cell can have excellent transit access "
                     "on a poorly-permeable street grid, or vice versa, and folding them obscures this",
                     "Further crowds an already-oversized dimension (9 criteria, proposed reduction to 4) with "
                     "3 more, undermining the redundancy cleanup in transit_redundancy_audit.json",
                     "Double-counting risk: transit accessibility and street connectivity both correlate with "
                     "general urbanization, so merging them into one dimension weight double-exposes that "
                     "shared urbanization signal"],
        },
        "architecture_B_separate_street_network_dimension": {
            "description": "New 'Street Network/Connectivity' dimension containing exactly "
            "intersection_density_km2, local_road_length_m, cycle_accessible_road_density_km_per_km2. "
            "road_density_km_per_km2 and major_road_length_m remain CONTEXTUAL (in no scored dimension). "
            "Road-grade stays in Terrain Feasibility (a slope/difficulty concept, not a network-geometry "
            "concept -- keeping it in Street Network would double-count terrain).",
            "pros": ["Matches established walkability/bikeability practice of treating network connectivity as "
                     "a distinct urban-form concept from transit service provision",
                     "Keeps the (separately being reduced) Mobility/Transit dimension focused and interpretable",
                     "Dimension-level weighting (per instruction 12) means a 3-criterion dimension is not "
                     "automatically under-weighted -- scenario design controls its influence explicitly"],
            "cons": ["Adds a 6th dimension, requiring every existing scenario's weight vector to be rebalanced",
                     "A 3-criterion dimension could in principle be given disproportionate weight if scenario "
                     "design is not deliberate -- mitigated by, not eliminated by, dimension-level weighting"],
        },
        "recommendation": "ARCHITECTURE B. Network permeability and transit service are mechanistically distinct "
        "and the transit dimension is independently being decluttered; combining them would re-crowd a "
        "dimension this phase is explicitly trying to make more legible, and would risk double-exposing a "
        "shared 'general urbanization' signal through two different criteria groups counted once. Recommended "
        "for BOTH the Conservative and Expanded candidate architectures below (Conservative simply omits the "
        "dimension's criteria if none pass the Conservative bar).",
    }
    (MCDA_V2_DIR / "dimension_architecture_v2.json").write_text(json.dumps(dimension_architecture, indent=2, default=str), encoding="utf-8")

    print("\n[6] Value function proposals for retained new criteria...")
    value_functions = pd.DataFrame([
        {"feature_name": "intersection_density_km2", "value_function_type": "Saturating benefit (diminishing returns)",
         "evidence_status": "ASSUMPTION-DRIVEN", "notes": "Benefit direction is evidence-backed (permeability "
         "literature); the SATURATING shape (vs. pure monotonic) is an assumption guarding against rewarding "
         "extreme values that may reflect messy/over-segmented digitization rather than real added permeability."},
        {"feature_name": "local_road_length_m", "value_function_type": "Saturating benefit",
         "evidence_status": "ASSUMPTION-DRIVEN", "notes": "Same rationale as intersection_density_km2."},
        {"feature_name": "cycle_accessible_road_density_km_per_km2", "value_function_type": "Monotonic benefit",
         "evidence_status": "EVIDENCE-BACKED (direct definitional relevance)", "notes": "Directly counts legally "
         "cycle-accessible network; monotonic benefit is the most defensible default, still capped for "
         "reasonableness like other density criteria in this project."},
        {"feature_name": "mean_absolute_road_grade_pct", "value_function_type": "Piecewise/threshold cost, "
         "reusing frozen pilot slope thresholds (comfortable <=3%, floor by 10%) adapted to grade",
         "evidence_status": "ASSUMPTION-DRIVEN (thresholds reused from a different physical quantity)",
         "notes": "Missing (NaN, roadless cells) MUST be handled by an explicit missing-data-safe rule at "
         "scoring time (e.g. fall back to raster slope alone), never imputed as 0 or as the worst/best case."},
        {"feature_name": "pct_road_length_grade_gt_8pct", "value_function_type": "Monotonic cost",
         "evidence_status": "ASSUMPTION-DRIVEN", "notes": "Same missing-data caveat as mean_absolute_road_grade_pct."},
        {"feature_name": "green_area_ratio", "value_function_type": "Contextual / no score "
         "(or inverted-U IF a recreational-cycling-opportunity sub-question is later posed)",
         "evidence_status": "ASSUMPTION-DRIVEN / UNRESOLVED", "notes": "No monotonic 'more green = better' "
         "assumption made; not scored in either Conservative or Expanded architecture below."},
        {"feature_name": "road_density_km_per_km2", "value_function_type": "Contextual / no score",
         "evidence_status": "N/A", "notes": "Class-conflation problem -- see criteria_catalog_v2_audit.csv."},
        {"feature_name": "major_road_length_m", "value_function_type": "Contextual / no score",
         "evidence_status": "N/A", "notes": "Ambiguous barrier-vs-connectivity direction -- see audit."},
        {"feature_name": "residential_share_conditional", "value_function_type": "Contextual / no score (excluded)",
         "evidence_status": "N/A", "notes": "Preprocessing artifact + coverage confound -- see audit."},
        {"feature_name": "industrial_share_conditional", "value_function_type": "Contextual / no score (excluded)",
         "evidence_status": "N/A", "notes": "Preprocessing artifact + coverage confound -- see audit."},
        {"feature_name": "landuse_has_mapped_evidence", "value_function_type": "Contextual / no score (excluded)",
         "evidence_status": "N/A", "notes": "Data-coverage diagnostic, not a real-world condition."},
    ])
    value_functions.to_csv(MCDA_V2_DIR / "value_function_proposals_v2.csv", index=False)

    print("\n[7] Proposed scenario-weight architecture (dimension-level, NOT final)...")
    dims_v1 = ["Demand/Activity Potential", "Urban Form", "Mobility/Transit Context", "Cycling Readiness", "Terrain Feasibility"]
    dims_v2_expanded = dims_v1 + ["Street Network/Connectivity"]
    scenarios_v2 = [
        {"scenario": "balanced_equal_dimensions_conservative", "architecture": "Conservative (5 dims, unchanged from V1)",
         "weights": {d: 0.20 for d in dims_v1}},
        {"scenario": "balanced_equal_dimensions_expanded", "architecture": "Expanded (6 dims)",
         "weights": {**{d: round(1/6, 4) for d in dims_v2_expanded}}},
        {"scenario": "demand_oriented_expanded", "architecture": "Expanded (6 dims)",
         "weights": {"Demand/Activity Potential": 0.35, "Urban Form": 0.13, "Mobility/Transit Context": 0.13,
                     "Cycling Readiness": 0.13, "Terrain Feasibility": 0.13, "Street Network/Connectivity": 0.13}},
        {"scenario": "infrastructure_readiness_oriented_expanded", "architecture": "Expanded (6 dims)",
         "weights": {"Demand/Activity Potential": 0.12, "Urban Form": 0.12, "Mobility/Transit Context": 0.12,
                     "Cycling Readiness": 0.32, "Terrain Feasibility": 0.12, "Street Network/Connectivity": 0.20}},
        {"scenario": "connectivity_oriented_expanded_NEW", "architecture": "Expanded (6 dims)",
         "weights": {"Demand/Activity Potential": 0.13, "Urban Form": 0.10, "Mobility/Transit Context": 0.15,
                     "Cycling Readiness": 0.15, "Terrain Feasibility": 0.12, "Street Network/Connectivity": 0.35},
         "note": "NEW scenario proposed specifically to stress-test Street Network's influence in isolation -- "
                 "not a V1 scenario, added because a new dimension warrants its own dedicated stress-test."},
    ]
    scen_df = pd.json_normalize(scenarios_v2, sep="__")
    scen_df.to_csv(MCDA_V2_DIR / "weighting_scenarios_v2_proposed.csv", index=False)
    print(f"  {len(scenarios_v2)} scenario proposals saved (dimension-level weights only, criterion-level "
          f"distribution remains equal-within-dimension by default, exactly as V1).")

    print("\n[8] Conservative vs Expanded criterion sets...")
    conservative_added = ["cycle_accessible_road_density_km_per_km2", "mean_absolute_road_grade_pct"]
    expanded_added = ["intersection_density_km2", "local_road_length_m",
                       "cycle_accessible_road_density_km_per_km2", "mean_absolute_road_grade_pct",
                       "pct_road_length_grade_gt_8pct"]
    print(f"  Conservative: V1's 24 (transit reduced 9->4 sensitivity split) + {len(conservative_added)} new "
          f"= cycling readiness gains 1 criterion, terrain gains 1, no new dimension.")
    print(f"  Expanded: V1's 24 (transit reduced 9->4) + {len(expanded_added)} new + new Street Network dimension.")

    summary = {
        "v1_baseline_retained_criteria": int((v1_catalog["mcda_disposition"] == "RETAIN").sum()),
        "transit_redundancy": {"pairs_ge_0.90": transit_audit["n_pairs_ge_0.90"], "proposal": "reduce 9 -> 4 retained + 5 sensitivity-only"},
        "road_grade_terrain_decision": "Option B: supplement with reduced weight",
        "cycling_overlap_decision": "PRIMARY = cycle_infrastructure_density_km_per_km2_ibb_only (unchanged from V1); "
        "pct_road_network_with_cycle_infrastructure held sensitivity-only -- percentage-of-network framing risks "
        "misleadingly inflated coverage in cells with very little road network at all (small-denominator effect), "
        "whereas absolute density is a standard, already-validated planning metric.",
        "land_use_decision": "residential/industrial three-state representations and the mapped-evidence flag "
        "EXCLUDED from MCDA scoring entirely (preprocessing artifacts + severe coverage confound); available "
        "for descriptive narrative only.",
        "green_space_decision": "green_area_ratio held CONTEXTUAL/no-score; no monotonic 'more green = better' "
        "assumption made; distinct from the already-scored POI-based leisure_count.",
        "recommended_dimension_architecture": "B (separate Street Network/Connectivity dimension)",
        "conservative_criteria_added": conservative_added,
        "expanded_criteria_added": expanded_added,
        "readiness_vs_opportunity": "All retained new road/grade criteria are READINESS-side (enabling "
        "conditions/feasibility), none are treated as demand and none enter the opportunity-gap term; "
        "road abundance (contextual-only features) is explicitly NOT treated as demand per instruction.",
        "sensitivity_testing_required_in_phase6b_v2": [
            "5 mode-specific transit distances (sensitivity-only vs the 4-criterion reduced set)",
            "pct_road_network_with_cycle_infrastructure vs cycle_infrastructure_density_km_per_km2_ibb_only",
            "road-grade weight magnitude within Terrain Feasibility (missing-data handling for roadless cells)",
            "Conservative vs Expanded architecture (does adding Street Network materially change readiness ranking?)",
            "Architecture A vs B (roads-in-transit vs separate dimension) as an explicit ablation",
            "connectivity_oriented_expanded_NEW scenario's isolated influence",
        ],
    }
    (MCDA_V2_DIR / "phase6a_v2_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print("\n--- SAVED ---")
    for f in ["criteria_catalog_v2_audit.csv", "v1_to_v2_criteria_change_log.csv", "dimension_architecture_v2.json",
              "value_function_proposals_v2.csv", "weighting_scenarios_v2_proposed.csv", "transit_redundancy_audit.json",
              "road_grade_terrain_redundancy_audit.json", "phase6a_v2_summary.json"]:
        print(f"[save] {MCDA_V2_DIR / f}")


if __name__ == "__main__":
    main()
