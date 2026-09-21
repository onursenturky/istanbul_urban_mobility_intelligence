"""Phase 6B: Scenario-Based Readiness and Latent Opportunity Scoring.

Uses ONLY the 24 criteria RETAINed in the frozen Phase 6A catalog.
Computes two permanently SEPARATE families of scores -- Deployment
Readiness and Latent Opportunity/Need -- under multiple transparent
scenarios, with sensitivity analysis. No single "suitability" score is
ever produced.

Dimension scores (each bounded [0,1]):
  - Demand / Activity Potential      (5 criteria)
  - Urban Form                        (2 criteria: has_buildings, conditional coverage)
  - Mobility / Transit Context        (9 criteria; T1 integration vs T2 substitution variants)
  - Cycling Readiness                 (5 criteria, BENEFIT direction)
  - Terrain Feasibility               (3 criteria, overlap-aware combination)
  - Cycling Infrastructure Gap        (the SAME 5 cycling criteria, inverted -- for Opportunity only)

Readiness (per scenario, per transit variant) = weighted sum of
{Urban Form, Mobility/Transit(T1|T2), Cycling Readiness, Terrain}, weights
renormalized from each Phase 6A scenario's 5-dimension vector after
dropping Demand.

Opportunity (per scenario, per demand variant) = demand_potential^alpha *
infrastructure_gap^(1-alpha), where alpha is each scenario's Demand share
renormalized against {Demand, Cycling Readiness} only. This is a bounded,
multiplicative form: a cell with ZERO demand potential gets ZERO
opportunity regardless of how large its infrastructure gap is -- directly
preventing remote, empty cells from registering as "opportunities" purely
because infrastructure happens to be absent there.
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.bcr_preprocessing_candidates import build_candidate_D
from src.utils import config as cfg

MCDA_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda"
OUT_DIR = MCDA_DIR / "phase6b"
MAPS_DIR = OUT_DIR / "maps"

EBIKE_SLOPE_COMFORTABLE_DEG = 3.0
EBIKE_SLOPE_STEEP_DEG = 10.0
EBIKE_SLOPE_FLOOR = 0.5

WEIGHTING_SCENARIOS = {
    "balanced_equal_dimensions": {"Demand/Activity Potential": 0.2, "Urban Form": 0.2, "Mobility/Transit Context": 0.2, "Cycling Readiness": 0.2, "Terrain Feasibility": 0.2},
    "demand_oriented": {"Demand/Activity Potential": 0.40, "Urban Form": 0.15, "Mobility/Transit Context": 0.15, "Cycling Readiness": 0.15, "Terrain Feasibility": 0.15},
    "infrastructure_readiness_oriented": {"Demand/Activity Potential": 0.15, "Urban Form": 0.15, "Mobility/Transit Context": 0.15, "Cycling Readiness": 0.40, "Terrain Feasibility": 0.15},
    "first_last_mile_transit_integration_oriented": {"Demand/Activity Potential": 0.15, "Urban Form": 0.10, "Mobility/Transit Context": 0.45, "Cycling Readiness": 0.15, "Terrain Feasibility": 0.15},
}


# --------------------------------------------------------------------------
# Value-function primitives (all operate on percentile rank r in [0,1])
# --------------------------------------------------------------------------

def pct_rank(x: pd.Series) -> np.ndarray:
    """Percentile rank using method='min' (not 'average'): a tied group
    receives the LOWEST rank in its tie, so a large tied-zero mass (common
    in count/density criteria -- e.g. 77% of cells have poi_density=0)
    correctly maps to percentile ~0, not the ~0.39 'average' ranking would
    give it. Using 'average' here was found (via the opportunity sanity
    check) to assign zero-activity cells a substantial saturating-benefit
    value purely from the tie-averaging artifact, not from any real signal
    -- the same class of bug already fixed once for building_coverage_ratio
    in Phase 5C, now also required for every zero-inflated MCDA criterion."""
    return (rankdata(x, method="min") - 1) / (len(x) - 1)


def saturating_benefit(x: pd.Series) -> np.ndarray:
    """Higher raw value -> higher value, diminishing returns (concave)."""
    return pct_rank(x) ** 0.5


def linear_benefit(x: pd.Series) -> np.ndarray:
    return pct_rank(x)


def saturating_cost(x: pd.Series) -> np.ndarray:
    """Lower raw value -> higher value (e.g. distance), diminishing returns."""
    return (1 - pct_rank(x)) ** 0.5


def target_range_from_rank(r: np.ndarray, low: float, high: float, floor: float) -> np.ndarray:
    """Rises linearly 0->1 over [0,low], flat at 1 over [low,high], declines
    linearly to `floor` over [high,1]. All breakpoints are explicit scenario
    assumptions, not empirical thresholds."""
    r = np.asarray(r, dtype=float)
    v = np.ones_like(r)
    rising = r < low
    v[rising] = r[rising] / low
    declining = r > high
    v[declining] = 1 - (r[declining] - high) / (1 - high) * (1 - floor)
    return v


def inverted_u_from_rank(r: np.ndarray, peak: float, floor_near: float, floor_far: float = 0.0) -> np.ndarray:
    """Peaks at rank=`peak`; declines toward `floor_far` as r->1 (far/low)
    and toward `floor_near` as r->0 (near/high) -- used for T2 substitution
    sensitivity, where extreme closeness is not maximally rewarded."""
    r = np.asarray(r, dtype=float)
    v = np.empty_like(r)
    far_side = r >= peak
    v[far_side] = floor_far + (1 - r[far_side]) / (1 - peak) * (1 - floor_far)
    near_side = ~far_side
    v[near_side] = floor_near + (r[near_side] / peak) * (1 - floor_near)
    return v


def slope_piecewise(x: pd.Series) -> np.ndarray:
    """Frozen pilot e-bike slope treatment: comfortable <=3 deg (value=1),
    linear decline to floor=0.5 by 10 deg, floor held beyond."""
    x = x.to_numpy(dtype=float)
    v = np.ones_like(x)
    mid = (x > EBIKE_SLOPE_COMFORTABLE_DEG) & (x <= EBIKE_SLOPE_STEEP_DEG)
    v[mid] = 1.0 - (x[mid] - EBIKE_SLOPE_COMFORTABLE_DEG) / (EBIKE_SLOPE_STEEP_DEG - EBIKE_SLOPE_COMFORTABLE_DEG) * (1.0 - EBIKE_SLOPE_FLOOR)
    v[x > EBIKE_SLOPE_STEEP_DEG] = EBIKE_SLOPE_FLOOR
    return v


def share_cost_floor(x: pd.Series, floor: float = EBIKE_SLOPE_FLOOR) -> np.ndarray:
    """For a 0-100 area-share COST criterion: 1.0 at 0% share, linear to
    `floor` at 100% share -- same floor convention as the slope treatment."""
    return 1.0 - (x.to_numpy(dtype=float) / 100.0) * (1.0 - floor)


# --------------------------------------------------------------------------
# Load data
# --------------------------------------------------------------------------

def load_data():
    master = gpd.read_parquet(cfg.DATA_PROCESSED / "features" / "urban_mobility_features_citywide.parquet")
    raw_bcr = master["building_coverage_ratio"]
    has_buildings, conditional_scaled, d_diag = build_candidate_D(raw_bcr)
    # We need the RAW conditional building coverage (not the log1p+RobustScaler
    # version used for clustering) for MCDA percentile value functions.
    built_mask = raw_bcr > 0
    df = master.copy()
    df["has_buildings"] = has_buildings
    df["building_coverage_ratio_conditional_raw"] = np.where(built_mask, raw_bcr, np.nan)
    return df, built_mask


def main() -> None:
    print("=" * 72)
    print("Phase 6B: Scenario-Based Readiness and Latent Opportunity Scoring")
    print("=" * 72)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MAPS_DIR.mkdir(parents=True, exist_ok=True)

    catalog = pd.read_csv(MCDA_DIR / "criteria_catalog.csv")
    retained = catalog[catalog["mcda_disposition"] == "RETAIN"].copy()
    assert len(retained) == 24, f"expected 24 retained criteria, found {len(retained)}"
    print(f"\nFrozen Phase 6A catalog: {len(retained)} retained criteria")

    df, built_mask = load_data()

    dim_criteria = {d: retained.loc[retained["dimension"] == d, "feature_name"].tolist() for d in retained["dimension"].unique()}
    for d, feats in dim_criteria.items():
        print(f"  {d}: {feats}")

    value_function_records = []

    def record(feat, dim, variant, func_desc):
        value_function_records.append({"feature_name": feat, "dimension": dim, "variant": variant, "value_function": func_desc})

    print("\n[1/6] Computing criterion value functions...")

    # --- Demand / Activity Potential (2 variants) ---
    demand_feats = dim_criteria["Demand/Activity Potential"]
    vf = pd.DataFrame(index=df.index)
    vf["poi_density_km2__sat"] = saturating_benefit(df["poi_density_km2"])
    record("poi_density_km2", "Demand", "sat", "percentile_rank ** 0.5 (concave, diminishing returns)")
    vf["poi_entropy__lin"] = linear_benefit(df["poi_entropy"])
    record("poi_entropy", "Demand", "lin", "percentile_rank (linear)")
    vf["retail_count__sat"] = saturating_benefit(df["retail_count"])
    record("retail_count", "Demand", "sat", "percentile_rank ** 0.5")
    vf["leisure_count__sat"] = saturating_benefit(df["leisure_count"])
    record("leisure_count", "Demand", "sat", "percentile_rank ** 0.5")

    r_pop = pct_rank(df["population_density_calibrated_km2"])
    vf["population_density__saturating"] = r_pop ** 0.5
    record("population_density_calibrated_km2", "Demand", "saturating", "percentile_rank ** 0.5 (Variant 1)")
    vf["population_density__target_range"] = target_range_from_rank(r_pop, low=0.5, high=0.85, floor=0.7)
    record("population_density_calibrated_km2", "Demand", "target_range",
           "Rising 0->1 over [p0,p50]; flat at 1 over [p50,p85]; declining to floor 0.7 over [p85,p100] "
           "(Variant 2 -- breakpoints p50/p85/floor=0.7 are explicit SCENARIO ASSUMPTIONS, not empirical thresholds)")

    demand_potential_saturating = vf[["poi_density_km2__sat", "poi_entropy__lin", "retail_count__sat", "leisure_count__sat", "population_density__saturating"]].mean(axis=1)
    demand_potential_target_range = vf[["poi_density_km2__sat", "poi_entropy__lin", "retail_count__sat", "leisure_count__sat", "population_density__target_range"]].mean(axis=1)

    # --- Urban Form (2 variants, using RAW conditional coverage among built cells) ---
    r_bcr = np.full(len(df), np.nan)
    r_bcr[built_mask.to_numpy()] = pct_rank(df.loc[built_mask, "building_coverage_ratio_conditional_raw"])
    bcr_sat = np.where(built_mask, r_bcr ** 0.5, 0.0)
    bcr_target = np.where(built_mask, target_range_from_rank(np.nan_to_num(r_bcr), low=0.5, high=0.85, floor=0.7), 0.0)
    record("has_buildings", "Urban Form", "binary", "0/1 threshold indicator, used directly")
    record("building_coverage_ratio_conditional", "Urban Form", "saturating",
           "Among built cells: percentile_rank(raw conditional coverage) ** 0.5; 0 for non-built cells (Variant 1)")
    record("building_coverage_ratio_conditional", "Urban Form", "target_range",
           "Among built cells: same [p50,p85,floor=0.7] target-range shape as population (Variant 2); 0 for non-built cells")

    urban_form_saturating = 0.5 * df["has_buildings"].to_numpy() + 0.5 * bcr_sat
    urban_form_target_range = 0.5 * df["has_buildings"].to_numpy() + 0.5 * bcr_target

    # --- Mobility / Transit Context (T1 integration vs T2 substitution) ---
    dist_feats = ["distance_to_nearest_metro_m", "distance_to_nearest_tram_m", "distance_to_nearest_rail_m",
                  "distance_to_nearest_ferry_m", "distance_to_nearest_metrobus_m", "distance_to_nearest_transit_m"]
    intensity_feats = ["transit_stops_within_500m", "fixed_guideway_stations_within_1000m", "bus_departures_per_day"]

    t1_cols, t2_cols = [], []
    for f in dist_feats:
        r = pct_rank(df[f])  # 0 = closest
        vf[f"{f}__T1"] = (1 - r) ** 0.5
        vf[f"{f}__T2"] = inverted_u_from_rank(r, peak=0.3, floor_near=0.6, floor_far=0.0)
        t1_cols.append(f"{f}__T1"); t2_cols.append(f"{f}__T2")
        record(f, "Transit", "T1_integration", "(1 - percentile_rank(distance)) ** 0.5 -- closer=better, diminishing returns")
        record(f, "Transit", "T2_substitution", "inverted-U peaking at the 70th-closeness percentile (rank=0.3), "
               "declining toward a floor of 0.6 for extreme closeness and 0.0 for extreme distance -- "
               "PEAK LOCATION AND FLOOR ARE SCENARIO ASSUMPTIONS, not an empirically validated crossover")
    for f in intensity_feats:
        r = pct_rank(df[f])
        vf[f"{f}__T1"] = r ** 0.5
        vf[f"{f}__T2"] = inverted_u_from_rank(r, peak=0.7, floor_near=0.6, floor_far=0.0)
        t1_cols.append(f"{f}__T1"); t2_cols.append(f"{f}__T2")
        record(f, "Transit", "T1_integration", "percentile_rank ** 0.5 -- more service=better, diminishing returns")
        record(f, "Transit", "T2_substitution", "inverted-U peaking at the 70th percentile of service intensity, "
               "declining toward 0.6 at the extreme high end -- SCENARIO ASSUMPTION")

    transit_T1 = vf[t1_cols].mean(axis=1)
    transit_T2 = vf[t2_cols].mean(axis=1)

    # --- Cycling Readiness (BENEFIT direction) + Infrastructure Gap (inverted) ---
    cyc_feats = dim_criteria["Cycling Readiness"]
    readiness_cols, gap_cols = [], []
    for f in cyc_feats:
        if "distance_to_nearest" in f:
            val = saturating_cost(df[f])  # closer = better
        else:
            val = saturating_benefit(df[f])  # more density = better
        vf[f"{f}__readiness"] = val
        vf[f"{f}__gap"] = 1 - val
        readiness_cols.append(f"{f}__readiness"); gap_cols.append(f"{f}__gap")
        record(f, "Cycling Readiness", "readiness", "percentile-rank-based saturating benefit/cost (see code); "
               "used directly for Readiness")
        record(f, "Cycling Infrastructure Gap", "gap", "1 - (the same criterion's Readiness value) -- Opportunity "
               "role only, never combined with Readiness's own use of this criterion")

    cycling_readiness = vf[readiness_cols].mean(axis=1)
    infrastructure_gap = vf[gap_cols].mean(axis=1)

    # --- Terrain Feasibility (overlap-aware, NOT equal-thirds) ---
    slope_val = slope_piecewise(df["mean_slope_deg"])
    band_6_10_val = share_cost_floor(df["pct_area_slope_6_10deg"])
    band_3_6_val = share_cost_floor(df["pct_area_slope_3_6deg"])
    record("mean_slope_deg", "Terrain", "piecewise", "Frozen pilot treatment: 1.0 <=3deg, linear decline to floor 0.5 "
           "by 10deg, floor held beyond. Weight 0.6 within Terrain (primary signal).")
    record("pct_area_slope_6_10deg", "Terrain", "share_cost", "1.0 at 0% steep-area share, linear to floor 0.5 at "
           "100% share. Weight 0.25 within Terrain (secondary: penalizes cells whose mean is moderate but whose "
           "steep sub-area is large).")
    record("pct_area_slope_3_6deg", "Terrain", "share_cost", "Same form. Weight 0.15 within Terrain (tertiary "
           "signal) -- weights are DELIBERATELY UNEQUAL (not 1/3 each) specifically to avoid triple-counting the "
           "same underlying slope information three times at full strength.")
    terrain_score = 0.6 * slope_val + 0.25 * band_6_10_val + 0.15 * band_3_6_val

    value_functions_df = pd.DataFrame(value_function_records)
    value_functions_df.to_csv(OUT_DIR / "criterion_value_functions.csv", index=False)
    print(f"  saved {OUT_DIR / 'criterion_value_functions.csv'} ({len(value_functions_df)} rows)")

    print("\n[2/6] Assembling dimension scores...")
    dims = pd.DataFrame({
        "grid_id": df["grid_id"], "district": df["district"],
        "demand_potential__saturating": demand_potential_saturating,
        "demand_potential__target_range": demand_potential_target_range,
        "urban_form__saturating": urban_form_saturating,
        "urban_form__target_range": urban_form_target_range,
        "transit__T1": transit_T1, "transit__T2": transit_T2,
        "cycling_readiness": cycling_readiness,
        "infrastructure_gap": infrastructure_gap,
        "terrain_feasibility": terrain_score,
    })
    for c in dims.columns:
        if c not in ("grid_id", "district"):
            assert dims[c].between(0, 1).all(), f"{c} out of [0,1] bounds"
    dims.to_parquet(OUT_DIR / "dimension_scores.parquet")
    print(f"  saved {OUT_DIR / 'dimension_scores.parquet'} -- all dimension scores verified in [0,1]")

    # Numeric verification: column-count independence
    print("\n  Verifying column-count independence: Transit (9 criteria) vs Terrain (3 criteria)...")
    print(f"    transit__T1 range: [{transit_T1.min():.3f}, {transit_T1.max():.3f}] (mean {transit_T1.mean():.3f})")
    print(f"    terrain_feasibility range: [{terrain_score.min():.3f}, {terrain_score.max():.3f}] (mean {terrain_score.mean():.3f})")
    print("    Both are single [0,1] dimension scores regardless of underlying criterion count; a dimension's "
          "influence on any scenario score is controlled ONLY by its scenario weight below, never by how many "
          "criteria were averaged to build it.")

    print("\n[3/6] Applying the 4 Phase 6A weighting scenarios...")
    weight_rows = []
    for scenario, w in WEIGHTING_SCENARIOS.items():
        assert abs(sum(w.values()) - 1.0) < 1e-9
        for d, wt in w.items():
            weight_rows.append({"scenario": scenario, "dimension": d, "weight": wt})
    weight_matrix = pd.DataFrame(weight_rows)
    weight_matrix.to_csv(OUT_DIR / "scenario_weight_matrix.csv", index=False)
    print(f"  saved {OUT_DIR / 'scenario_weight_matrix.csv'}")

    scenario_scores = pd.DataFrame({"grid_id": df["grid_id"], "district": df["district"]})
    for scenario, w in WEIGHTING_SCENARIOS.items():
        readiness_w_sum = w["Urban Form"] + w["Mobility/Transit Context"] + w["Cycling Readiness"] + w["Terrain Feasibility"]
        w_uf = w["Urban Form"] / readiness_w_sum
        w_tr = w["Mobility/Transit Context"] / readiness_w_sum
        w_cyc = w["Cycling Readiness"] / readiness_w_sum
        w_ter = w["Terrain Feasibility"] / readiness_w_sum

        for transit_variant, transit_col in [("T1", transit_T1), ("T2", transit_T2)]:
            for uf_variant, uf_col in [("sat", urban_form_saturating), ("tr", urban_form_target_range)]:
                readiness = w_uf * uf_col + w_tr * transit_col + w_cyc * cycling_readiness + w_ter * terrain_score
                scenario_scores[f"readiness__{scenario}__{transit_variant}__uf_{uf_variant}"] = readiness

        alpha = w["Demand/Activity Potential"] / (w["Demand/Activity Potential"] + w["Cycling Readiness"])
        for demand_variant, demand_col in [("sat", demand_potential_saturating), ("tr", demand_potential_target_range)]:
            opportunity = (demand_col.to_numpy() ** alpha) * (infrastructure_gap.to_numpy() ** (1 - alpha))
            scenario_scores[f"opportunity__{scenario}__demand_{demand_variant}"] = opportunity
            scenario_scores[f"demand_potential__{scenario}__demand_{demand_variant}"] = demand_col.to_numpy()
        scenario_scores[f"infrastructure_gap__{scenario}"] = infrastructure_gap.to_numpy()

    scenario_scores.to_parquet(OUT_DIR / "scenario_scores.parquet")
    print(f"  saved {OUT_DIR / 'scenario_scores.parquet'} ({len(scenario_scores.columns) - 2} score columns)")

    print("\n[4/6] Sanity checks on pathological cases...")
    run_sanity_checks(df, dims, scenario_scores, built_mask)

    print("\n[5/6] Scenario sensitivity + top-decile overlap + typology summary...")
    run_sensitivity(scenario_scores)

    print("\n[6/6] Maps...")
    make_maps(df, dims, scenario_scores)

    summary = {
        "n_retained_criteria": 24,
        "dimensions": list(dim_criteria.keys()) + ["Cycling Infrastructure Gap"],
        "weighting_scenarios": list(WEIGHTING_SCENARIOS.keys()),
        "transit_variants": ["T1_integration (diminishing-returns benefit)", "T2_substitution (inverted-U, peak at rank 0.3/0.7, floor 0.6)"],
        "demand_variants": ["saturating (percentile_rank**0.5)", "target_range (rising/flat/declining, breakpoints p50/p85, floor 0.7)"],
        "opportunity_formula": "demand_potential ** alpha * infrastructure_gap ** (1 - alpha), alpha = scenario's "
        "Demand weight / (Demand weight + Cycling Readiness weight) -- multiplicative, bounded [0,1], zero demand "
        "forces zero opportunity regardless of gap size.",
        "readiness_formula": "weighted sum of {Urban Form, Transit(T1|T2), Cycling Readiness, Terrain}, weights "
        "renormalized from each scenario's 5-dimension vector after excluding Demand.",
        "readiness_and_opportunity_never_combined": True,
        "no_scenario_selected_as_preferred": True,
        "no_districts_ranked": True,
        "limitations": [
            "No observed shared e-bike demand/deployment target exists anywhere in this project -- all scores "
            "are scenario-based decision-support indicators, not predicted demand or validated outcomes.",
            "No citywide road-network dimension (PARTIAL, 0/39 districts).",
            "No complete citywide land-use/green-space dimension (PARTIAL, 22/39 districts).",
            "Population reference year (2020) predates most other sources (OSM/GTFS 2026).",
            "main_gtfs (metro/tram/rail/ferry) infrastructure snapshot is from 2023-2024.",
            "Cycling infrastructure/parking criteria are İBB-only (OSM complement excluded).",
        ],
    }
    (OUT_DIR / "phase6b_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[save] {OUT_DIR / 'phase6b_summary.json'}")


def run_sanity_checks(df, dims, scenario_scores, built_mask):
    cases = []
    s = scenario_scores

    def add_case(label, mask, cols):
        if mask.sum() == 0:
            cases.append({"case": label, "n_cells": 0, "note": "no matching cells found"})
            return
        row = {"case": label, "n_cells": int(mask.sum())}
        for c in cols:
            row[f"mean_{c}"] = round(float(s.loc[mask, c].mean()), 4)
            row[f"max_{c}"] = round(float(s.loc[mask, c].max()), 4)
        cases.append(row)

    key_readiness = "readiness__balanced_equal_dimensions__T1__uf_sat"
    key_opportunity = "opportunity__balanced_equal_dimensions__demand_sat"
    key_gap = "infrastructure_gap__balanced_equal_dimensions"
    key_demand = "demand_potential__balanced_equal_dimensions__demand_sat"

    zero_pop_building = (df["population_density_calibrated_km2"] == 0) & (~built_mask)
    add_case("zero_population_AND_zero_building", zero_pop_building, [key_readiness, key_opportunity, key_demand, key_gap])

    remote_rural = (df["district"].isin(["Çatalca", "Silivri", "Şile"])) & (df["poi_density_km2"] == 0)
    add_case("remote_rural_Catalca_Silivri_Sile_zero_poi", remote_rural, [key_readiness, key_opportunity, key_demand, key_gap])

    dense_commercial = df["poi_density_km2"] > df["poi_density_km2"].quantile(0.99)
    add_case("dense_commercial_core_top1pct_poi", dense_commercial, [key_readiness, key_opportunity, key_demand, key_gap])

    transit_rich_cycling_poor = (df["distance_to_nearest_transit_m"] < df["distance_to_nearest_transit_m"].quantile(0.10)) & \
                                 (df["cycle_infrastructure_density_km_per_km2_ibb_only"] == 0)
    add_case("transit_rich_cycling_poor", transit_rich_cycling_poor, [key_readiness, key_opportunity, key_demand, key_gap])

    # poi_density_km2's 30th percentile is 0 (77% of all cells are exactly
    # zero), so "< p30" is vacuous (never true) for a strictly non-negative
    # variable -- using the median AMONG cells that actually have cycling
    # infrastructure instead, to get a meaningful "lower activity, relative
    # to other cycling-served cells" comparison group.
    has_cycling = df["cycle_infrastructure_density_km_per_km2_ibb_only"] > 0
    poi_median_among_cycling_served = df.loc[has_cycling, "poi_density_km2"].median()
    cycling_rich_low_demand = has_cycling & (df["poi_density_km2"] <= poi_median_among_cycling_served)
    add_case("cycling_rich_lower_demand", cycling_rich_low_demand, [key_readiness, key_opportunity, key_demand, key_gap])
    print(f"  (cycling_rich_lower_demand threshold: poi_density_km2 <= {poi_median_among_cycling_served:.2f}, "
          f"the median among the {has_cycling.sum()} cells that have any İBB cycling infrastructure at all)")

    steep = df["mean_slope_deg"] > EBIKE_SLOPE_STEEP_DEG
    add_case("steep_cells_over_10deg", steep, [key_readiness, key_opportunity, key_demand, key_gap])

    no_cycling_infra = df["cycle_infrastructure_density_km_per_km2_ibb_only"] == 0
    add_case("no_cycling_infrastructure_at_all", no_cycling_infra, [key_readiness, key_opportunity, key_demand, key_gap])

    sanity_df = pd.DataFrame(cases)
    sanity_df.to_csv(OUT_DIR / "sanity_check_cases.csv", index=False)
    print(sanity_df.to_string(index=False))

    # Explicit pathological-case assertions
    remote_opp = s.loc[remote_rural, key_opportunity]
    citywide_p90_opp = s[key_opportunity].quantile(0.90)
    citywide_p75_opp = s[key_opportunity].quantile(0.75)
    pct_remote_in_top_decile = (remote_opp >= citywide_p90_opp).mean() * 100
    pct_remote_in_top_quartile = (remote_opp >= citywide_p75_opp).mean() * 100
    print(f"\n  CRITICAL CHECK: remote rural (Çatalca/Silivri/Şile, zero POI), n={remote_rural.sum()} cells --")
    print(f"    mean opportunity={remote_opp.mean():.4f}, median={remote_opp.median():.4f} "
          f"(55.5% of ALL citywide cells have opportunity==0, so a citywide median comparison is uninformative)")
    print(f"    pct of these cells landing in the citywide TOP DECILE of opportunity: {pct_remote_in_top_decile:.2f}%")
    print(f"    pct of these cells landing in the citywide TOP QUARTILE of opportunity: {pct_remote_in_top_quartile:.2f}% "
          f"(vs. 25% expected if these cells were typical/unremarkable)")
    # The substantive test: infrastructure absence in a genuinely empty area
    # must not place cells in the CITYWIDE TOP DECILE of opportunity -- that
    # is the literal failure mode the user asked to rule out. A handful of
    # these cells retain trace residual population (the mask only filters on
    # poi_density==0, not population==0) so a small nonzero tail is expected
    # and acceptable; landing in the top decile is not.
    assert pct_remote_in_top_decile == 0.0, "FAILED: some remote empty cells land in the citywide top decile of opportunity"
    assert pct_remote_in_top_quartile < 25.0, "FAILED: remote empty cells are over-represented in the citywide top quartile"
    print("  PASSED: 0% of remote zero-POI cells reach the citywide top decile of opportunity, and they are "
          "under-represented (not over-represented) even in the top quartile -- infrastructure absence alone "
          "does not generate high opportunity.")


def run_sensitivity(scenario_scores: pd.DataFrame) -> None:
    readiness_cols = [c for c in scenario_scores.columns if c.startswith("readiness__")]
    opportunity_cols = [c for c in scenario_scores.columns if c.startswith("opportunity__")]

    sens_rows = []
    for cols, label in [(readiness_cols, "readiness"), (opportunity_cols, "opportunity")]:
        for i, a in enumerate(cols):
            for b in cols[i + 1:]:
                rho, _ = spearmanr(scenario_scores[a], scenario_scores[b])
                sens_rows.append({"score_type": label, "variant_a": a, "variant_b": b, "spearman_rho": round(float(rho), 4)})
    sens_df = pd.DataFrame(sens_rows)
    sens_df.to_csv(OUT_DIR / "scenario_sensitivity.csv", index=False)
    print(f"  saved scenario_sensitivity.csv ({len(sens_df)} pairwise comparisons)")
    print(f"  readiness pairwise rho: min={sens_df[sens_df.score_type=='readiness'].spearman_rho.min():.3f}, "
          f"max={sens_df[sens_df.score_type=='readiness'].spearman_rho.max():.3f}")
    print(f"  opportunity pairwise rho: min={sens_df[sens_df.score_type=='opportunity'].spearman_rho.min():.3f}, "
          f"max={sens_df[sens_df.score_type=='opportunity'].spearman_rho.max():.3f}")

    top_decile_rows = []
    n = len(scenario_scores)
    top_sets = {}
    for c in readiness_cols + opportunity_cols:
        thresh = scenario_scores[c].quantile(0.9)
        top_sets[c] = set(scenario_scores.index[scenario_scores[c] >= thresh])
    cols_all = readiness_cols + opportunity_cols
    for i, a in enumerate(cols_all):
        for b in cols_all[i + 1:]:
            inter = len(top_sets[a] & top_sets[b])
            union = len(top_sets[a] | top_sets[b])
            top_decile_rows.append({"variant_a": a, "variant_b": b, "jaccard_top_decile": round(inter / union, 4) if union else 0.0})
    top_decile_df = pd.DataFrame(top_decile_rows)
    top_decile_df.to_csv(OUT_DIR / "top_decile_overlap.csv", index=False)
    print(f"  saved top_decile_overlap.csv (stability diagnostic only, NOT a ranking)")

    # Consistently high/low cells
    scenario_scores["_n_top_decile_readiness"] = sum((scenario_scores[c] >= scenario_scores[c].quantile(0.9)).astype(int) for c in readiness_cols)
    scenario_scores["_n_top_decile_opportunity"] = sum((scenario_scores[c] >= scenario_scores[c].quantile(0.9)).astype(int) for c in opportunity_cols)
    consistently_high_readiness = int((scenario_scores["_n_top_decile_readiness"] == len(readiness_cols)).sum())
    consistently_high_opportunity = int((scenario_scores["_n_top_decile_opportunity"] == len(opportunity_cols)).sum())
    assumption_sensitive_readiness = int(((scenario_scores["_n_top_decile_readiness"] > 0) & (scenario_scores["_n_top_decile_readiness"] < len(readiness_cols))).sum())
    print(f"  cells in top decile under ALL {len(readiness_cols)} readiness variants: {consistently_high_readiness}")
    print(f"  cells in top decile under ALL {len(opportunity_cols)} opportunity variants: {consistently_high_opportunity}")
    print(f"  cells in top decile under SOME but not all readiness variants (assumption-sensitive): {assumption_sensitive_readiness}")

    # Typology cross-tab
    assignments = pd.read_parquet(cfg.PROJECT_ROOT / "analysis" / "clustering_v2" / "cluster_assignments_v2.parquet")
    merged = scenario_scores.merge(assignments[["grid_id", "cluster"]], on="grid_id")
    example_cols = ["readiness__balanced_equal_dimensions__T1__uf_sat", "readiness__balanced_equal_dimensions__T2__uf_sat",
                     "opportunity__balanced_equal_dimensions__demand_sat", "infrastructure_gap__balanced_equal_dimensions"]
    typology_summary = merged.groupby("cluster")[example_cols].agg(["mean", "median"])
    typology_summary.columns = [f"{c}_{s}" for c, s in typology_summary.columns]
    typology_summary.insert(0, "n_cells", merged["cluster"].value_counts().sort_index())
    typology_summary.to_csv(OUT_DIR / "typology_score_summary.csv")
    print(f"  saved typology_score_summary.csv (interpretation only, no suitability labels assigned)")


def make_maps(df, dims, scenario_scores) -> None:
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")[["grid_id", "geometry"]]
    districts_gdf = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    minx, miny, maxx, maxy = districts_gdf.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    extent = (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)

    plot_df = scenario_scores.merge(dims[["grid_id"]], on="grid_id").merge(grid, on="grid_id")
    plot_df = gpd.GeoDataFrame(plot_df, geometry="geometry", crs=cfg.METRIC_CRS)

    def _base(ax, title):
        districts_gdf.boundary.plot(ax=ax, linewidth=0.5, color="black", alpha=0.5, zorder=3)
        ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
        ax.set_title(title, fontsize=10)
        ax.set_axis_off()

    specs = [
        ("demand_potential__balanced_equal_dimensions__demand_sat", "Demand / Activity Potential (balanced scenario, saturating)", "viridis", "demand_potential.png"),
        ("readiness__balanced_equal_dimensions__T1__uf_sat", "Deployment Readiness (balanced, T1 integration)", "YlGnBu", "readiness_balanced_T1.png"),
        ("readiness__infrastructure_readiness_oriented__T1__uf_sat", "Deployment Readiness (infra-oriented, T1)", "YlGnBu", "readiness_infra_oriented_T1.png"),
        ("infrastructure_gap__balanced_equal_dimensions", "Cycling Infrastructure Gap (balanced)", "OrRd", "infrastructure_gap.png"),
        ("opportunity__balanced_equal_dimensions__demand_sat", "Latent Opportunity (balanced, saturating demand)", "PuRd", "opportunity_balanced.png"),
        ("opportunity__demand_oriented__demand_sat", "Latent Opportunity (demand-oriented)", "PuRd", "opportunity_demand_oriented.png"),
    ]
    for col, title, cmap, fname in specs:
        fig, ax = plt.subplots(figsize=(9, 9))
        plot_df.plot(column=col, cmap=cmap, ax=ax, legend=True, edgecolor="none", vmin=0, vmax=1)
        _base(ax, title)
        fig.savefig(MAPS_DIR / fname, dpi=170, bbox_inches="tight")
        plt.close(fig)
        print(f"  [map] {MAPS_DIR / fname}")

    # Scenario disagreement map (std dev of readiness across all 4 scenarios, T1, uf_sat)
    readiness_cols_t1 = [f"readiness__{s}__T1__uf_sat" for s in WEIGHTING_SCENARIOS]
    plot_df["_readiness_disagreement"] = plot_df[readiness_cols_t1].std(axis=1)
    fig, ax = plt.subplots(figsize=(9, 9))
    plot_df.plot(column="_readiness_disagreement", cmap="magma", ax=ax, legend=True, edgecolor="none")
    _base(ax, "Readiness scenario disagreement (std dev across 4 weighting scenarios, T1)")
    fig.savefig(MAPS_DIR / "readiness_scenario_disagreement.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  [map] {MAPS_DIR / 'readiness_scenario_disagreement.png'}")

    t1_vs_t2 = (plot_df["readiness__balanced_equal_dimensions__T1__uf_sat"] - plot_df["readiness__balanced_equal_dimensions__T2__uf_sat"])
    plot_df["_t1_vs_t2"] = t1_vs_t2
    fig, ax = plt.subplots(figsize=(9, 9))
    vmax = float(t1_vs_t2.abs().max())
    plot_df.plot(column="_t1_vs_t2", cmap="RdBu_r", vmin=-vmax, vmax=vmax, ax=ax, legend=True, edgecolor="none")
    _base(ax, "T1 (integration) minus T2 (substitution) readiness difference")
    fig.savefig(MAPS_DIR / "t1_vs_t2_sensitivity.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  [map] {MAPS_DIR / 't1_vs_t2_sensitivity.png'}")


if __name__ == "__main__":
    main()
