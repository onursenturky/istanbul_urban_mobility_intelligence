"""Phase 10, Sections 13-16: district descriptive summaries (NOT a
ranking), V2 typology post-hoc, Phase 9-vs-Phase 10 cycling-gain overlap,
and e-bike Opportunity/Readiness cross-application overlap.

All post-hoc: typology and e-bike scores never enter routing/accessibility
computation. This module only joins already-computed Phase 10 results
(and, for Section 15, already-computed Phase 9 results) by grid_id.
"""

from __future__ import annotations

import json

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "first_last_mile_transit"
CYC_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "cycling_accessibility"
MCDA_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda_v2" / "phase6b"
THRESHOLDS = [5, 10, 15]


def main() -> None:
    print("=" * 72)
    print("Phase 10 Sections 13-16: district summary, typology, Phase9 overlap, e-bike overlap")
    print("=" * 72)

    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet",
                          columns=["grid_id", "population_calibrated"])
    origin_quality = pd.read_parquet(OUT_DIR / "_origin_quality.parquet")
    district_quality = pd.read_csv(OUT_DIR / "transit_district_quality.csv")[["district", "transit_data_quality_class"]]

    walk_a = pd.read_parquet(OUT_DIR / "walking_general_transit_accessibility.parquet")
    walk_b = pd.read_parquet(OUT_DIR / "walking_fixed_transit_accessibility.parquet")
    cyc_a = pd.read_parquet(OUT_DIR / "cycling_general_transit_accessibility.parquet")
    cyc_b = pd.read_parquet(OUT_DIR / "cycling_fixed_transit_accessibility.parquet")
    gap_diag = pd.read_parquet(OUT_DIR / "transit_gap_diagnostics.parquet")

    base = walk_a[["grid_id", "district"]].copy()
    base["walk_general_10min"] = walk_a["access_10min"].to_numpy()
    base["cycle_general_10min"] = cyc_a["access_10min"].to_numpy()
    base["walk_fixed_15min"] = walk_b["access_15min"].to_numpy()
    base["cycle_fixed_15min"] = cyc_b["access_15min"].to_numpy()
    base = base.merge(v2, on="grid_id").merge(gap_diag[["grid_id", "gap_class"]], on="grid_id")
    total_pop = float(v2["population_calibrated"].sum())

    print("\n[Section 13] District descriptive summary (NOT a ranking)...")
    by_district = base.groupby("district").agg(
        n_cells=("grid_id", "size"),
        pop_total=("population_calibrated", "sum"),
        pct_walk_general_10min=("walk_general_10min", "mean"),
        pct_cycle_general_10min=("cycle_general_10min", "mean"),
        pct_walk_fixed_15min=("walk_fixed_15min", "mean"),
        pct_cycle_fixed_15min=("cycle_fixed_15min", "mean"),
    ).reset_index()
    for c in ["pct_walk_general_10min", "pct_cycle_general_10min", "pct_walk_fixed_15min", "pct_cycle_fixed_15min"]:
        by_district[c] = (by_district[c] * 100).round(2)

    cycle_gain_by_district = base[base["gap_class"] != "NO_TRANSIT_GAP"].copy()
    # population where cycling closes a gap that walking alone does not (general, primary 10min threshold)
    closure_pop = base[(~base["walk_general_10min"]) & (base["cycle_general_10min"])].groupby("district")["population_calibrated"].sum()
    by_district = by_district.merge(closure_pop.rename("cycling_gap_closure_population_general_10min").reset_index(), on="district", how="left")
    by_district["cycling_gap_closure_population_general_10min"] = by_district["cycling_gap_closure_population_general_10min"].fillna(0).round(1)
    by_district = by_district.merge(district_quality, on="district", how="left")

    print(by_district.sort_values("district").to_string(index=False))
    flagged = by_district[by_district["transit_data_quality_class"] != "GOOD_COVERAGE"]
    print(f"\n  {len(flagged)}/{len(by_district)} districts flagged non-GOOD_COVERAGE -- their accessibility "
          f"values below must be read with that caveat, NOT as genuine transport disadvantage.")
    by_district.to_csv(OUT_DIR / "district_transit_accessibility_summary.csv", index=False)
    print(f"[save] {OUT_DIR / 'district_transit_accessibility_summary.csv'}")

    print("\n[Section 14] Typology post-hoc (V2 eight-family, FROZEN, never used in routing)...")
    typ_base = base.merge(origin_quality[["grid_id", "cluster"]], on="grid_id")
    by_cluster = typ_base.groupby("cluster").agg(
        n_cells=("grid_id", "size"), pop_total=("population_calibrated", "sum"),
        pct_walk_general_10min=("walk_general_10min", "mean"),
        pct_cycle_general_10min=("cycle_general_10min", "mean"),
        pct_walk_fixed_15min=("walk_fixed_15min", "mean"),
        pct_cycle_fixed_15min=("cycle_fixed_15min", "mean"),
    ).reset_index()
    for c in ["pct_walk_general_10min", "pct_cycle_general_10min", "pct_walk_fixed_15min", "pct_cycle_fixed_15min"]:
        by_cluster[c] = (by_cluster[c] * 100).round(2)
    gap_cross = pd.crosstab(typ_base["cluster"], typ_base["gap_class"], normalize="index").round(4) * 100
    for cls in ["NO_TRANSIT_GAP", "FIXED_GUIDEWAY_GAP", "GENERAL_TRANSIT_GAP", "BOTH_TRANSIT_GAPS"]:
        by_cluster[f"pct_{cls}"] = by_cluster["cluster"].map(gap_cross[cls]) if cls in gap_cross.columns else 0.0
    print(by_cluster.to_string(index=False))
    by_cluster.to_csv(OUT_DIR / "typology_transit_accessibility_summary.csv", index=False)
    print(f"[save] {OUT_DIR / 'typology_transit_accessibility_summary.csv'}")

    strong_walk_clusters = by_cluster.loc[by_cluster["pct_walk_general_10min"] >= by_cluster["pct_walk_general_10min"].median(), "cluster"].tolist()
    best_cycle_gain_cluster = int(by_cluster.loc[by_cluster["pct_cycle_general_10min"].sub(by_cluster["pct_walk_general_10min"]).idxmax(), "cluster"])
    worst_both_cluster = int(by_cluster.loc[by_cluster["pct_BOTH_TRANSIT_GAPS"].idxmax(), "cluster"]) if "pct_BOTH_TRANSIT_GAPS" in by_cluster.columns else None
    print(f"\n  cluster where cycling most expands general-transit catchment (10min): {best_cycle_gain_cluster}")
    print(f"  cluster where neither mode overcomes sparse transit (highest BOTH_TRANSIT_GAPS share): {worst_both_cluster}")

    print("\n[Section 15] Phase 9 vs Phase 10 cycling-gain overlap (post-hoc, descriptive only)...")
    phase9_comp = pd.read_parquet(CYC_DIR / "walking_cycling_complete_access_comparison.parquet")[["grid_id", "access_class"]]
    phase9_comp = phase9_comp.rename(columns={"access_class": "phase9_everyday_needs_access_class"})
    p9_p10 = base.merge(phase9_comp, on="grid_id")
    p9_p10["phase9_gain"] = p9_p10["phase9_everyday_needs_access_class"] == "CYCLE_ONLY_GAIN"
    p9_p10["phase10_gain"] = p9_p10["gap_class"].isin(["FIXED_GUIDEWAY_GAP", "GENERAL_TRANSIT_GAP", "BOTH_TRANSIT_GAPS"]) & \
                              (~p9_p10["walk_general_10min"]) & (p9_p10["cycle_general_10min"])

    def overlap_group(row):
        if row["phase9_gain"] and row["phase10_gain"]:
            return "BOTH_GAINS"
        if row["phase9_gain"] and not row["phase10_gain"]:
            return "EVERYDAY_NEEDS_GAIN_ONLY"
        if not row["phase9_gain"] and row["phase10_gain"]:
            return "TRANSIT_GAIN_ONLY"
        return "NO_CYCLING_GAIN"

    p9_p10["overlap_group"] = p9_p10.apply(overlap_group, axis=1)
    overlap_summary = []
    for grp, g in p9_p10.groupby("overlap_group"):
        overlap_summary.append({"overlap_group": grp, "n_cells": len(g), "pct_cells": round(len(g) / len(p9_p10) * 100, 2),
                                  "population": round(float(g["population_calibrated"].sum()), 1),
                                  "pct_population": round(float(g["population_calibrated"].sum()) / total_pop * 100, 2)})
    overlap_summary_df = pd.DataFrame(overlap_summary)
    print(overlap_summary_df.to_string(index=False))

    p9_p10_out = {
        "question": "Does cycling improve everyday-needs accessibility (Phase 9) and transit access (Phase 10) "
                     "in the same places, or do these benefits occur in different urban contexts?",
        "definition_phase10_gain": "cell where general-transit (System A) is NOT reachable by walking within "
                                    "10min but IS reachable by cycling within 10min (CYCLE_ONLY general-transit gain)",
        "overlap_summary": overlap_summary_df.to_dict(orient="records"),
        "no_combined_score_created": True,
    }
    (OUT_DIR / "phase9_phase10_cycling_gain_overlap.json").write_text(
        json.dumps(p9_p10_out, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"[save] {OUT_DIR / 'phase9_phase10_cycling_gain_overlap.json'}")

    print("\n[Section 16] E-bike Readiness/Opportunity cross-application overlap (post-hoc, descriptive)...")
    ebike_opp = pd.read_parquet(MCDA_DIR / "ebike_opportunity_baseline.parquet", columns=["grid_id", "ebike_opportunity"])
    ebike_read = pd.read_parquet(MCDA_DIR / "ebike_readiness_baseline.parquet", columns=["grid_id", "ebike_readiness"])
    ebike = ebike_opp.merge(ebike_read, on="grid_id")
    p10_gain_cells = base.merge(gap_diag[["grid_id"]], on="grid_id")
    transit_gain_mask = (~base["walk_general_10min"]) & (base["cycle_general_10min"])
    transit_gain_cells = base.loc[transit_gain_mask, ["grid_id"]].merge(ebike, on="grid_id", how="inner")

    opp_q75 = float(ebike["ebike_opportunity"].quantile(0.75))
    read_q75 = float(ebike["ebike_readiness"].quantile(0.75))
    n_gain = len(transit_gain_cells)
    n_high_opp = int((transit_gain_cells["ebike_opportunity"] >= opp_q75).sum())
    n_high_read = int((transit_gain_cells["ebike_readiness"] >= read_q75).sum())

    print(f"  CYCLE_ONLY_TRANSIT_GAIN (general, 10min) cells: {n_gain}")
    print(f"  of these, top-quartile e-bike Opportunity: {n_high_opp} ({n_high_opp/n_gain*100 if n_gain else 0:.1f}%, vs 25% baseline)")
    print(f"  of these, top-quartile e-bike Readiness: {n_high_read} ({n_high_read/n_gain*100 if n_gain else 0:.1f}%, vs 25% baseline)")

    ebike_overlap = {
        "note": "Cross-application convergence check -- descriptive co-location only, NOT validation, NOT a "
                "combined score. E-bike model was not modified; e-bike scores did not enter transit routing.",
        "definition_transit_gain_cells": "cells where general transit (System A) is unreachable by walking within "
                                          "10min but reachable by cycling within 10min",
        "n_transit_gain_cells": n_gain,
        "n_transit_gain_cells_top_quartile_ebike_opportunity": n_high_opp,
        "pct_transit_gain_cells_top_quartile_ebike_opportunity": round(n_high_opp / n_gain * 100, 2) if n_gain else None,
        "n_transit_gain_cells_top_quartile_ebike_readiness": n_high_read,
        "pct_transit_gain_cells_top_quartile_ebike_readiness": round(n_high_read / n_gain * 100, 2) if n_gain else None,
        "baseline_top_quartile_share_citywide_pct": 25.0,
        "ebike_opportunity_q75_threshold": round(opp_q75, 4),
        "ebike_readiness_q75_threshold": round(read_q75, 4),
    }
    (OUT_DIR / "ebike_transit_gain_overlap.json").write_text(
        json.dumps(ebike_overlap, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"[save] {OUT_DIR / 'ebike_transit_gain_overlap.json'}")

    (OUT_DIR / "_phase10_district_typology_summary.json").write_text(
        json.dumps({"best_cycle_gain_cluster": best_cycle_gain_cluster, "worst_both_gap_cluster": worst_both_cluster,
                    "n_districts_flagged_non_good_coverage": len(flagged)}, indent=2, default=str), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
