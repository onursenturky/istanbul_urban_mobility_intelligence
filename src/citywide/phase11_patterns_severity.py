"""Phase 11, Sections 7-10: multi-domain accessibility patterns, the
active-mobility intervention descriptive classes, the high-population gap
table, and physical (non-weighted) severity metrics. All derived from the
Section 1-6 synthesis columns already on disk -- no new routing.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "accessibility_gap_intelligence"
REQUIRED = ["food", "healthcare", "education"]
TRANSIT_GAP_CLASSES = {"GENERAL_ACCESS_GAP", "FIXED_GUIDEWAY_ACCESS_GAP", "BOTH_TRANSIT_ACCESS_GAPS"}


def multi_domain_class(row) -> str:
    if not row["strict_synthesis_reliable"]:
        return "E_DATA_OR_NETWORK_UNCERTAIN"
    everyday_gap = row["everyday_gap_class"] != "NO_REQUIRED_GAP"
    transit_gap = row["transit_access_gap_class"] in TRANSIT_GAP_CLASSES
    if not everyday_gap and not transit_gap:
        return "A_BROAD_ACCESS"
    if everyday_gap and not transit_gap:
        return "B_EVERYDAY_NEEDS_GAP_ONLY"
    if not everyday_gap and transit_gap:
        return "C_TRANSIT_ACCESS_GAP_ONLY"
    return "D_BOTH_ACCESS_GAPS"


def intervention_class(row) -> str:
    if not row["strict_synthesis_reliable"]:
        return "QUALITY_UNCERTAIN"
    everyday_gap = row["everyday_gap_class"] != "NO_REQUIRED_GAP"
    transit_gap = row["transit_access_gap_class"] in TRANSIT_GAP_CLASSES
    if not everyday_gap and not transit_gap:
        return "WALKING_SUFFICIENT"
    closes_everyday = row["cycling_closure_status"] == "FULLY_CLOSED_BY_CYCLING"
    closes_transit = transit_gap and bool(row["CYCLE_ONLY_TRANSIT_GAIN"])
    partial_everyday = row["cycling_closure_status"] == "PARTIALLY_CLOSED_BY_CYCLING"
    if closes_everyday and closes_transit:
        return "CYCLING_CLOSES_BOTH"
    if closes_everyday:
        return "CYCLING_CLOSES_EVERYDAY_GAP"
    if closes_transit:
        return "CYCLING_CLOSES_TRANSIT_GAP"
    if partial_everyday:
        return "CYCLING_PARTIAL_GAIN"
    return "CYCLING_DOES_NOT_CLOSE_GAP"


def main() -> None:
    print("=" * 72)
    print("Phase 11 Sections 7-10: multi-domain patterns, intervention logic, high-pop gaps, severity")
    print("=" * 72)

    df = pd.read_parquet(OUT_DIR / "accessibility_gap_grid_synthesis.parquet")
    total_pop = float(df["population_calibrated"].sum())

    print("\n[Section 7] Multi-domain accessibility patterns...")
    df["multi_domain_class"] = df.apply(multi_domain_class, axis=1)
    md_summary = []
    for cls, g in df.groupby("multi_domain_class"):
        md_summary.append({"class": cls, "n_cells": len(g), "pct_cells": round(len(g) / len(df) * 100, 2),
                             "population": round(float(g["population_calibrated"].sum()), 1),
                             "pct_population": round(float(g["population_calibrated"].sum()) / total_pop * 100, 2)})
    md_summary_df = pd.DataFrame(md_summary).sort_values("n_cells", ascending=False)
    print(md_summary_df.to_string(index=False))

    md_typology_cross = pd.crosstab(df["cluster"], df["multi_domain_class"], normalize="index").round(4) * 100
    print("\n  typology composition (row %):")
    print(md_typology_cross.to_string())

    md_cols = ["grid_id", "district", "cluster", "population_calibrated", "everyday_gap_class",
               "transit_access_gap_class", "multi_domain_class"]
    df[md_cols].to_parquet(OUT_DIR / "multi_domain_accessibility_patterns.parquet")
    md_summary_df.to_csv(OUT_DIR / "multi_domain_accessibility_summary.csv", index=False)
    print(f"[save] multi_domain_accessibility_patterns.parquet, multi_domain_accessibility_summary.csv")

    print("\n[Section 8] Active-mobility intervention classes (descriptive only, NOT a recommendation model)...")
    df["intervention_class"] = df.apply(intervention_class, axis=1)
    iv_summary = []
    for cls, g in df.groupby("intervention_class"):
        iv_summary.append({"intervention_class": cls, "n_cells": len(g), "pct_cells": round(len(g) / len(df) * 100, 2),
                             "population": round(float(g["population_calibrated"].sum()), 1),
                             "pct_population": round(float(g["population_calibrated"].sum()) / total_pop * 100, 2)})
    iv_summary_df = pd.DataFrame(iv_summary).sort_values("n_cells", ascending=False)
    print(iv_summary_df.to_string(index=False))

    iv_cols = ["grid_id", "district", "cluster", "population_calibrated", "everyday_gap_class", "cycling_closure_status",
               "transit_access_gap_class", "CYCLE_ONLY_TRANSIT_GAIN", "intervention_class"]
    df[iv_cols].to_parquet(OUT_DIR / "active_mobility_intervention_classes.parquet")
    iv_summary_df.to_csv(OUT_DIR / "active_mobility_intervention_summary.csv", index=False)
    print(f"[save] active_mobility_intervention_classes.parquet, active_mobility_intervention_summary.csv")

    print("\n[Section 9] High-population accessibility gaps (transparent dimensions, NO priority score)...")
    has_gap = (df["everyday_gap_class"] != "NO_REQUIRED_GAP") | (df["transit_access_gap_class"].isin(TRANSIT_GAP_CLASSES))
    gap_cells = df[has_gap & (df["population_calibrated"] > 0)].copy()
    # descriptive population bands (quartiles among gap cells with population>0) -- explicitly NOT a priority ranking
    gap_cells["population_band"] = pd.qcut(gap_cells["population_calibrated"], 4,
                                            labels=["Q1_LOWEST_POPULATION", "Q2", "Q3", "Q4_HIGHEST_POPULATION"], duplicates="drop")
    hp_cols = ["grid_id", "district", "cluster", "population_calibrated", "population_band",
               "everyday_gap_class", "food_missing", "healthcare_missing", "education_missing",
               "walk_food_nearest_min", "walk_healthcare_nearest_min", "walk_education_nearest_min",
               "cycling_closure_status", "cycling_closed_categories",
               "transit_access_gap_class", "CYCLE_ONLY_TRANSIT_GAIN",
               "walking_quality_flag", "cycling_quality_flag", "transit_data_quality_class", "strict_synthesis_reliable"]
    gap_cells[hp_cols].to_parquet(OUT_DIR / "high_population_accessibility_gaps.parquet")
    print(f"  {len(gap_cells)} populated gap cells identified (population>0, everyday OR transit gap)")
    print(f"  population bands: {gap_cells['population_band'].value_counts().to_dict()}")
    print(f"[save] high_population_accessibility_gaps.parquet")

    print("\n[Section 10] Physical accessibility severity metrics (measurement only, NOT a weighted score)...")
    print("  NOTE: Phase 8's walking search used a single 15-minute cutoff-Dijkstra per origin, so any recorded "
          "nearest_time_min is BY CONSTRUCTION <=15 or NaN (unreachable within that horizon) -- 'excess over "
          "15min' is therefore always 0 for reachable cells and UNDEFINED (not zero, not a large number) for "
          "unreachable ones. This is reported transparently rather than papered over with a fabricated value.")

    sev = df[["grid_id", "district", "population_calibrated", "walking_quality_flag", "everyday_access_reliable"]].copy()
    n_unreachable_total = 0
    for cat, col in zip(["food", "healthcare", "education"], ["walk_food_nearest_min", "walk_healthcare_nearest_min", "walk_education_nearest_min"]):
        t = df[col]
        sev[f"{cat}_unreachable_within_15min"] = t.isna()
        sev[f"{cat}_excess_min_over_15"] = (t - 15).clip(lower=0)  # always 0 when not NaN, per the note above
        sev[f"{cat}_headroom_min_under_15"] = (15 - t).clip(lower=0)  # genuinely informative: how close to the 15min edge
        n_unreachable_total += int(t.isna().sum())

    unreachable_cols = [f"{c}_unreachable_within_15min" for c in REQUIRED]
    sev["number_required_categories_unreachable_within_15min"] = sev[unreachable_cols].sum(axis=1)
    headroom_cols = [f"{c}_headroom_min_under_15" for c in REQUIRED]
    # aggregate headroom only across categories that ARE reachable (mean/min ignoring NaN, standard pandas skipna)
    sev["mean_required_service_headroom_min"] = sev[headroom_cols].mean(axis=1, skipna=True)
    sev["min_required_service_headroom_min"] = sev[headroom_cols].min(axis=1, skipna=True)

    print(f"  cells with >=1 required category unreachable within 15min: "
          f"{int((sev['number_required_categories_unreachable_within_15min']>0).sum())}")
    print(f"  distribution of number_required_categories_unreachable_within_15min:")
    print(sev["number_required_categories_unreachable_within_15min"].value_counts().sort_index().to_string())
    print(f"  mean_required_service_headroom_min (reachable categories only) distribution:")
    print(sev["mean_required_service_headroom_min"].describe().to_string())

    sev.to_parquet(OUT_DIR / "physical_accessibility_deficit_metrics.parquet")
    print(f"[save] physical_accessibility_deficit_metrics.parquet")

    summary_out = {
        "methodological_note": "excess_min_over_15 is structurally ~0 for all reachable cells because Phase 8's "
            "search horizon itself was capped at 15 minutes -- it is retained in the output for schema "
            "completeness but is NOT an informative severity signal on its own. The genuinely informative fields "
            "here are (a) number_required_categories_unreachable_within_15min (0-3) and (b) "
            "mean/min_required_service_headroom_min (how close a reachable category is to the 15-minute edge).",
        "n_cells_any_required_category_unreachable": int((sev["number_required_categories_unreachable_within_15min"] > 0).sum()),
        "distribution_n_categories_unreachable": sev["number_required_categories_unreachable_within_15min"].value_counts().sort_index().to_dict(),
        "mean_headroom_min_summary_stats": json.loads(sev["mean_required_service_headroom_min"].describe().to_json()),
    }
    (OUT_DIR / "_phase11_severity_summary.json").write_text(json.dumps(summary_out, indent=2, default=str), encoding="utf-8")

    df.to_parquet(OUT_DIR / "accessibility_gap_grid_synthesis.parquet")
    print(f"\n[save] accessibility_gap_grid_synthesis.parquet (updated with multi-domain + intervention columns)")


if __name__ == "__main__":
    main()
