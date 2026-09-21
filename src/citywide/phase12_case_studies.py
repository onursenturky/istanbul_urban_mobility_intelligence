"""Phase 12, Section 13: nine analytical-archetype case studies. Cells are
selected by ANALYTICAL CRITERIA (a representative, moderate-population
member of each archetype), not by picking global min/max extremes --
avoiding cherry-picking per the explicit instruction.
"""

from __future__ import annotations

import json

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

ROOT = cfg.PROJECT_ROOT
OUT_DIR = ROOT / "analysis" / "framework_synthesis"
DASH_DIR = OUT_DIR / "dashboard"
TRANSIT_DIR = ROOT / "analysis" / "applications" / "first_last_mile_transit"


def build_case(row: pd.Series, label: str, why: str) -> dict:
    return {
        "case_label": label, "grid_id": row["grid_id"], "district": row["district"],
        "population": None if pd.isna(row["calibrated_population_2020"]) else round(float(row["calibrated_population_2020"]), 1),
        "typology_cluster": None if pd.isna(row["typology_cluster"]) else int(row["typology_cluster"]),
        "walking_accessibility": {
            "food_min": _n(row["food_walk_min"]), "healthcare_min": _n(row["healthcare_walk_min"]), "education_min": _n(row["education_walk_min"]),
            "required_categories_15min": _n(row["required_categories_walk_15"]), "complete_15min": bool(row["complete_walk_15"]) if pd.notna(row["complete_walk_15"]) else None,
        },
        "cycling_accessibility": {
            "food_min": _n(row["food_cycle_min"]), "healthcare_min": _n(row["healthcare_cycle_min"]), "education_min": _n(row["education_cycle_min"]),
            "required_categories_15min": _n(row["required_categories_cycle_15"]), "complete_15min": bool(row["complete_cycle_15"]) if pd.notna(row["complete_cycle_15"]) else None,
            "cycle_only_everyday_gain": bool(row["cycle_only_everyday_gain"]) if pd.notna(row["cycle_only_everyday_gain"]) else None,
        },
        "transit_accessibility": {
            "general_transit_walk_min": _n(row["general_transit_walk_min"]), "general_transit_cycle_min": _n(row["general_transit_cycle_min"]),
            "fixed_transit_walk_min": _n(row["fixed_transit_walk_min"]), "fixed_transit_cycle_min": _n(row["fixed_transit_cycle_min"]),
            "cycle_only_transit_gain_general_10min": bool(row["cycle_only_transit_gain"]) if pd.notna(row["cycle_only_transit_gain"]) else None,
        },
        "gap_class": {
            "everyday_gap_type": row["everyday_gap_type"], "cycling_gap_closure": row["cycling_gap_closure"],
            "transit_gap_type": row["transit_gap_type"], "multi_domain_pattern": row["multi_domain_pattern"],
            "active_mobility_intervention": row["active_mobility_intervention"],
        },
        "ebike_context": {
            "readiness": _n(row["ebike_readiness"]), "opportunity": _n(row["ebike_opportunity"]),
            "readiness_robustness": row["ebike_readiness_robustness"], "opportunity_robustness": row["ebike_opportunity_robustness"],
        },
        "quality_status": {
            "walking_quality": row["walking_quality"], "cycling_quality": row["cycling_quality"],
            "transit_data_quality": row["transit_data_quality"], "synthesis_reliable": bool(row["synthesis_reliable"]) if pd.notna(row["synthesis_reliable"]) else None,
        },
        "why_this_case_matters": why,
    }


def _n(v):
    return None if pd.isna(v) else round(float(v), 2) if isinstance(v, (int, float)) else v


