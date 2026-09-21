"""Phase 9, Sections 12-14: quality-aware comparison, typology post-hoc,
and post-hoc e-bike Opportunity/Readiness overlap.

Section 12 keeps RAW (all cells) and QUALITY-AWARE (RELIABLE-only) gain
interpretation explicitly separate -- a gain in a QUESTIONABLE_ANCHOR,
SMALL_COMPONENT_CAUTION, or KNOWN_NETWORK_LIMITATION_ADALAR cell is not
labeled a genuine finding.

Section 13: typology (analysis/clustering_v2_eight_family/cluster_
assignments_v2ef.parquet, FROZEN) is used ONLY for a post-hoc cross-tab --
it never entered any routing/accessibility computation above.

Section 14: post-hoc, descriptive-only overlap between CYCLE_ONLY_GAIN
cells and the FROZEN e-bike Opportunity/Readiness baselines
(analysis/mcda_v2/phase6b/*). Does NOT change the e-bike model or use
e-bike scores in any accessibility calculation.
"""

from __future__ import annotations

import json

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "cycling_accessibility"
MCDA_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda_v2" / "phase6b"
TYPOLOGY_PATH = cfg.PROJECT_ROOT / "analysis" / "clustering_v2_eight_family" / "cluster_assignments_v2ef.parquet"


