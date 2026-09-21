"""Citywide coverage-gate check, run per feature family before proceeding to
the next family (and before any suitability work).

For a given per-cell numeric feature (or set of features), reports:
  - expected geographic coverage (all 39 districts, since every district
    has at least some land/road/building presence)
  - observed coverage: % of cells with a non-null value, % with a
    strictly-zero value, broken down by district
  - whether zero cells concentrate suspiciously in specific districts
    (which would suggest truncation) vs. spreading in a pattern consistent
    with genuine sparsity (e.g. zero POIs in a rural district cell)
  - a simple "concentration check": what fraction of the citywide TOTAL
    (sum) falls inside the original 3-district pilot area — if this is
    implausibly high relative to the pilot's area share of the city
    (114/5454 = 2.1%), that is the specific "silently only fetched the
    pilot area" failure mode this gate exists to catch.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

PILOT_DISTRICTS = {"Kadıköy", "Üsküdar", "Maltepe"}
PILOT_AREA_SHARE_OF_CITY = 114.42 / 5453.98  # from Phase 1-2 vs Section 1, ~2.1%


def coverage_report(features: gpd.GeoDataFrame, value_cols: list[str], district_col: str = "district") -> dict:
    n_cells = len(features)
    n_districts = features[district_col].nunique()
    report = {"n_cells": n_cells, "n_districts_present": n_districts, "columns": {}}

    for col in value_cols:
        vals = features[col]
        n_null = int(vals.isna().sum())
        n_zero = int((vals == 0).sum())
        n_nonzero_nonnull = n_cells - n_null - n_zero

        by_district = features.groupby(district_col)[col].agg(
            n_cells="size",
            n_zero=lambda s: int((s == 0).sum()),
            n_null=lambda s: int(s.isna().sum()),
            total=lambda s: float(s.fillna(0).sum()),
        )
        by_district["pct_zero_or_null"] = (by_district["n_zero"] + by_district["n_null"]) / by_district["n_cells"] * 100
        districts_all_zero_or_null = by_district[by_district["pct_zero_or_null"] >= 99.9].index.tolist()

        pilot_total = float(features.loc[features[district_col].isin(PILOT_DISTRICTS), col].fillna(0).sum())
        city_total = float(vals.fillna(0).sum())
        pilot_share = pilot_total / city_total if city_total else float("nan")

        report["columns"][col] = {
            "n_null": n_null,
            "n_zero": n_zero,
            "n_nonzero": n_nonzero_nonnull,
            "pct_null": round(n_null / n_cells * 100, 2),
            "pct_zero": round(n_zero / n_cells * 100, 2),
            "districts_fully_zero_or_null": districts_all_zero_or_null,
            "n_districts_fully_zero_or_null": len(districts_all_zero_or_null),
            "citywide_total": city_total,
            "pilot_3district_total": pilot_total,
            "pilot_share_of_citywide_total_pct": round(pilot_share * 100, 2) if city_total else None,
            "expected_pilot_share_if_uniform_pct": round(PILOT_AREA_SHARE_OF_CITY * 100, 2),
            "concentration_flag": (
                "SUSPICIOUS: pilot 3 districts hold >50% of the citywide total despite being ~2% of the "
                "city's area — check for truncated/incomplete citywide fetch"
                if city_total and pilot_share > 0.5 else "ok"
            ),
        }
    return report


def print_report(report: dict, family_name: str) -> None:
    print(f"\n=== COVERAGE GATE: {family_name} ===")
    print(f"n_cells={report['n_cells']}  n_districts_present={report['n_districts_present']} (expect 39)")
    for col, r in report["columns"].items():
        print(f"\n  {col}:")
        print(f"    null={r['n_null']} ({r['pct_null']}%)  zero={r['n_zero']} ({r['pct_zero']}%)  nonzero={r['n_nonzero']}")
        print(f"    districts fully zero/null: {r['n_districts_fully_zero_or_null']} {r['districts_fully_zero_or_null']}")
        print(f"    pilot-3-district share of citywide total: {r['pilot_share_of_citywide_total_pct']}% "
              f"(expected ~{r['expected_pilot_share_if_uniform_pct']}% if uniform)  -> {r['concentration_flag']}")
