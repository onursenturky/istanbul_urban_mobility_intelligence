"""Phase 6A: E-bike Deployment Suitability Criteria Architecture.

Builds a transparent MCDA criteria catalog from the 71 Phase 5A-eligible
citywide predictors (READY + READY_WITH_LIMITATION), independent of the
Phase 5C k=5 descriptive typology (which is used ONLY afterward, for
cross-tab interpretation -- never as a predictor or weight source).

Produces the full criteria architecture: dimension assignment, benefit/
cost/context-dependent/exclude classification with rationale, redundancy
resolution (building on Phase 5A/5C's already-computed correlations),
candidate value-function proposals, a readiness-vs-need/opportunity split,
citywide typology cross-tabulation for interpretation, and several
transparent weighting SCENARIOS (not a final weight vector).

Does NOT compute any suitability score, ranking, or map.
"""

from __future__ import annotations

import json

import geopandas as gpd
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

MCDA_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda"
EDA_DIR = cfg.PROJECT_ROOT / "analysis" / "eda"
CLUSTER_V2_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering_v2"

# Frozen pilot e-bike slope thresholds (src/analysis/suitability_config.py),
# reused unchanged rather than inventing new cutoffs.
EBIKE_SLOPE_COMFORTABLE_DEG = 3.0
EBIKE_SLOPE_STEEP_DEG = 10.0
EBIKE_SLOPE_FLOOR = 0.5


# --------------------------------------------------------------------------
# 1. Criteria catalog: every Phase 5A-eligible predictor, MCDA disposition
# --------------------------------------------------------------------------

