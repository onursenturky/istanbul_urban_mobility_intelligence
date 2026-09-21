"""Phase 10, Sections 9-12: walking-vs-cycling gap closure per system,
first/last-mile time savings, transit-gap diagnostics (data quality kept
separate from accessibility deficit), and population-weighted results
(RAW vs QUALITY-AWARE).

Primary threshold convention reused from Section 8: General transit uses
the 10-minute threshold, Fixed-guideway uses the 15-minute threshold --
this is why GENERAL_TRANSIT_GAP and FIXED_GUIDEWAY_GAP are logically
independent (System B access points are a SUBSET of System A's, so at the
SAME threshold fixed-access would always imply general-access; the
different thresholds make a "reachable only within 11-15min, and that
access point happens to be fixed-guideway" cell possible).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "first_last_mile_transit"
THRESHOLDS = [5, 10, 15]
GENERAL_PRIMARY_MIN = 10
FIXED_PRIMARY_MIN = 15
RELIABLE_FLAGS = {"RELIABLE", "RELIABLE_SEPARATE_COMPONENT"}


def build_mode_comparison(walk_df: pd.DataFrame, cyc_df: pd.DataFrame, v2: pd.DataFrame, system_label: str) -> pd.DataFrame:
    base = walk_df[["grid_id", "district"]].copy()
    for t in THRESHOLDS:
        w, c = walk_df[f"access_{t}min"], cyc_df[f"access_{t}min"]

        def classify(wv, cv):
            if wv and cv:
                return "WALK_AND_CYCLE_ACCESS"
            if wv and not cv:
                return "WALK_ONLY_ACCESS"
            if not wv and cv:
                return f"CYCLE_ONLY_{system_label}_GAIN"
            return "NEITHER_ACCESS"

        base[f"access_class_{t}min"] = [classify(wv, cv) for wv, cv in zip(w, c)]
    return base


def summarize_class(df: pd.DataFrame, t: int, v2: pd.DataFrame, total_pop: float, system_label: str) -> list[dict]:
    m = df.merge(v2, on="grid_id")
    out = []
    for cls, g in m.groupby(f"access_class_{t}min"):
        out.append({"system": system_label, "threshold_min": t, "access_class": cls,
                     "n_cells": len(g), "pct_cells": round(len(g) / len(m) * 100, 2),
                     "population": round(float(g["population_calibrated"].sum()), 1),
                     "pct_population": round(float(g["population_calibrated"].sum()) / total_pop * 100, 2)})
    return out


def main() -> None:
    print("=" * 72)
    print("Phase 10 Sections 9-12: gap closure, time savings, gap diagnostics, population")
    print("=" * 72)

    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet",
                          columns=["grid_id", "population_calibrated"])
    total_pop = float(v2["population_calibrated"].sum())
    origin_quality = pd.read_parquet(OUT_DIR / "_origin_quality.parquet")
    district_quality = pd.read_csv(OUT_DIR / "transit_district_quality.csv")[["district", "transit_data_quality_class"]]

    walk_a = pd.read_parquet(OUT_DIR / "walking_general_transit_accessibility.parquet")
    walk_b = pd.read_parquet(OUT_DIR / "walking_fixed_transit_accessibility.parquet")
    cyc_a = pd.read_parquet(OUT_DIR / "cycling_general_transit_accessibility.parquet")
    cyc_b = pd.read_parquet(OUT_DIR / "cycling_fixed_transit_accessibility.parquet")

    print("\n[Section 9] Walk-vs-cycle gap closure, General + Fixed systems, 5/10/15min...")
    general_comp = build_mode_comparison(walk_a, cyc_a, v2, "TRANSIT")
    fixed_comp = build_mode_comparison(walk_b, cyc_b, v2, "TRANSIT")  # spec names the class CYCLE_ONLY_TRANSIT_GAIN for both

    general_comp.to_parquet(OUT_DIR / "general_transit_mode_comparison.parquet")
    fixed_comp.to_parquet(OUT_DIR / "fixed_transit_mode_comparison.parquet")
    print(f"[save] general_transit_mode_comparison.parquet, fixed_transit_mode_comparison.parquet")

    class_summary_rows = []
    for t in THRESHOLDS:
        class_summary_rows += summarize_class(general_comp, t, v2, total_pop, "GENERAL")
        class_summary_rows += summarize_class(fixed_comp, t, v2, total_pop, "FIXED")
    class_summary_df = pd.DataFrame(class_summary_rows)
    print(class_summary_df[class_summary_df["threshold_min"] == 15].to_string(index=False))

    cycle_only_gain_15 = class_summary_df[(class_summary_df["threshold_min"] == 15) &
                                            (class_summary_df["access_class"] == "CYCLE_ONLY_TRANSIT_GAIN")]
    print(f"\n  CYCLE_ONLY_TRANSIT_GAIN @ 15min: {cycle_only_gain_15.to_dict(orient='records')}")

    print("\n[Section 10] First/last-mile time savings (both modes reach the access point)...")
    savings_rows = []
    for system_label, walk_df, cyc_df in [("GENERAL", walk_a, cyc_a), ("FIXED", walk_b, cyc_b)]:
        both = walk_df[["grid_id", "nearest_time_min"]].rename(columns={"nearest_time_min": "walk_nearest_min"}).merge(
            cyc_df[["grid_id", "nearest_time_min"]].rename(columns={"nearest_time_min": "cycle_nearest_min"}), on="grid_id"
        )
        both_reachable = both.dropna(subset=["walk_nearest_min", "cycle_nearest_min"])
        both_reachable = both_reachable.assign(time_savings_min=both_reachable["walk_nearest_min"] - both_reachable["cycle_nearest_min"])
        savings_rows.append({
            "system": system_label, "n_cells_both_reachable_15min": len(both_reachable),
            "pct_cells_both_reachable_15min": round(len(both_reachable) / len(both) * 100, 2),
            "median_time_savings_min": round(float(both_reachable["time_savings_min"].median()), 2),
            "p25_time_savings_min": round(float(both_reachable["time_savings_min"].quantile(0.25)), 2),
            "p75_time_savings_min": round(float(both_reachable["time_savings_min"].quantile(0.75)), 2),
            "p90_time_savings_min": round(float(both_reachable["time_savings_min"].quantile(0.90)), 2),
            "pct_cells_cycling_slower_than_walking": round(float((both_reachable["time_savings_min"] < 0).mean() * 100), 2),
        })
    savings_df = pd.DataFrame(savings_rows)
    print(savings_df.to_string(index=False))
    savings_df.to_csv(OUT_DIR / "transit_time_savings_summary.csv", index=False)
    print(f"[save] {OUT_DIR / 'transit_time_savings_summary.csv'}")

    print("\n[Section 11] Transit-gap diagnostics (data quality kept separate from deficit)...")
    diag_base = walk_a[["grid_id", "district"]].copy()
    has_general_10 = walk_a[f"access_{GENERAL_PRIMARY_MIN}min"].to_numpy() | cyc_a[f"access_{GENERAL_PRIMARY_MIN}min"].to_numpy()
    has_fixed_15 = walk_b[f"access_{FIXED_PRIMARY_MIN}min"].to_numpy() | cyc_b[f"access_{FIXED_PRIMARY_MIN}min"].to_numpy()
    diag_base["has_general_access_10min_either_mode"] = has_general_10
    diag_base["has_fixed_access_15min_either_mode"] = has_fixed_15

    def gap_class(hg, hf):
        if hg and hf:
            return "NO_TRANSIT_GAP"
        if hg and not hf:
            return "FIXED_GUIDEWAY_GAP"
        if not hg and hf:
            return "GENERAL_TRANSIT_GAP"  # structurally rare: reachable only 11-15min AND that point is fixed-guideway
        return "BOTH_TRANSIT_GAPS"

    diag_base["gap_class"] = [gap_class(hg, hf) for hg, hf in zip(has_general_10, has_fixed_15)]
    diag_base = diag_base.merge(origin_quality[["grid_id", "walking_quality_flag", "cycling_quality_flag"]], on="grid_id")
    diag_base = diag_base.merge(district_quality, on="district", how="left")

    def quality_uncertainty(row):
        if row["transit_data_quality_class"] in ("SUSPECT_FEED_COVERAGE", "NO_FEED_COVERAGE"):
            return "DATA_COVERAGE_UNCERTAIN"
        if row["walking_quality_flag"] not in RELIABLE_FLAGS or row["cycling_quality_flag"] not in RELIABLE_FLAGS:
            return "NETWORK_QUALITY_UNCERTAIN"
        return "RELIABLE"

    diag_base["quality_uncertainty_flag"] = diag_base.apply(quality_uncertainty, axis=1)
    diag_base = diag_base.merge(v2, on="grid_id")

    print("  gap_class counts (RAW, all cells):")
    print(diag_base["gap_class"].value_counts().to_string())
    print("\n  quality_uncertainty_flag counts:")
    print(diag_base["quality_uncertainty_flag"].value_counts().to_string())
    print("\n  gap_class x quality_uncertainty_flag cross-tab (cell counts):")
    print(pd.crosstab(diag_base["gap_class"], diag_base["quality_uncertainty_flag"]).to_string())

    diag_base.to_parquet(OUT_DIR / "transit_gap_diagnostics.parquet")
    print(f"\n[save] {OUT_DIR / 'transit_gap_diagnostics.parquet'}")

    n_reliable = int((diag_base["quality_uncertainty_flag"] == "RELIABLE").sum())
    n_both_gap_reliable = int(((diag_base["gap_class"] == "BOTH_TRANSIT_GAPS") & (diag_base["quality_uncertainty_flag"] == "RELIABLE")).sum())
    n_both_gap_total = int((diag_base["gap_class"] == "BOTH_TRANSIT_GAPS").sum())
    print(f"\n  BOTH_TRANSIT_GAPS cells: {n_both_gap_total} total, {n_both_gap_reliable} RELIABLE "
          f"(genuine deficit) vs {n_both_gap_total - n_both_gap_reliable} with data/network quality caveats")

    print("\n[Section 12] Population-weighted results, RAW vs QUALITY-AWARE...")
    reliable_mask = diag_base.set_index("grid_id")["quality_uncertainty_flag"] == "RELIABLE"

    def pop_summary_for(df: pd.DataFrame, label: str) -> dict:
        m = df.merge(v2, on="grid_id")
        m_reliable = m[m["grid_id"].map(reliable_mask).fillna(False)]
        out = {"label": label, "total_population": round(total_pop, 1)}
        for scope, mm in [("RAW", m), ("QUALITY_AWARE_RELIABLE_ONLY", m_reliable)]:
            scope_total = float(mm["population_calibrated"].sum()) if scope == "RAW" else float(mm["population_calibrated"].sum())
            denom = total_pop if scope == "RAW" else scope_total  # quality-aware denominator = reliable population itself
            entry = {}
            for t in THRESHOLDS:
                pop_t = float(mm.loc[mm[f"access_{t}min"], "population_calibrated"].sum())
                entry[f"population_within_{t}min"] = round(pop_t, 1)
                entry[f"pct_within_{t}min"] = round(pop_t / denom * 100, 2) if denom else None
            pop_unreachable = float(mm.loc[mm["nearest_time_min"].isna(), "population_calibrated"].sum())
            entry["population_unreachable_within_15min"] = round(pop_unreachable, 1)
            entry["pct_unreachable_within_15min"] = round(pop_unreachable / denom * 100, 2) if denom else None
            entry["denominator_population"] = round(denom, 1)
            out[scope] = entry
        return out

    population_summary = {
        "population_layer_caveat": "This combines calibrated 2020 population distribution with the frozen "
            "transit/network data snapshots -- NOT a 2026 population estimate.",
        "walking_general_transit": pop_summary_for(walk_a, "walking_general_transit"),
        "walking_fixed_transit": pop_summary_for(walk_b, "walking_fixed_transit"),
        "cycling_general_transit": pop_summary_for(cyc_a, "cycling_general_transit"),
        "cycling_fixed_transit": pop_summary_for(cyc_b, "cycling_fixed_transit"),
        "gap_class_population_raw": diag_base.groupby("gap_class")["population_calibrated"].sum().round(1).to_dict(),
        "gap_class_population_reliable_only": diag_base[diag_base["quality_uncertainty_flag"] == "RELIABLE"]
            .groupby("gap_class")["population_calibrated"].sum().round(1).to_dict(),
        "cycle_only_transit_gain_by_system_and_threshold": class_summary_df[
            class_summary_df["access_class"] == "CYCLE_ONLY_TRANSIT_GAIN"].to_dict(orient="records"),
    }
    (OUT_DIR / "population_transit_accessibility_summary.json").write_text(
        json.dumps(population_summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"[save] {OUT_DIR / 'population_transit_accessibility_summary.json'}")

    class_summary_df.to_csv(OUT_DIR / "transit_accessibility_gain_5_10_15.csv", index=False)
    print(f"[save] {OUT_DIR / 'transit_accessibility_gain_5_10_15.csv'}")


if __name__ == "__main__":
    main()