def main() -> None:
    print("=" * 72)
    print("Phase 9 Sections 12-14: quality-aware comparison, typology, e-bike overlap")
    print("=" * 72)

    comp = pd.read_parquet(OUT_DIR / "walking_cycling_complete_access_comparison.parquet")
    quality = pd.read_parquet(OUT_DIR / "cycling_accessibility_quality_flags.parquet",
                               columns=["grid_id", "corrected_quality_flag"])
    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet",
                          columns=["grid_id", "population_calibrated"])
    merged = comp.merge(quality, on="grid_id").merge(v2, on="grid_id")
    total_pop = float(v2["population_calibrated"].sum())

    print("\n[Section 12] RAW vs QUALITY-AWARE access-class distribution...")
    raw_dist = merged["access_class"].value_counts(normalize=True).round(4) * 100
    reliable_mask = merged["corrected_quality_flag"].isin(["RELIABLE", "RELIABLE_SEPARATE_COMPONENT"])
    quality_aware = merged[reliable_mask]
    qa_dist = quality_aware["access_class"].value_counts(normalize=True).round(4) * 100
    print("  RAW (%):"); print(raw_dist.to_string())
    print("  QUALITY-AWARE, RELIABLE cells only (%):"); print(qa_dist.to_string())

    cycle_only_gain = merged[merged["access_class"] == "CYCLE_ONLY_GAIN"]
    n_raw = len(cycle_only_gain)
    n_reliable = int(cycle_only_gain["corrected_quality_flag"].isin(["RELIABLE", "RELIABLE_SEPARATE_COMPONENT"]).sum())
    flag_breakdown = cycle_only_gain["corrected_quality_flag"].value_counts().to_dict()
    print(f"\n  CYCLE_ONLY_GAIN cells: {n_raw} RAW -> {n_reliable} after excluding non-RELIABLE quality flags "
          f"({n_raw - n_reliable} removed: {flag_breakdown})")
    pop_raw = float(cycle_only_gain["population_calibrated"].sum())
    pop_reliable = float(cycle_only_gain.loc[cycle_only_gain["corrected_quality_flag"].isin(["RELIABLE", "RELIABLE_SEPARATE_COMPONENT"]), "population_calibrated"].sum())
    print(f"  CYCLE_ONLY_GAIN population: {pop_raw:,.0f} RAW -> {pop_reliable:,.0f} QUALITY-AWARE "
          f"({(pop_raw-pop_reliable)/pop_raw*100 if pop_raw else 0:.1f}% of raw population removed)")

    quality_aware_summary = {
        "raw_access_class_pct": raw_dist.to_dict(),
        "quality_aware_reliable_only_access_class_pct": qa_dist.to_dict(),
        "cycle_only_gain_raw_n_cells": n_raw, "cycle_only_gain_reliable_n_cells": n_reliable,
        "cycle_only_gain_raw_population": round(pop_raw, 1), "cycle_only_gain_reliable_population": round(pop_reliable, 1),
        "cycle_only_gain_flag_breakdown": flag_breakdown,
        "interpretation": "CYCLE_ONLY_GAIN cells flagged QUESTIONABLE_ANCHOR, SMALL_COMPONENT_CAUTION, or "
                          "KNOWN_NETWORK_LIMITATION_ADALAR should NOT be read as genuine active-mobility gains -- "
                          "they may reflect anchor/snap artifacts rather than a real routable improvement. Use the "
                          "RELIABLE-only figures for any downstream claim about genuine cycling accessibility gain.",
    }

    print("\n[Section 13] Typology post-hoc cross-tab (V2 eight-family typology, FROZEN, never used in routing)...")
    typ = pd.read_parquet(TYPOLOGY_PATH)[["grid_id", "cluster"]]
    typ_merged = merged.merge(typ, on="grid_id", how="left")
    typ_cross = pd.crosstab(typ_merged["cluster"], typ_merged["access_class"], normalize="index").round(4) * 100
    typ_counts = pd.crosstab(typ_merged["cluster"], typ_merged["access_class"])
    print("  cluster x access_class (row %):")
    print(typ_cross.to_string())

    typ_pop = typ_merged.groupby(["cluster", "access_class"])["population_calibrated"].sum().round(1).unstack(fill_value=0)
    cycle_gain_share_by_cluster = typ_cross["CYCLE_ONLY_GAIN"] if "CYCLE_ONLY_GAIN" in typ_cross.columns else None
    strongest_gain_cluster = cycle_gain_share_by_cluster.idxmax() if cycle_gain_share_by_cluster is not None else None
    print(f"\n  cluster with highest CYCLE_ONLY_GAIN share: cluster {strongest_gain_cluster} "
          f"({cycle_gain_share_by_cluster.max():.2f}%)" if strongest_gain_cluster is not None else "  n/a")

    already_high_walk = typ_cross["WALK_AND_CYCLE_ACCESS"] if "WALK_AND_CYCLE_ACCESS" in typ_cross.columns else None
    cycling_fails_cluster = typ_cross["NEITHER_ACCESS"].idxmax() if "NEITHER_ACCESS" in typ_cross.columns else None

    typ_summary_rows = []
    for cl in sorted(typ_merged["cluster"].dropna().unique()):
        row = {"cluster": int(cl), "n_cells": int((typ_merged["cluster"] == cl).sum())}
        for cls in ["WALK_AND_CYCLE_ACCESS", "WALK_ONLY_ACCESS", "CYCLE_ONLY_GAIN", "NEITHER_ACCESS"]:
            row[f"pct_{cls}"] = round(float(typ_cross.loc[cl, cls]), 2) if cls in typ_cross.columns else 0.0
        typ_summary_rows.append(row)
    typ_summary_df = pd.DataFrame(typ_summary_rows)
    typ_summary_df.to_csv(OUT_DIR / "typology_cycling_gain_summary.csv", index=False)
    print(f"\n[save] {OUT_DIR / 'typology_cycling_gain_summary.csv'}")

    print("\n[Section 14] Post-hoc e-bike Opportunity/Readiness overlap (DESCRIPTIVE ONLY)...")
    ebike_opp = pd.read_parquet(MCDA_DIR / "ebike_opportunity_baseline.parquet", columns=["grid_id", "ebike_opportunity"])
    ebike_read = pd.read_parquet(MCDA_DIR / "ebike_readiness_baseline.parquet", columns=["grid_id", "ebike_readiness"])
    ebike = ebike_opp.merge(ebike_read, on="grid_id")
    ebike_merged = merged.merge(ebike, on="grid_id", how="inner")
    print(f"  matched {len(ebike_merged)}/{len(merged)} grid cells to frozen e-bike baseline")

    # High e-bike opportunity/readiness defined by the SAME top-quartile convention the
    # e-bike application already uses for its own descriptive breakdowns (not a new threshold).
    opp_q75 = float(ebike_merged["ebike_opportunity"].quantile(0.75))
    read_q75 = float(ebike_merged["ebike_readiness"].quantile(0.75))
    high_opp = ebike_merged["ebike_opportunity"] >= opp_q75
    high_read = ebike_merged["ebike_readiness"] >= read_q75

    cyc_gain_mask = ebike_merged["access_class"] == "CYCLE_ONLY_GAIN"
    overlap_high_opp = int((cyc_gain_mask & high_opp).sum())
    overlap_high_read = int((cyc_gain_mask & high_read).sum())
    n_cyc_gain = int(cyc_gain_mask.sum())
    n_high_opp = int(high_opp.sum())

    print(f"  CYCLE_ONLY_GAIN cells: {n_cyc_gain}")
    print(f"  of these, top-quartile e-bike Opportunity: {overlap_high_opp} ({overlap_high_opp/n_cyc_gain*100 if n_cyc_gain else 0:.1f}%)")
    print(f"  of these, top-quartile e-bike Readiness: {overlap_high_read} ({overlap_high_read/n_cyc_gain*100 if n_cyc_gain else 0:.1f}%)")
    print(f"  (for reference, top-quartile Opportunity is {n_high_opp}/{len(ebike_merged)} cells citywide = 25% by construction)")

    # Correlation as an additional descriptive signal (not a model).
    corr_opp = float(ebike_merged["ebike_opportunity"].corr(
        (ebike_merged["cycling_required_categories_accessible_15min"] - ebike_merged["walking_required_categories_accessible_15min"]).clip(lower=0)
    ))

    ebike_overlap = {
        "question": "Do areas identified as e-bike opportunities also correspond to places where cycling can "
                     "materially improve access to everyday needs?",
        "method": "Descriptive overlap only -- e-bike Opportunity/Readiness (frozen Phase 6B-V2 MCDA baseline) "
                   "was NOT used to compute cycling accessibility, and cycling accessibility results were NOT "
                   "fed back into the e-bike model.",
        "n_grid_cells_matched": len(ebike_merged),
        "n_cycle_only_gain_cells": n_cyc_gain,
        "n_cycle_only_gain_cells_top_quartile_ebike_opportunity": overlap_high_opp,
        "pct_cycle_only_gain_cells_top_quartile_ebike_opportunity": round(overlap_high_opp / n_cyc_gain * 100, 2) if n_cyc_gain else None,
        "n_cycle_only_gain_cells_top_quartile_ebike_readiness": overlap_high_read,
        "pct_cycle_only_gain_cells_top_quartile_ebike_readiness": round(overlap_high_read / n_cyc_gain * 100, 2) if n_cyc_gain else None,
        "baseline_top_quartile_share_citywide_pct": 25.0,
        "correlation_ebike_opportunity_vs_required_categories_gained": round(corr_opp, 4) if corr_opp == corr_opp else None,
        "ebike_opportunity_q75_threshold": round(opp_q75, 4),
        "ebike_readiness_q75_threshold": round(read_q75, 4),
        "interpretation_note": "A positive overlap above the 25% citywide baseline would suggest the two frozen, "
                                "independently-derived analyses (MCDA-based e-bike suitability and network-based "
                                "cycling accessibility gain) are pointing at overlapping areas -- a potentially "
                                "important framework-level cross-validation result. Any such overlap is descriptive "
                                "co-location, not a causal or behavioral claim.",
    }
    (OUT_DIR / "ebike_cycling_gain_overlap.json").write_text(
        json.dumps(ebike_overlap, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"\n[save] {OUT_DIR / 'ebike_cycling_gain_overlap.json'}")

    (OUT_DIR / "_phase9_quality_aware_typology_summary.json").write_text(
        json.dumps({"quality_aware_comparison": quality_aware_summary,
                    "typology_cross_tab_counts": typ_counts.to_dict(),
                    "typology_cross_tab_pop": typ_pop.to_dict(),
                    "strongest_gain_cluster": str(strongest_gain_cluster),
                    "cluster_with_highest_neither_access_share": str(cycling_fails_cluster)},
                   indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"[save] {OUT_DIR / '_phase9_quality_aware_typology_summary.json'} (intermediate)")


if __name__ == "__main__":
    main()