def build_catalog() -> pd.DataFrame:
    rows = []

    def add(name, dimension, disposition, direction, rationale, represented_by=None):
        rows.append({
            "feature_name": name, "dimension": dimension, "mcda_disposition": disposition,
            "direction": direction, "rationale": rationale,
            "represented_by_if_excluded": represented_by,
        })

    # --- Demand / Activity Potential ---
    add("population_density_calibrated_km2", "Demand/Activity Potential", "RETAIN", "CONTEXT_DEPENDENT",
        "Higher residential density plausibly supports trip demand, but extremely dense environments can face "
        "saturation, pedestrian conflict, and street-space/parking constraints for shared vehicles -- not "
        "assumed monotonic per explicit instruction.")
    add("poi_density_km2", "Demand/Activity Potential", "RETAIN", "BENEFIT",
        "General activity intensity is a defensible demand proxy; diminishing returns expected at extreme "
        "density (see value function), but not reversed the way population density might be.")
    add("poi_entropy", "Demand/Activity Potential", "RETAIN", "BENEFIT",
        "Land-use/activity-type diversity (mixed-use character) plausibly supports varied trip purposes "
        "throughout the day, distinct from raw activity volume.")
    add("retail_count", "Demand/Activity Potential", "RETAIN", "BENEFIT",
        "Retail destinations are classic short-trip generators well-suited to micromobility.")
    add("leisure_count", "Demand/Activity Potential", "RETAIN", "BENEFIT",
        "Leisure/recreational destinations represent a distinct trip purpose from retail/commercial.")
    for c in ["hospital_count", "university_count", "school_count", "healthcare_count", "cafe_count",
              "restaurant_count", "bar_pub_count", "supermarket_count", "office_count", "tourism_count"]:
        add(c, "Demand/Activity Potential", "EXCLUDE_REDUNDANT", "N/A",
            "Individual POI sub-category; its contribution to overall activity intensity is already captured "
            "by poi_density_km2, and food/retail/leisure-specific demand nuance would require a dedicated "
            "sub-index this phase does not construct. Kept out of the compact criterion set to avoid "
            "over-weighting POI-derived signal relative to other dimensions.",
            represented_by="poi_density_km2 (general); retail_count/leisure_count (specific facets retained)")
    add("total_poi_count", "Demand/Activity Potential", "EXCLUDE_REDUNDANT", "N/A",
        "Sum of the 12 POI categories; redundant with the density (per-area-normalized) form.",
        represented_by="poi_density_km2")
    add("poi_category_count", "Demand/Activity Potential", "EXCLUDE_REDUNDANT", "N/A",
        "Category-diversity count is highly correlated with poi_entropy, which captures the same concept "
        "(mixed-use diversity) more informatively (weighted by category share, not just presence/absence).",
        represented_by="poi_entropy")
    add("population_worldpop_raw", "Demand/Activity Potential", "EXCLUDE_REDUNDANT", "N/A",
        "Superseded by the district-calibrated estimate.", represented_by="population_density_calibrated_km2")
    add("population_calibrated", "Demand/Activity Potential", "EXCLUDE_REDUNDANT", "N/A",
        "Raw count is area-dependent; density is the comparable, scale-free form.",
        represented_by="population_density_calibrated_km2")
    add("population_density_worldpop_raw_km2", "Demand/Activity Potential", "EXCLUDE_REDUNDANT", "N/A",
        "Superseded by the district-calibrated estimate.", represented_by="population_density_calibrated_km2")

    # --- Urban Form ---
    add("has_buildings", "Urban Form", "RETAIN", "BENEFIT",
        "Presence of any built environment is a minimal precondition for meaningful pedestrian/cyclist "
        "activity and safe operating space; a natural 0/1 threshold criterion.")
    add("building_coverage_ratio_conditional", "Urban Form", "RETAIN", "CONTEXT_DEPENDENT",
        "Conditional on buildings being present, moderate coverage plausibly indicates walkable, active "
        "street frontage; extremely high coverage can mean narrow streets, no curb space, and difficult "
        "vehicle staging/parking -- an inverted-U is plausible, not assumed monotonic.")
    add("building_coverage_ratio", "Urban Form", "EXCLUDE_REDUNDANT", "N/A",
        "Superseded by the two-part representation (has_buildings + building_coverage_ratio_conditional) "
        "adopted in Phase 5C to fix its extreme-skew clustering-dominance problem; the same fix is carried "
        "into the MCDA criteria set for consistency.",
        represented_by="has_buildings / building_coverage_ratio_conditional")
    add("building_count", "Urban Form", "EXCLUDE_REDUNDANT", "N/A",
        "Correlated with coverage ratio; ratio is the scale-free, more interpretable form.",
        represented_by="has_buildings / building_coverage_ratio_conditional")
    add("building_footprint_area_m2", "Urban Form", "EXCLUDE_REDUNDANT", "N/A",
        "Correlated with coverage ratio.", represented_by="building_coverage_ratio_conditional")
    add("mean_building_footprint_m2", "Urban Form", "EXCLUDE_REDUNDANT", "N/A",
        "0-filled placeholder for an undefined mean on zero-building cells (see Phase 5A); average building "
        "SIZE is also not a clearly-directional suitability signal.", represented_by="has_buildings")

    # --- Mobility / Transit Context (ambiguous per explicit instruction) ---
    transit_note = ("Transit proximity/service is explicitly ambiguous for e-bike/shared-micromobility "
                     "suitability: moderate presence plausibly supports first/last-mile integration, but very "
                     "strong direct transit provision may substitute for some e-bike trips. Marked "
                     "CONTEXT_DEPENDENT rather than forced into a simple benefit or cost direction, per instruction.")
    for c in ["distance_to_nearest_metro_m", "distance_to_nearest_tram_m", "distance_to_nearest_rail_m",
              "distance_to_nearest_ferry_m", "distance_to_nearest_metrobus_m", "distance_to_nearest_transit_m"]:
        add(c, "Mobility/Transit Context", "RETAIN", "CONTEXT_DEPENDENT", transit_note)
    for c in ["metro_station_count", "tram_station_count", "rail_station_count", "ferry_terminal_count",
              "metrobus_station_count"]:
        add(c, "Mobility/Transit Context", "EXCLUDE_REDUNDANT", "N/A",
            "Presence-count is redundant with the corresponding distance-to-nearest measure for a 500m cell; "
            "distance is the finer-grained, more informative form.",
            represented_by="the corresponding distance_to_nearest_*_m criterion")
    add("transit_stops_within_500m", "Mobility/Transit Context", "RETAIN", "CONTEXT_DEPENDENT", transit_note)
    add("transit_stops_within_1000m", "Mobility/Transit Context", "EXCLUDE_REDUNDANT", "N/A",
        "Correlated with the 500m radius version at this grid resolution.",
        represented_by="transit_stops_within_500m")
    add("fixed_guideway_stations_within_1000m", "Mobility/Transit Context", "RETAIN", "CONTEXT_DEPENDENT",
        transit_note + " Distinguished from generic transit_stops_within_500m as specifically capturing "
        "higher-capacity (metro/tram/rail) integration potential.")
    add("unique_rail_lines", "Mobility/Transit Context", "EXCLUDE_REDUNDANT", "N/A",
        "Correlated with fixed_guideway_stations_within_1000m.", represented_by="fixed_guideway_stations_within_1000m")
    add("bus_departures_per_day", "Mobility/Transit Context", "RETAIN", "CONTEXT_DEPENDENT",
        transit_note + " Represents current, non-stale service intensity (İETT feed), distinct from "
        "infrastructure presence.")
    add("bus_departures_peak_hour", "Mobility/Transit Context", "EXCLUDE_REDUNDANT", "N/A",
        "Highly correlated with daily departures at this scale.", represented_by="bus_departures_per_day")
    add("number_of_transit_modes_accessible", "Mobility/Transit Context", "EXCLUDE_REDUNDANT", "N/A",
        "Derived from the same underlying distances/counts already retained individually.",
        represented_by="the individual distance_to_nearest_*_m criteria")
    add("bus_stops_within_500m", "Mobility/Transit Context", "EXCLUDE_REDUNDANT", "N/A",
        "Subset of transit_stops_within_500m (bus is the dominant mode); pooled measure preferred.",
        represented_by="transit_stops_within_500m")
    add("routes_serving_grid", "Mobility/Transit Context", "EXCLUDE_REDUNDANT", "N/A",
        "Correlated with bus_departures_per_day / stop counts.", represented_by="bus_departures_per_day")
    add("unique_bus_routes", "Mobility/Transit Context", "EXCLUDE_REDUNDANT", "N/A",
        "Correlated with bus_departures_per_day.", represented_by="bus_departures_per_day")
    add("total_transit_stop_count", "Mobility/Transit Context", "EXCLUDE_REDUNDANT", "N/A",
        "Sum of the individual mode counts already excluded in favor of distances.",
        represented_by="transit_stops_within_500m")
    add("bus_stop_count", "Mobility/Transit Context", "EXCLUDE_REDUNDANT", "N/A",
        "Presence-count redundant with the pooled distance/radius measures.",
        represented_by="distance_to_nearest_transit_m / transit_stops_within_500m")
    add("distance_to_nearest_bus_stop_m", "Mobility/Transit Context", "EXCLUDE_REDUNDANT", "N/A",
        "Correlated with the pooled distance_to_nearest_transit_m (bus is the dominant/most ubiquitous mode).",
        represented_by="distance_to_nearest_transit_m")
    add("rail_stations_within_1000m", "Mobility/Transit Context", "EXCLUDE_REDUNDANT", "N/A",
        "Exact duplicate of fixed_guideway_stations_within_1000m (deprecated alias).",
        represented_by="fixed_guideway_stations_within_1000m")

    # --- Cycling Readiness (ambiguous per explicit instruction) ---
    cycling_note = ("Existing cycling/micromobility infrastructure is explicitly ambiguous: presence may "
                     "indicate deployment readiness and rider safety, OR its absence in a high-demand area may "
                     "indicate unmet need rather than unsuitability. This criterion feeds the READINESS "
                     "dimension as BENEFIT; the same underlying signal (inverted) also feeds the NEED/"
                     "OPPORTUNITY dimension -- see readiness_need_architecture.json. Not resolved to a single "
                     "direction here.")
    add("cycle_infrastructure_density_km_per_km2_ibb_only", "Cycling Readiness", "RETAIN", "CONTEXT_DEPENDENT", cycling_note)
    add("protected_cycleway_density_km_per_km2_ibb_only", "Cycling Readiness", "RETAIN", "CONTEXT_DEPENDENT",
        cycling_note + " Distinguished from the general density as specifically physically-separated (safer) "
        "infrastructure.")
    add("distance_to_nearest_cycle_infrastructure_m_ibb_only", "Cycling Readiness", "RETAIN", "CONTEXT_DEPENDENT", cycling_note)
    add("distance_to_nearest_bicycle_parking_m", "Cycling Readiness", "RETAIN", "CONTEXT_DEPENDENT",
        "Same readiness-vs-prior-deployment ambiguity as cycling infrastructure: existing parking may reflect "
        "institutional readiness OR may partly encode where past deployment decisions were already made.")
    add("bicycle_parking_count", "Cycling Readiness", "EXCLUDE_REDUNDANT", "N/A",
        "Correlated with the corresponding distance measure at this grid resolution; distance is more "
        "informative for a mostly-sparse point layer.", represented_by="distance_to_nearest_bicycle_parking_m")
    add("distance_to_nearest_micromobility_parking_m", "Cycling Readiness", "RETAIN", "CONTEXT_DEPENDENT",
        "Same institutional-readiness-vs-prior-deployment ambiguity, for scooter/e-bike-oriented parking "
        "specifically (distinct facility type from bicycle-specific parking).")
    add("micromobility_parking_count", "Cycling Readiness", "EXCLUDE_REDUNDANT", "N/A",
        "Correlated with the corresponding distance measure.", represented_by="distance_to_nearest_micromobility_parking_m")
    add("cycle_infrastructure_length_km_ibb_only", "Cycling Readiness", "EXCLUDE_REDUNDANT", "N/A",
        "Length is area-dependent; density is the scale-free form.", represented_by="cycle_infrastructure_density_km_per_km2_ibb_only")
    add("protected_cycleway_length_km_ibb_only", "Cycling Readiness", "EXCLUDE_REDUNDANT", "N/A",
        "Length is area-dependent; density is the scale-free form.", represented_by="protected_cycleway_density_km_per_km2_ibb_only")
    add("pct_road_network_with_cycle_infrastructure_status", "Cycling Readiness", "EXCLUDE_PENDING", "N/A",
        "Explicit PENDING_ROAD_NETWORK status sentinel, not a usable numeric criterion yet.")

    # --- Terrain Feasibility ---
    terrain_note = (f"e-bikes tolerate slope substantially better than conventional bicycles (the pilot's frozen "
                     f"methodology treats slope as comfortable below {EBIKE_SLOPE_COMFORTABLE_DEG} deg, still "
                     f"e-bike-manageable up to {EBIKE_SLOPE_STEEP_DEG} deg, with a floor of "
                     f"{EBIKE_SLOPE_FLOOR} to avoid rewarding perfectly flat terrain arbitrarily), but very "
                     "steep terrain remains operationally undesirable regardless of motor assistance (safety, "
                     "battery drain, braking). Treated as COST with a shallow-then-steepening penalty, not a "
                     "simple linear cost, reusing the frozen pilot thresholds rather than inventing new ones.")
    add("mean_slope_deg", "Terrain Feasibility", "RETAIN", "COST", terrain_note)
    add("pct_area_slope_3_6deg", "Terrain Feasibility", "RETAIN", "COST",
        "Share of cell area in the mildly-sloped band -- supports a piecewise/threshold value function alongside mean_slope_deg.")
    add("pct_area_slope_6_10deg", "Terrain Feasibility", "RETAIN", "COST",
        "Share of cell area approaching the steep threshold -- distinguishes cells with a mild mean slope but "
        "a substantial steep sub-area from uniformly mild cells.")
    add("pct_area_slope_lt_3deg", "Terrain Feasibility", "EXCLUDE_REDUNDANT", "N/A",
        "Complementary share; retaining the two higher bands is sufficient to characterize the slope profile "
        "without triple-counting (all four bands sum to 100%).", represented_by="mean_slope_deg (overall summary)")
    add("pct_area_slope_gt_10deg", "Terrain Feasibility", "EXCLUDE_REDUNDANT", "N/A",
        "Correlated with mean_slope_deg/max_slope_deg at this resolution; the two retained mid-range bands "
        "already capture the comfortable-to-steep transition relevant to e-bikes.",
        represented_by="mean_slope_deg")
    for c in ["median_elevation_m", "max_elevation_m", "min_elevation_m", "elevation_range_m", "elevation_std_m",
              "median_slope_deg", "max_slope_deg", "slope_std_deg"]:
        add(c, "Terrain Feasibility", "EXCLUDE_REDUNDANT", "N/A",
            "Redundant summary statistic of the same elevation/slope distribution.", represented_by="mean_slope_deg")
    add("mean_elevation_m", "Terrain Feasibility", "EXCLUDE_NOT_DECISION_RELEVANT", "N/A",
        "Absolute elevation has no direct operational relevance to e-bike suitability -- it is GRADE (slope), "
        "not height above sea level, that affects rider effort/safety and battery use.",
        represented_by="mean_slope_deg")
    add("n_valid_dem_pixels", "Terrain Feasibility", "EXCLUDE_NOT_DECISION_RELEVANT", "N/A",
        "Coverage diagnostic, not a substantive criterion.")
    add("road_grade_status", "Terrain Feasibility", "EXCLUDE_PENDING", "N/A",
        "Explicit PENDING_ROAD_NETWORK status sentinel -- road-grade (as opposed to terrain slope) requires "
        "the citywide road network, still unavailable.")

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 2. Value function proposals (for RETAINed criteria only)
# --------------------------------------------------------------------------

