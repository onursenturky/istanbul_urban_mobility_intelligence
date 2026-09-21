"""Phase 11, Sections 4-6: everyday-needs gap typology, cycling
gap-closure typology, and transit-access gap typology. All three
typologies are derived exclusively from already-frozen Phase 8/9/10
fields already present in the Section 1-3 synthesis table -- no new
travel-time computation.
"""

from __future__ import annotations

import json

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "accessibility_gap_intelligence"


def everyday_gap_class(row) -> str:
    if not row["everyday_access_reliable"]:
        return "UNKNOWN_OR_QUALITY_LIMITED"
    f, h, e = bool(row["food_missing"]), bool(row["healthcare_missing"]), bool(row["education_missing"])
    n = f + h + e
    if n == 0:
        return "NO_REQUIRED_GAP"
    if n == 3:
        return "ALL_REQUIRED_GAP"
    if n == 1:
        return "FOOD_GAP" if f else ("HEALTHCARE_GAP" if h else "EDUCATION_GAP")
    # n == 2
    if f and h:
        return "FOOD_HEALTHCARE_GAP"
    if f and e:
        return "FOOD_EDUCATION_GAP"
    return "HEALTHCARE_EDUCATION_GAP"


def cycling_closure(row) -> tuple[str, str]:
    if not row["everyday_access_reliable"]:
        return "CYCLING_RESULT_UNCERTAIN", "UNCERTAIN"
    missing = {"FOOD": row["food_missing"], "HEALTHCARE": row["healthcare_missing"], "EDUCATION": row["education_missing"]}
    cycle_ok = {"FOOD": (pd.notna(row["cycle_food_nearest_min"]) and row["cycle_food_nearest_min"] <= 15),
                "HEALTHCARE": (pd.notna(row["cycle_healthcare_nearest_min"]) and row["cycle_healthcare_nearest_min"] <= 15),
                "EDUCATION": (pd.notna(row["cycle_education_nearest_min"]) and row["cycle_education_nearest_min"] <= 15)}
    missing_cats = [c for c, m in missing.items() if m]
    n_missing = len(missing_cats)
    if n_missing == 0:
        return "NOT_APPLICABLE_NO_GAP", "NONE"
    closed_cats = [c for c in missing_cats if cycle_ok[c]]
    still_missing = [c for c in missing_cats if not cycle_ok[c]]
    closed_str = "+".join(closed_cats) if closed_cats else "NONE"
    if len(still_missing) == 0:
        return "FULLY_CLOSED_BY_CYCLING", closed_str
    if len(closed_cats) > 0:
        return "PARTIALLY_CLOSED_BY_CYCLING", closed_str
    return "UNCHANGED_BY_CYCLING", closed_str


def transit_gap_class(row) -> str:
    quf = row["transit_quality_uncertainty_flag"]
    if quf == "DATA_COVERAGE_UNCERTAIN":
        return "TRANSIT_DATA_UNCERTAIN"
    if quf == "NETWORK_QUALITY_UNCERTAIN":
        return "NETWORK_QUALITY_UNCERTAIN"
    mapping = {"NO_TRANSIT_GAP": "NO_TRANSIT_ACCESS_GAP", "GENERAL_TRANSIT_GAP": "GENERAL_ACCESS_GAP",
               "FIXED_GUIDEWAY_GAP": "FIXED_GUIDEWAY_ACCESS_GAP", "BOTH_TRANSIT_GAPS": "BOTH_TRANSIT_ACCESS_GAPS"}
    return mapping.get(row["transit_gap_class"], "TRANSIT_DATA_UNCERTAIN")


