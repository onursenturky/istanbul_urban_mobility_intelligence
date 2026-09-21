"""Phase 8.1 step 3: reproduce the original 82.49% population-accessibility
result exactly, then report it under three transparent, increasingly
conservative denominators using the corrected quality classification.

Denominators:
  A. ALL POPULATED CELLS -- the original Phase 8 raw citywide result,
     reproduced exactly (population-weighted over all 22,322 cells; cells
     with zero population contribute zero to both numerator and
     denominator, so this is equivalent to "all cells" or "all populated
     cells").
  B. QUALITY-RELIABLE POPULATED CELLS -- corrected_quality_flag in
     {RELIABLE, RELIABLE_SEPARATE_COMPONENT} (excludes QUESTIONABLE_ANCHOR,
     KNOWN_NETWORK_LIMITATION_ADALAR, SMALL_COMPONENT_CAUTION).
  C. STRICT HIGH-CONFIDENCE CELLS -- B, further restricted to cells whose
     walking anchor sits in a MAJOR_VALID_COMPONENT (one of the two
     dominant regional networks only, excluding the 82 smaller-but-real
     local components) -- the most conservative, least assumption-laden
     denominator.
"""

from __future__ import annotations

import json

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

APP_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city"
VAL_DIR = APP_DIR / "validation"


def denom_stats(df: pd.DataFrame, mask: pd.Series, label: str, full_pop: float) -> dict:
    sub = df[mask]
    included_pop = float(sub["population_calibrated"].sum())
    complete_pop = float(sub.loc[sub["COMPLETE_15MIN_ACCESS"], "population_calibrated"].sum())
    return {
        "label": label, "n_included_cells": int(mask.sum()),
        "included_calibrated_population": round(included_pop, 1),
        "population_with_complete_access": round(complete_pop, 1),
        "pct_with_complete_access": round(complete_pop / included_pop * 100, 2) if included_pop else None,
        "population_excluded_by_qa": round(full_pop - included_pop, 1),
        "pct_of_total_population_excluded": round((full_pop - included_pop) / full_pop * 100, 2),
    }


def main() -> None:
    print("=" * 72)
    print("Phase 8.1 step 3: population accessibility validation (3 denominators)")
    print("=" * 72)

    proximity = pd.read_parquet(APP_DIR / "grid_proximity_summary.parquet")
    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet", columns=["grid_id", "population_calibrated"])
    quality = pd.read_parquet(VAL_DIR / "corrected_accessibility_quality_flags.parquet")

    df = proximity.merge(v2, on="grid_id").merge(
        quality[["grid_id", "corrected_quality_flag", "component_class"]], on="grid_id"
    )

    print("\n[1/2] Reproducing the original raw 82.49% result...")
    total_pop = float(df["population_calibrated"].sum())
    complete_pop_raw = float(df.loc[df["COMPLETE_15MIN_ACCESS"], "population_calibrated"].sum())
    pct_raw = complete_pop_raw / total_pop * 100
    print(f"  total calibrated population: {total_pop:,.1f}")
    print(f"  population with complete access: {complete_pop_raw:,.1f}")
    print(f"  pct: {pct_raw:.2f}% (original report: 82.49%, {'MATCHES' if abs(pct_raw - 82.49) < 0.01 else 'DOES NOT MATCH -- INVESTIGATE'})")

    print("\n[2/2] Denominators A / B / C...")
    mask_a = pd.Series(True, index=df.index)
    mask_b = df["corrected_quality_flag"].isin(["RELIABLE", "RELIABLE_SEPARATE_COMPONENT"])
    mask_c = mask_b & (df["component_class"] == "MAJOR_VALID_COMPONENT")

    result_a = denom_stats(df, mask_a, "A_ALL_POPULATED_CELLS", total_pop)
    result_b = denom_stats(df, mask_b, "B_QUALITY_RELIABLE_CELLS", total_pop)
    result_c = denom_stats(df, mask_c, "C_STRICT_HIGH_CONFIDENCE_CELLS", total_pop)

    for r in [result_a, result_b, result_c]:
        print(f"\n  {r['label']}: n_cells={r['n_included_cells']}, pop_included={r['included_calibrated_population']:,.0f}, "
              f"complete_access_pop={r['population_with_complete_access']:,.0f}, pct={r['pct_with_complete_access']}%, "
              f"pop_excluded={r['population_excluded_by_qa']:,.0f} ({r['pct_of_total_population_excluded']}%)")

    output = {
        "reproduction_check": {
            "total_calibrated_population": round(total_pop, 1), "population_with_complete_access": round(complete_pop_raw, 1),
            "reproduced_pct": round(pct_raw, 2), "original_reported_pct": 82.49,
            "matches_original": bool(abs(pct_raw - 82.49) < 0.01),
        },
        "denominator_A_all_populated_cells": result_a,
        "denominator_B_quality_reliable_cells": result_b,
        "denominator_C_strict_high_confidence_cells": result_c,
        "interpretation": "The gap between A and B/C (if any) shows how much of the raw 82.49% figure rests on "
            "cells whose network representation is questionable/limited, as opposed to genuinely well-represented "
            "network structure. A large A-to-C drop would mean the headline figure is NOT quality-robust; a small "
            "drop means it is.",
    }
    (VAL_DIR / "population_accessibility_validation.json").write_text(json.dumps(output, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[save] {VAL_DIR / 'population_accessibility_validation.json'}")


if __name__ == "__main__":
    main()