def build_value_functions() -> pd.DataFrame:
    rows = []

    def add(name, family_type, proposal, params_note):
        rows.append({"feature_name": name, "value_function_type": family_type, "proposal": proposal, "parameters_and_caveats": params_note})

    add("population_density_calibrated_km2", "NON_MONOTONIC / target-range (candidate)",
        "Percentile-based scenario: increasing benefit up to ~p75-p85 citywide, then flat or mildly declining "
        "beyond ~p90-p95 to reflect saturation/operational-constraint concerns.",
        "No defensible physical density threshold identified; percentile breakpoints are a transparent "
        "placeholder, not a claimed empirical saturation point -- to be set as a scenario parameter, not fixed here.")
    add("poi_density_km2", "Saturation / diminishing returns",
        "Monotonic increasing, concave (e.g. sqrt or log1p of the percentile rank) so the top few extreme-"
        "activity cells do not dominate the value function the way raw density would.",
        "Diminishing returns rationale: marginal suitability gain from 'very high' to 'extremely high' "
        "activity is plausibly smaller than from 'low' to 'moderate'.")
    add("poi_entropy", "Monotonic increasing", "Linear percentile-rank benefit.", "Bounded metric (bits); already well-behaved, no transform needed beyond percentile-ranking.")
    add("retail_count", "Saturation / diminishing returns", "Same concave treatment as poi_density_km2.", "Sparse, zero-inflated -- percentile rank computed with zero as a genuine floor, not imputed.")
    add("leisure_count", "Saturation / diminishing returns", "Same concave treatment as poi_density_km2.", "Same sparsity handling as retail_count.")
    add("has_buildings", "Threshold (step)", "0 -> minimum value; 1 -> full eligibility to be scored on building_coverage_ratio_conditional.", "Binary by construction; not a continuous value function.")
    add("building_coverage_ratio_conditional", "Target-range / inverted-U (candidate)",
        "Benefit rising through low-to-moderate coverage, plateauing or mildly declining at extreme coverage "
        "(candidate breakpoint: citywide p85-p90 among built cells).",
        "No defensible physical breakpoint (e.g. a specific street-width or curb-space threshold) identified "
        "from available data -- percentile-based, to be set as a scenario parameter.")
    for c in ["distance_to_nearest_metro_m", "distance_to_nearest_tram_m", "distance_to_nearest_rail_m",
              "distance_to_nearest_ferry_m", "distance_to_nearest_metrobus_m", "distance_to_nearest_transit_m"]:
        add(c, "Inverted-U / target-range (unresolved)",
            "Candidate shape: low suitability when extremely close (substitution risk) and when very far (no "
            "integration benefit), higher suitability at a moderate 'sweet spot' distance.",
            "No defensible distance thresholds for the substitution vs. integration crossover are established "
            "in the literature reviewed for this project; this is flagged as an UNRESOLVED methodological "
            "choice requiring a decision (e.g. a specific scenario assumption) before scoring, not silently "
            "defaulted to monotonic.")
    for c in ["transit_stops_within_500m", "fixed_guideway_stations_within_1000m", "bus_departures_per_day"]:
        add(c, "Inverted-U / target-range (unresolved)", "Same substitution-vs-integration ambiguity as distance measures, expressed as a count/intensity rather than a distance.", "Same unresolved-threshold caveat.")
    for c in ["cycle_infrastructure_density_km_per_km2_ibb_only", "protected_cycleway_density_km_per_km2_ibb_only"]:
        add(c, "Dual-direction (readiness vs. need) -- not resolved to one function here",
            "Under READINESS: monotonic increasing (more existing infrastructure = safer, more ready). Under "
            "NEED/OPPORTUNITY: monotonic DECREASING conditional on high demand (low infrastructure + high "
            "demand = latent opportunity), mirroring the pilot's frozen Latent Opportunity Gap concept.",
            "Direction depends entirely on which of the two indices (readiness or need) this feeds -- see "
            "readiness_need_architecture.json. Not combined into one number in this phase.")
    for c in ["distance_to_nearest_cycle_infrastructure_m_ibb_only", "distance_to_nearest_bicycle_parking_m",
              "distance_to_nearest_micromobility_parking_m"]:
        add(c, "Dual-direction (readiness vs. need) -- not resolved to one function here",
            "Under READINESS: monotonic decreasing (closer = more ready). Under NEED/OPPORTUNITY: farther, "
            "conditional on high demand, indicates a service gap.",
            "Same dual-direction caveat as the density measures above.")
    add("mean_slope_deg", "Piecewise / threshold (reuses frozen pilot thresholds)",
        f"Comfortable (full value) below {EBIKE_SLOPE_COMFORTABLE_DEG} deg, linearly or convexly declining "
        f"toward a floor of {EBIKE_SLOPE_FLOOR} by {EBIKE_SLOPE_STEEP_DEG} deg, floor held beyond.",
        "Reuses src.analysis.suitability_config's frozen e-bike-specific slope treatment exactly -- no new threshold invented.")
    for c in ["pct_area_slope_3_6deg", "pct_area_slope_6_10deg"]:
        add(c, "Piecewise (supporting mean_slope_deg)",
            "Used as a secondary/tie-breaking signal alongside mean_slope_deg rather than an independent "
            "value function -- e.g. penalizing a cell whose mean is mild but whose steep-area share is high.",
            "Exact combination rule (e.g. weighted penalty) deferred to scoring phase.")

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 3. Readiness vs. Need/Opportunity architecture
# --------------------------------------------------------------------------