def main() -> None:
    print("=" * 72)
    print("Phase 11 Sections 4-6: everyday-needs / cycling-closure / transit gap typologies")
    print("=" * 72)

    df = pd.read_parquet(OUT_DIR / "accessibility_gap_grid_synthesis.parquet")
    total_pop = float(df["population_calibrated"].sum())

    print("\n[Section 4] Everyday-needs gap typology (frozen Phase 8 flags)...")
    df["everyday_gap_class"] = df.apply(everyday_gap_class, axis=1)
    en_summary = []
    for cls, g in df.groupby("everyday_gap_class"):
        en_summary.append({"gap_class": cls, "n_cells": len(g), "pct_cells": round(len(g) / len(df) * 100, 2),
                             "population": round(float(g["population_calibrated"].sum()), 1),
                             "pct_population": round(float(g["population_calibrated"].sum()) / total_pop * 100, 2)})
    en_summary_df = pd.DataFrame(en_summary).sort_values("n_cells", ascending=False)
    print(en_summary_df.to_string(index=False))

    en_typology = df[["grid_id", "district", "population_calibrated", "everyday_access_reliable",
                       "food_missing", "healthcare_missing", "education_missing", "everyday_gap_class"]]
    en_typology.to_parquet(OUT_DIR / "everyday_needs_gap_typology.parquet")
    en_summary_df.to_csv(OUT_DIR / "everyday_needs_gap_summary.csv", index=False)
    print(f"[save] everyday_needs_gap_typology.parquet, everyday_needs_gap_summary.csv")

    # Consistency check A (spec Section 15.A): NO_REQUIRED_GAP among reliable cells should equal
    # frozen COMPLETE_15MIN_ACCESS among the SAME reliable cells.
    rel = df[df["everyday_access_reliable"]]
    a_check = int((rel["everyday_gap_class"] == "NO_REQUIRED_GAP").sum()) == int(rel["WALKING_COMPLETE_15MIN_ACCESS"].sum())
    print(f"  [inline check A] NO_REQUIRED_GAP count == COMPLETE_15MIN_ACCESS count (reliable cells only): {a_check}")

    print("\n[Section 5] Cycling gap-closure typology (only for cells WITH a walking gap)...")
    closure_results = df.apply(cycling_closure, axis=1, result_type="expand")
    closure_results.columns = ["cycling_closure_status", "cycling_closed_categories"]
    df = pd.concat([df, closure_results], axis=1)

    gap_cells = df[~df["everyday_gap_class"].isin(["NO_REQUIRED_GAP"])].copy()
    # UNKNOWN_OR_QUALITY_LIMITED cells already route to CYCLING_RESULT_UNCERTAIN via cycling_closure()
    closure_summary = []
    for cls, g in gap_cells.groupby("cycling_closure_status"):
        closure_summary.append({"closure_status": cls, "n_cells": len(g), "pct_of_gap_cells": round(len(g) / len(gap_cells) * 100, 2),
                                  "population": round(float(g["population_calibrated"].sum()), 1)})
    closure_summary_df = pd.DataFrame(closure_summary)
    print(closure_summary_df.to_string(index=False))

    closure_out = gap_cells[["grid_id", "district", "population_calibrated", "everyday_gap_class",
                              "cycling_closure_status", "cycling_closed_categories", "everyday_access_reliable"]]
    closure_out.to_parquet(OUT_DIR / "cycling_gap_closure.parquet")
    closure_summary_df.to_csv(OUT_DIR / "cycling_gap_closure_summary.csv", index=False)
    print(f"[save] cycling_gap_closure.parquet, cycling_gap_closure_summary.csv")

    # Consistency check B: FULLY_CLOSED_BY_CYCLING should align with frozen CYCLE_ONLY_GAIN / CYCLING_COMPLETE_15MIN_ACCESS
    fully_closed = gap_cells[gap_cells["cycling_closure_status"] == "FULLY_CLOSED_BY_CYCLING"]
    b_check_rate = float(fully_closed["CYCLE_ONLY_GAIN"].mean()) if len(fully_closed) else None
    print(f"  [inline check B] of FULLY_CLOSED_BY_CYCLING cells, {b_check_rate*100 if b_check_rate is not None else 'n/a'}% "
          f"are also flagged CYCLE_ONLY_GAIN in frozen Phase 9 (expected: very close to 100% for RELIABLE gap cells "
          f"without a walking gap already closed some other way -- see Phase 11 consistency test B for the full check)")

    print("\n[Section 6] Transit access gap typology (QUALITY-AWARE headline, RAW retained as diagnostic)...")
    df["transit_access_gap_class"] = df.apply(transit_gap_class, axis=1)
    transit_summary = []
    for cls, g in df.groupby("transit_access_gap_class"):
        transit_summary.append({"gap_class": cls, "n_cells": len(g), "pct_cells": round(len(g) / len(df) * 100, 2),
                                  "population": round(float(g["population_calibrated"].sum()), 1),
                                  "pct_population": round(float(g["population_calibrated"].sum()) / total_pop * 100, 2)})
    transit_summary_df = pd.DataFrame(transit_summary).sort_values("n_cells", ascending=False)
    print(transit_summary_df.to_string(index=False))

    transit_typology_out = df[["grid_id", "district", "population_calibrated", "transit_gap_class",
                                "transit_quality_uncertainty_flag", "transit_access_gap_class"]].rename(
        columns={"transit_gap_class": "transit_gap_class_RAW_diagnostic_phase10"}
    )
    transit_typology_out.to_parquet(OUT_DIR / "transit_access_gap_typology.parquet")
    transit_summary_df.to_csv(OUT_DIR / "transit_access_gap_summary.csv", index=False)
    print(f"[save] transit_access_gap_typology.parquet, transit_access_gap_summary.csv")

    df.to_parquet(OUT_DIR / "accessibility_gap_grid_synthesis.parquet")
    print(f"\n[save] accessibility_gap_grid_synthesis.parquet (updated with gap-typology columns)")

    (OUT_DIR / "_phase11_gap_typology_inline_checks.json").write_text(
        json.dumps({"check_A_no_required_gap_matches_complete_access": a_check,
                    "check_B_fully_closed_cycle_only_gain_rate": b_check_rate}, indent=2, default=str), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
