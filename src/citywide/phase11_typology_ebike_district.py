"""Phase 11, Sections 11-13: V2 typology post-hoc gap composition, e-bike
Readiness/Opportunity cross-application convergence (descriptive only,
NOT validation), and descriptive (non-ranked) district summaries.
"""

from __future__ import annotations

import json

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "accessibility_gap_intelligence"


def main() -> None:
    print("=" * 72)
    print("Phase 11 Sections 11-13: typology, e-bike convergence, district summaries")
    print("=" * 72)

    df = pd.read_parquet(OUT_DIR / "accessibility_gap_grid_synthesis.parquet")
    total_pop = float(df["population_calibrated"].sum())

    print("\n[Section 11] Typology post-hoc gap composition (V2 eight-family, descriptive only)...")
    rows = []
    for cl, g in df.groupby("cluster"):
        pop = float(g["population_calibrated"].sum())
        row = {"cluster": int(cl), "n_cells": len(g), "population": round(pop, 1)}
        for cls, gg in g["everyday_gap_class"].value_counts(normalize=True).items():
            row[f"pct_everyday_{cls}"] = round(gg * 100, 2)
        for cls, gg in g["transit_access_gap_class"].value_counts(normalize=True).items():
            row[f"pct_transit_{cls}"] = round(gg * 100, 2)
        for cls, gg in g["intervention_class"].value_counts(normalize=True).items():
            row[f"pct_intervention_{cls}"] = round(gg * 100, 2)
        rows.append(row)
    typ_df = pd.DataFrame(rows).fillna(0.0)
    print(typ_df.to_string(index=False))
    typ_df.to_csv(OUT_DIR / "typology_accessibility_gap_summary.csv", index=False)
    print(f"[save] {OUT_DIR / 'typology_accessibility_gap_summary.csv'}")

    print("\n[Section 12] E-bike cross-application convergence (post-hoc, descriptive, NOT validation)...")
    opp_q75 = float(df["ebike_opportunity"].quantile(0.75))
    read_q75 = float(df["ebike_readiness"].quantile(0.75))

    groups = {
        "CYCLING_CLOSES_EVERYDAY_GAP": df["intervention_class"] == "CYCLING_CLOSES_EVERYDAY_GAP",
        "CYCLING_CLOSES_TRANSIT_GAP": df["intervention_class"] == "CYCLING_CLOSES_TRANSIT_GAP",
        "CYCLING_CLOSES_BOTH": df["intervention_class"] == "CYCLING_CLOSES_BOTH",
    }
    convergence = {"baseline_citywide": {"top_quartile_share_pct": 25.0,
                                           "robust_high_readiness_share_pct": round(float((df["readiness_consensus_class"] == "ROBUST_HIGH").mean() * 100), 2),
                                           "robust_high_opportunity_share_pct": round(float((df["opportunity_consensus_class"] == "ROBUST_HIGH").mean() * 100), 2)}}
    for label, mask in groups.items():
        g = df[mask]
        n = len(g)
        entry = {
            "n_cells": n,
            "pct_top_quartile_ebike_opportunity": round(float((g["ebike_opportunity"] >= opp_q75).mean() * 100), 2) if n else None,
            "pct_top_quartile_ebike_readiness": round(float((g["ebike_readiness"] >= read_q75).mean() * 100), 2) if n else None,
            "pct_robust_high_readiness": round(float((g["readiness_consensus_class"] == "ROBUST_HIGH").mean() * 100), 2) if n else None,
            "pct_robust_high_opportunity": round(float((g["opportunity_consensus_class"] == "ROBUST_HIGH").mean() * 100), 2) if n else None,
        }
        convergence[label] = entry
        print(f"  {label} (n={n}): top-quartile Opportunity={entry['pct_top_quartile_ebike_opportunity']}%, "
              f"Readiness={entry['pct_top_quartile_ebike_readiness']}%, "
              f"ROBUST_HIGH Readiness={entry['pct_robust_high_readiness']}%, Opportunity={entry['pct_robust_high_opportunity']}%")

    convergence["interpretation"] = ("Descriptive cross-application convergence check only -- NOT validation of "
        "either application, and e-bike scores were not modified or used to compute any Phase 11 gap/closure "
        "class. Elevated shares above the citywide baseline suggest the independently-derived MCDA-based e-bike "
        "application and this network-based accessibility-gap synthesis are pointing at overlapping areas.")
    (OUT_DIR / "ebike_gap_convergence.json").write_text(json.dumps(convergence, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {OUT_DIR / 'ebike_gap_convergence.json'}")

    print("\n[Section 13] District descriptive summaries (NOT a ranking)...")
    district_rows = []
    for dist, g in df.groupby("district"):
        pop = float(g["population_calibrated"].sum())
        everyday_gap_mask = g["everyday_gap_class"].isin(
            ["FOOD_GAP", "HEALTHCARE_GAP", "EDUCATION_GAP", "FOOD_HEALTHCARE_GAP", "FOOD_EDUCATION_GAP",
             "HEALTHCARE_EDUCATION_GAP", "ALL_REQUIRED_GAP"])
        pop_everyday_gap = float(g.loc[everyday_gap_mask, "population_calibrated"].sum())
        dominant_gap = g.loc[everyday_gap_mask, "everyday_gap_class"].mode()
        dominant_gap_type = dominant_gap.iloc[0] if len(dominant_gap) else "NONE"
        pop_everyday_closed = float(g.loc[g["cycling_closure_status"] == "FULLY_CLOSED_BY_CYCLING", "population_calibrated"].sum())

        transit_quality = g["transit_data_quality_class"].mode()
        transit_quality_val = transit_quality.iloc[0] if len(transit_quality) else None
        if transit_quality_val in ("SUSPECT_FEED_COVERAGE", "NO_FEED_COVERAGE"):
            transit_gap_pop_display = "INSUFFICIENT_TRANSIT_DATA_FOR_INTERPRETATION"
            transit_gap_closed_display = "INSUFFICIENT_TRANSIT_DATA_FOR_INTERPRETATION"
        else:
            transit_gap_mask = g["transit_access_gap_class"].isin(["GENERAL_ACCESS_GAP", "FIXED_GUIDEWAY_ACCESS_GAP", "BOTH_TRANSIT_ACCESS_GAPS"])
            transit_gap_pop_display = round(float(g.loc[transit_gap_mask, "population_calibrated"].sum()), 1)
            transit_closed_mask = transit_gap_mask & g["CYCLE_ONLY_TRANSIT_GAIN"].fillna(False)
            transit_gap_closed_display = round(float(g.loc[transit_closed_mask, "population_calibrated"].sum()), 1)

        district_rows.append({
            "district": dist, "n_cells": len(g), "population_total": round(pop, 1),
            "population_with_everyday_needs_gap": round(pop_everyday_gap, 1),
            "dominant_everyday_gap_type": dominant_gap_type,
            "population_everyday_gap_closed_by_cycling": round(pop_everyday_closed, 1),
            "population_transit_access_gap": transit_gap_pop_display,
            "population_transit_gap_closed_by_cycling": transit_gap_closed_display,
            "transit_data_quality_class": transit_quality_val,
        })
    district_df = pd.DataFrame(district_rows).sort_values("district")
    print(district_df.to_string(index=False))
    district_df.to_csv(OUT_DIR / "district_accessibility_gap_summary.csv", index=False)
    print(f"\n[save] {OUT_DIR / 'district_accessibility_gap_summary.csv'}")


if __name__ == "__main__":
    main()