def build_readiness_need_architecture() -> dict:
    return {
        "recommendation": (
            "YES -- construct two separate dimensions (Readiness, Need/Opportunity) rather than one immediate "
            "suitability index. Several retained criteria (cycling infrastructure density/proximity, parking "
            "density/proximity) have a direction that depends on which question is being asked, and Phase 5C's "
            "robustness audit already showed the citywide typology's structure is sensitive to how such "
            "criteria are combined -- collapsing them into one number now would hide that ambiguity rather "
            "than resolve it."
        ),
        "deployment_readiness": {
            "definition": "How ready is this cell's existing environment to support safe, integrated "
            "station-free e-bike operation right now?",
            "candidate_criteria": [
                "has_buildings (BENEFIT)", "building_coverage_ratio_conditional (CONTEXT_DEPENDENT, inverted-U)",
                "cycle_infrastructure_density_km_per_km2_ibb_only (BENEFIT direction)",
                "protected_cycleway_density_km_per_km2_ibb_only (BENEFIT direction)",
                "distance_to_nearest_cycle_infrastructure_m_ibb_only (COST direction, i.e. closer=better)",
                "distance_to_nearest_bicycle_parking_m (COST direction)",
                "distance_to_nearest_micromobility_parking_m (COST direction)",
                "transit accessibility criteria, moderate-proximity framing (CONTEXT_DEPENDENT)",
            ],
        },
        "potential_need_opportunity": {
            "definition": "How much latent demand exists that current cycling/micromobility provision does "
            "not yet serve? Directly parallels the pilot's frozen Latent Opportunity Gap concept "
            "(non-infrastructure composite minus cycling-infrastructure score), now considered for a two-"
            "dimension readiness/need architecture rather than a single gap score.",
            "candidate_criteria": [
                "population_density_calibrated_km2 (demand side, CONTEXT_DEPENDENT re: saturation)",
                "poi_density_km2, poi_entropy, retail_count, leisure_count (demand side, BENEFIT)",
                "cycle_infrastructure_density_km_per_km2_ibb_only (need direction, i.e. LOW = higher latent need, conditional on high demand)",
                "distance_to_nearest_bicycle_parking_m / micromobility_parking_m (need direction, i.e. FAR = higher latent need, conditional on high demand)",
            ],
        },
        "explicit_non_combination": (
            "This phase does NOT combine readiness and need/opportunity into one score, and does NOT compute "
            "either dimension's value for any cell. That is scoring work for a later phase, contingent on "
            "resolving the unresolved value-function questions logged here (especially the transit and "
            "cycling-infrastructure dual-direction ambiguities)."
        ),
    }