def median_pick(df: pd.DataFrame, mask: pd.Series) -> pd.Series:
    """Picks the MEDIAN-population row satisfying mask, among populated cells --
    a representative case, not a cherry-picked extreme."""
    sub = df[mask & (df["calibrated_population_2020"] > 0)].sort_values("calibrated_population_2020")
    if len(sub) == 0:
        sub = df[mask]
    return sub.iloc[len(sub) // 2]


def main() -> None:
    print("=" * 72)
    print("Phase 12 Section 13: nine analytical case studies")
    print("=" * 72)

    df = pd.read_parquet(DASH_DIR / "dashboard_grid.parquet")
    fixed_comp = pd.read_parquet(TRANSIT_DIR / "fixed_transit_mode_comparison.parquet", columns=["grid_id", "access_class_15min"])
    df = df.merge(fixed_comp.rename(columns={"access_class_15min": "fixed_transit_access_class_15min"}), on="grid_id", how="left")

    cases = []

    core_districts = ["Fatih", "Beyoğlu", "Kadıköy", "Şişli", "Beşiktaş"]
    row = median_pick(df, df["district"].isin(core_districts) & (df["complete_walk_15"] == True))
    cases.append(build_case(row, "CASE_1_DENSE_CORE_STRONG_WALKING",
        "Illustrates the dense-core baseline: complete walking access is already the norm here, so this is the "
        "reference case against which every 'cycling adds value' claim elsewhere should be compared."))

    row = median_pick(df, df["district"].isin(core_districts) & (df["complete_walk_15"] == True) &
                       (df["active_mobility_intervention"] == "WALKING_SUFFICIENT"))
    cases.append(build_case(row, "CASE_2_DENSE_CYCLING_ADDS_LITTLE",
        "Shows the honest counter-case to the 'cycling helps everywhere' narrative: in an already-complete dense "
        "area, cycling has no everyday-needs gap left to close."))

    row = median_pick(df, df["cycling_gap_closure"] == "FULLY_CLOSED_BY_CYCLING")
    cases.append(build_case(row, "CASE_3_CYCLING_FULLY_CLOSES_GAP",
        "A populated, mid-range (not extreme) example of the single most important active-mobility finding: a "
        "cell with an everyday-needs gap under walking where cycling's modeled network fully closes it."))

    row = median_pick(df, df["cycling_gap_closure"] == "PARTIALLY_CLOSED_BY_CYCLING")
    cases.append(build_case(row, "CASE_4_CYCLING_PARTIALLY_CLOSES_GAP",
        "Illustrates the nuance lost in a binary framing: cycling helps but does not fully solve the gap here -- "
        "one or two required categories remain out of reach even by bike."))

    row = median_pick(df, df["cycling_gap_closure"] == "UNCHANGED_BY_CYCLING")
    cases.append(build_case(row, "CASE_5_CYCLING_CANNOT_OVERCOME_SPARSITY",
        "Demonstrates the limit of active-mobility interventions: when destinations themselves are sparse, no "
        "network-based mode improvement (walking or cycling) can create accessibility that does not exist."))

    row = median_pick(df, df["fixed_transit_access_class_15min"] == "CYCLE_ONLY_TRANSIT_GAIN")
    cases.append(build_case(row, "CASE_6_CYCLING_EXPANDS_FIXED_GUIDEWAY_ACCESS",
        "Shows cycling's single largest quantified transit contribution (Phase 10): reaching a metro/tram/rail/"
        "metrobus station within 15 minutes by bike where walking cannot, at all, within the same window."))

    row = median_pick(df, (df["active_mobility_intervention"] == "CYCLING_CLOSES_EVERYDAY_GAP") &
                       (df["ebike_readiness_robustness"] == "ROBUST_HIGH"))
    cases.append(build_case(row, "CASE_7_EBIKE_ACCESSIBILITY_CONVERGENCE",
        "A concrete instance of Phase 11/12's cross-application convergence finding: this cell's network-measured "
        "everyday-needs cycling closure co-occurs with an independently-derived, ROBUST_HIGH e-bike Readiness score."))

    row = median_pick(df, df["transit_data_quality"].isin(["SUSPECT_FEED_COVERAGE", "NO_FEED_COVERAGE"]))
    cases.append(build_case(row, "CASE_8_INSUFFICIENT_TRANSIT_DATA",
        "A mandatory transparency case: this cell's transit-access figures must be read as DATA INSUFFICIENT, not "
        "as evidence of an actual transit desert -- the underlying GTFS feed simply does not map stops reliably here."))

    row = median_pick(df, df["district"] == "Adalar")
    cases.append(build_case(row, "CASE_9_ADALAR_KNOWN_NETWORK_LIMITATION",
        "The framework's standing known-limitation case: Adalar's walking network is a genuine small local "
        "component and its cycling network has ZERO real on-island nodes (cycling figures reflect cross-water "
        "snapping to the mainland, not real routes) -- flagged at every phase since Phase 7."))

    print(f"  {len(cases)} case studies selected")
    for c in cases:
        print(f"  [{c['case_label']}] {c['grid_id']} ({c['district']}, pop={c['population']})")

    (OUT_DIR / "case_studies" / "case_studies.json").write_text(
        json.dumps({"cases": cases, "selection_method": "Median-population member of each analytically-defined "
                    "archetype group (not global min/max) -- avoids cherry-picking per instruction."},
                   indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"\n[save] {OUT_DIR / 'case_studies' / 'case_studies.json'}")


if __name__ == "__main__":
    main()