# --------------------------------------------------------------------------
# 4. Weighting scenarios (conceptual-dimension level, NOT selected/final)
# --------------------------------------------------------------------------

def build_weighting_scenarios() -> pd.DataFrame:
    dims = ["Demand/Activity Potential", "Urban Form", "Mobility/Transit Context", "Cycling Readiness", "Terrain Feasibility"]
    scenarios = {
        "balanced_equal_dimensions": {d: round(1 / len(dims), 3) for d in dims},
        "demand_oriented": {"Demand/Activity Potential": 0.40, "Urban Form": 0.15, "Mobility/Transit Context": 0.15, "Cycling Readiness": 0.15, "Terrain Feasibility": 0.15},
        "infrastructure_readiness_oriented": {"Demand/Activity Potential": 0.15, "Urban Form": 0.15, "Mobility/Transit Context": 0.15, "Cycling Readiness": 0.40, "Terrain Feasibility": 0.15},
        "first_last_mile_transit_integration_oriented": {"Demand/Activity Potential": 0.15, "Urban Form": 0.10, "Mobility/Transit Context": 0.45, "Cycling Readiness": 0.15, "Terrain Feasibility": 0.15},
    }
    rows = []
    for scenario, weights in scenarios.items():
        for d, w in weights.items():
            rows.append({"scenario": scenario, "dimension": d, "dimension_weight": w})
    df = pd.DataFrame(rows)
    df["note"] = (
        "Dimension weights only -- NOT final. Within-dimension distribution is explicitly EQUAL across "
        "retained criteria in that dimension by default (documented, not computed here), so a dimension with "
        "more retained criteria does not automatically receive more total influence than one with fewer; a "
        "criterion-level weight table is scoring-phase work, contingent on resolving the logged unresolved "
        "value-function choices."
    )
    return df


def main() -> None:
    print("=" * 72)
    print("Phase 6A: E-bike Deployment Suitability Criteria Architecture")
    print("=" * 72)
    MCDA_DIR.mkdir(parents=True, exist_ok=True)

    catalog = build_catalog()
    catalog.to_csv(MCDA_DIR / "criteria_catalog.csv", index=False)
    print(f"\n[save] criteria_catalog.csv ({len(catalog)} predictors catalogued)")
    print(catalog["mcda_disposition"].value_counts())

    redundancy_log = catalog[catalog["mcda_disposition"].str.startswith("EXCLUDE")].copy()
    redundancy_log.to_csv(MCDA_DIR / "criteria_redundancy_log.csv", index=False)
    print(f"[save] criteria_redundancy_log.csv ({len(redundancy_log)} excluded predictors, each mapped to a retained representative where applicable)")

    retained = catalog[catalog["mcda_disposition"] == "RETAIN"].copy()
    print(f"\nRetained criteria: {len(retained)}")
    print(retained.groupby(["dimension", "direction"]).size())

    value_functions = build_value_functions()
    value_functions.to_csv(MCDA_DIR / "value_function_proposals.csv", index=False)
    print(f"\n[save] value_function_proposals.csv ({len(value_functions)} proposals)")

    readiness_need = build_readiness_need_architecture()
    (MCDA_DIR / "readiness_need_architecture.json").write_text(json.dumps(readiness_need, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[save] readiness_need_architecture.json")

    weighting = build_weighting_scenarios()
    weighting.to_csv(MCDA_DIR / "weighting_scenarios_proposed.csv", index=False)
    print(f"[save] weighting_scenarios_proposed.csv ({weighting['scenario'].nunique()} scenarios)")

    # --- Typology cross-tab (interpretation only) ---
    print("\nCross-tabulating retained criteria against the Phase 5C k=5 typology (interpretation only)...")
    master = gpd.read_parquet(cfg.DATA_PROCESSED / "features" / "urban_mobility_features_citywide.parquet")
    assignments = pd.read_parquet(CLUSTER_V2_DIR / "cluster_assignments_v2.parquet")

    retained_names = [c for c in retained["feature_name"] if c in master.columns]
    df = master[["grid_id"] + retained_names].merge(assignments[["grid_id", "cluster"]], on="grid_id")
    crosstab = df.groupby("cluster")[retained_names].median()
    crosstab.insert(0, "n_cells", df["cluster"].value_counts().sort_index())
    crosstab.to_csv(MCDA_DIR / "typology_criteria_crosstab.csv")
    print(f"[save] typology_criteria_crosstab.csv (median of each retained criterion by k=5 cluster -- interpretation only, no weights/labels assigned)")

    unresolved = [
        "Transit proximity/service direction (substitution vs. integration) -- no defensible distance/"
        "frequency threshold identified for the crossover point.",
        "Cycling infrastructure and parking direction depends on whether it feeds Readiness or Need/"
        "Opportunity -- both are logged, neither is chosen as 'the' direction.",
        "Population density and building coverage saturation breakpoints are percentile-based placeholders, "
        "not empirically defensible physical thresholds -- need a scenario decision before scoring.",
        "Whether Readiness and Need/Opportunity are ultimately combined (and how) or reported as two "
        "separate maps/dimensions is NOT decided in this phase.",
        "Final within-dimension criterion weights (vs. the default equal-split assumption used for the "
        "scenario table) are not set.",
        "Which weighting scenario (or blend) to adopt is not decided.",
    ]

    summary = {
        "n_eligible_predictors_reviewed": len(catalog),
        "n_retained_criteria": len(retained),
        "n_excluded_redundant": int((catalog["mcda_disposition"] == "EXCLUDE_REDUNDANT").sum()),
        "n_excluded_not_decision_relevant": int((catalog["mcda_disposition"] == "EXCLUDE_NOT_DECISION_RELEVANT").sum()),
        "n_excluded_pending_dependency": int((catalog["mcda_disposition"] == "EXCLUDE_PENDING").sum()),
        "dimensions": sorted(retained["dimension"].unique().tolist()),
        "direction_counts": retained["direction"].value_counts().to_dict(),
        "readiness_need_recommendation": readiness_need["recommendation"],
        "weighting_scenarios": sorted(weighting["scenario"].unique().tolist()),
        "typology_used_for_interpretation_only": True,
        "limitations": [
            "No citywide road-network features (PARTIAL, 0/39 districts) -- road-grade and pct-cycle-infra-"
            "coverage-of-roads criteria remain PENDING_DEPENDENCY, excluded here.",
            "No complete citywide land-use/green-space features (PARTIAL, 22/39 districts) -- no land-use "
            "dimension exists in this architecture; its absence is not treated as zero.",
            "WorldPop reference year (2020) vs. official calibration source (2020, matched) vs. OSM/GTFS "
            "(2026) -- population criteria are several years older than most other criteria.",
            "main_gtfs (metro/tram/rail/ferry) infrastructure snapshot is from 2023-2024, not current -- "
            "transit criteria involving these modes may not reflect newly opened lines.",
            "Cycling infrastructure/parking criteria are İBB-only (OSM complement excluded per prior "
            "instruction) -- a definitionally narrower inventory than the pilot's combined source.",
            "No observed shared e-bike demand or deployment data exists anywhere in this project -- every "
            "criterion here is a plausibility-based proxy, not a validated demand driver. No causal claim is "
            "made or implied by any BENEFIT/COST direction in this catalog.",
        ],
        "unresolved_methodological_choices_before_scoring": unresolved,
    }
    (MCDA_DIR / "phase6a_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[save] phase6a_summary.json")


if __name__ == "__main__":
    main()
