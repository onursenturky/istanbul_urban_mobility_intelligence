"""Phase 9, Sections 6-11: CYCLING_COMPLETE_15MIN_ACCESS, walking-vs-cycling
core comparison, category-level gain, gain curves, walking-deficit closure,
and high-value active-mobility gain cells.

This is a DIRECT NETWORK MEASUREMENT joining two already-computed
accessibility results by grid_id -- NOT an MCDA score, no arbitrary
weights. Frozen walking artifacts (Phase 8/8.1) are read-only; nothing
under analysis/applications/15min_city/ is modified.
"""

from __future__ import annotations

import json

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

WALK_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city"
OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "cycling_accessibility"
CATEGORIES = ["A_food_groceries", "B_healthcare", "C_education", "D_daily_services",
              "E_retail_shopping", "F_leisure_social", "G_green_recreation", "H_public_transport_access"]
REQUIRED = ["A_food_groceries", "B_healthcare", "C_education"]
REQUIRED_SHORT = {"A_food_groceries": "FOOD", "B_healthcare": "HEALTHCARE", "C_education": "EDUCATION"}
THRESHOLDS = [5, 10, 15]


def build_cycling_proximity() -> pd.DataFrame:
    acc = {t: pd.read_parquet(OUT_DIR / f"cycling_accessibility_{t}min.parquet") for t in THRESHOLDS}
    base = acc[15][["grid_id", "district"]].copy()
    for t_min, df in acc.items():
        access_cols = [f"{c}_access_{t_min}min" for c in CATEGORIES]
        base[f"cycling_categories_accessible_{t_min}min"] = df[access_cols].sum(axis=1).to_numpy()
        req_cols = [f"{c}_access_{t_min}min" for c in REQUIRED]
        base[f"cycling_required_categories_accessible_{t_min}min"] = df[req_cols].sum(axis=1).to_numpy()
        base[f"CYCLING_COMPLETE_{t_min}MIN_ACCESS"] = (df[req_cols].sum(axis=1) == len(REQUIRED)).to_numpy()
    return base


def main() -> None:
    print("=" * 72)
    print("Phase 9 Sections 6-11: cycling complete access + walk-vs-cycle comparison")
    print("=" * 72)

    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet",
                          columns=["grid_id", "population_calibrated"])
    total_pop = float(v2["population_calibrated"].sum())

    print("\n[Section 6] Building CYCLING_COMPLETE_15MIN_ACCESS...")
    cyc_prox = build_cycling_proximity()
    cyc_prox_pop = cyc_prox.merge(v2, on="grid_id")
    n_complete_cyc = int(cyc_prox["CYCLING_COMPLETE_15MIN_ACCESS"].sum())
    pop_complete_cyc = float(cyc_prox_pop.loc[cyc_prox_pop["CYCLING_COMPLETE_15MIN_ACCESS"], "population_calibrated"].sum())
    print(f"  CYCLING_COMPLETE_15MIN_ACCESS: {n_complete_cyc}/{len(cyc_prox)} cells "
          f"({n_complete_cyc/len(cyc_prox)*100:.2f}%), population {pop_complete_cyc:,.0f}/{total_pop:,.0f} "
          f"({pop_complete_cyc/total_pop*100:.2f}%)")

    print("\n[Section 7] Walking vs cycling access classification...")
    walk_prox = pd.read_parquet(WALK_DIR / "grid_proximity_summary.parquet")[
        ["grid_id", "district", "categories_accessible_15min", "required_categories_accessible_15min", "COMPLETE_15MIN_ACCESS"]
    ].rename(columns={
        "categories_accessible_15min": "walking_categories_accessible_15min",
        "required_categories_accessible_15min": "walking_required_categories_accessible_15min",
        "COMPLETE_15MIN_ACCESS": "WALKING_COMPLETE_15MIN_ACCESS",
    })
    comp = walk_prox.merge(cyc_prox[["grid_id", "cycling_categories_accessible_15min",
                                      "cycling_required_categories_accessible_15min", "CYCLING_COMPLETE_15MIN_ACCESS"]],
                            on="grid_id")

    def classify(row):
        w, c = row["WALKING_COMPLETE_15MIN_ACCESS"], row["CYCLING_COMPLETE_15MIN_ACCESS"]
        if w and c:
            return "WALK_AND_CYCLE_ACCESS"
        if w and not c:
            return "WALK_ONLY_ACCESS"
        if not w and c:
            return "CYCLE_ONLY_GAIN"
        return "NEITHER_ACCESS"

    comp["access_class"] = comp.apply(classify, axis=1)
    comp = comp.merge(v2, on="grid_id")

    print(comp["access_class"].value_counts().to_string())
    class_summary = []
    for cls, g in comp.groupby("access_class"):
        class_summary.append({
            "access_class": cls, "n_cells": len(g), "pct_cells": round(len(g) / len(comp) * 100, 2),
            "population": round(float(g["population_calibrated"].sum()), 1),
            "pct_population": round(float(g["population_calibrated"].sum()) / total_pop * 100, 2),
        })
    class_summary_df = pd.DataFrame(class_summary).sort_values("n_cells", ascending=False)
    print(class_summary_df.to_string(index=False))

    comp.drop(columns=["population_calibrated"]).to_parquet(OUT_DIR / "walking_cycling_complete_access_comparison.parquet")
    print(f"\n[save] {OUT_DIR / 'walking_cycling_complete_access_comparison.parquet'}")

    print("\n[Section 8] Category-level accessibility gain (required categories)...")
    walk_nearest = pd.read_parquet(WALK_DIR / "grid_nearest_service_times.parquet")
    cyc_nearest = pd.read_parquet(OUT_DIR / "cycling_nearest_service_times.parquet")
    gain_df = walk_nearest[["grid_id", "district"]].copy()
    cat_gain_rows = []
    for c in REQUIRED:
        wcol, ccol = f"{c}_nearest_time_min", f"{c}_nearest_time_min"
        gain_df[f"{c}_walking_nearest_time_min"] = walk_nearest[wcol].to_numpy()
        gain_df[f"{c}_cycling_nearest_time_min"] = cyc_nearest[ccol].to_numpy()
        w = gain_df[f"{c}_walking_nearest_time_min"]
        cy = gain_df[f"{c}_cycling_nearest_time_min"]
        gain_df[f"{c}_time_reduction_min"] = (w - cy).where(w.notna() & cy.notna())
        gain_df[f"{c}_walk_inaccessible_cycle_accessible"] = w.isna() & cy.notna()

    gain_pop = gain_df.merge(v2, on="grid_id")
    for c in REQUIRED:
        transitioned = gain_pop[f"{c}_walk_inaccessible_cycle_accessible"]
        improved = gain_pop[f"{c}_time_reduction_min"] > 0
        cat_gain_rows.append({
            "category": REQUIRED_SHORT[c],
            "n_cells_walk_inaccessible_cycle_accessible": int(transitioned.sum()),
            "population_walk_inaccessible_cycle_accessible": round(float(gain_pop.loc[transitioned, "population_calibrated"].sum()), 1),
            "n_cells_time_reduced_when_both_accessible": int(improved.sum()),
            "median_time_reduction_min_when_both_accessible": round(float(gain_pop.loc[improved, f"{c}_time_reduction_min"].median()), 2) if improved.any() else None,
            "population_benefiting_any_improvement": round(float(gain_pop.loc[transitioned | improved, "population_calibrated"].sum()), 1),
        })
    cat_gain_summary = pd.DataFrame(cat_gain_rows)
    print(cat_gain_summary.to_string(index=False))
    gain_df.to_parquet(OUT_DIR / "walking_cycling_category_gain.parquet")
    print(f"[save] {OUT_DIR / 'walking_cycling_category_gain.parquet'}")

    print("\n[Section 9] Accessibility gain curves at 5/10/15 min...")
    walk_acc = {t: pd.read_parquet(WALK_DIR / f"grid_accessibility_{t}min.parquet") for t in THRESHOLDS}
    cyc_acc = {t: pd.read_parquet(OUT_DIR / f"cycling_accessibility_{t}min.parquet") for t in THRESHOLDS}
    curve_rows = []
    for t in THRESHOLDS:
        wdf = walk_acc[t].merge(v2, on="grid_id")
        cdf = cyc_acc[t].merge(v2, on="grid_id")
        for c in REQUIRED:
            wcol, ccol = f"{c}_access_{t}min", f"{c}_access_{t}min"
            w_pct_cells = round(float(wdf[wcol].mean() * 100), 2)
            c_pct_cells = round(float(cdf[ccol].mean() * 100), 2)
            w_pct_pop = round(float(wdf.loc[wdf[wcol], "population_calibrated"].sum()) / total_pop * 100, 2)
            c_pct_pop = round(float(cdf.loc[cdf[ccol], "population_calibrated"].sum()) / total_pop * 100, 2)
            curve_rows.append({"metric": REQUIRED_SHORT[c], "threshold_min": t,
                                "walking_pct_cells": w_pct_cells, "cycling_pct_cells": c_pct_cells,
                                "diff_pct_cells": round(c_pct_cells - w_pct_cells, 2),
                                "walking_pct_population": w_pct_pop, "cycling_pct_population": c_pct_pop,
                                "diff_pct_population": round(c_pct_pop - w_pct_pop, 2)})
        # complete access
        w_req_cols = [f"{c}_access_{t}min" for c in REQUIRED]
        w_complete = (wdf[w_req_cols].sum(axis=1) == len(REQUIRED))
        c_complete = (cdf[w_req_cols].sum(axis=1) == len(REQUIRED))
        w_pct_cells = round(float(w_complete.mean() * 100), 2)
        c_pct_cells = round(float(c_complete.mean() * 100), 2)
        w_pct_pop = round(float(wdf.loc[w_complete, "population_calibrated"].sum()) / total_pop * 100, 2)
        c_pct_pop = round(float(cdf.loc[c_complete, "population_calibrated"].sum()) / total_pop * 100, 2)
        curve_rows.append({"metric": "COMPLETE_ACCESS", "threshold_min": t,
                            "walking_pct_cells": w_pct_cells, "cycling_pct_cells": c_pct_cells,
                            "diff_pct_cells": round(c_pct_cells - w_pct_cells, 2),
                            "walking_pct_population": w_pct_pop, "cycling_pct_population": c_pct_pop,
                            "diff_pct_population": round(c_pct_pop - w_pct_pop, 2)})
    curve_df = pd.DataFrame(curve_rows)
    print(curve_df.to_string(index=False))
    curve_df.to_csv(OUT_DIR / "accessibility_gain_5_10_15.csv", index=False)
    print(f"[save] {OUT_DIR / 'accessibility_gain_5_10_15.csv'}")
    largest_marginal = curve_df.loc[curve_df["diff_pct_population"].idxmax()]
    print(f"\n  largest marginal cycling population-share addition: {largest_marginal['metric']} "
          f"@ {largest_marginal['threshold_min']}min (+{largest_marginal['diff_pct_population']}pp)")

    print("\n[Section 10] Walking-deficit closure by cycling...")
    deficits = pd.read_parquet(WALK_DIR / "accessibility_deficit_classes.parquet")
    acc15_cyc = cyc_acc[15]
    req_cols_cyc = [f"{c}_access_15min" for c in REQUIRED]
    closure = deficits[deficits["deficit_class"] != "NONE_COMPLETE_ACCESS"][
        ["grid_id", "district", "deficit_class", "n_required_categories_missing_15min", "food_missing", "healthcare_missing", "education_missing"]
    ].merge(acc15_cyc[["grid_id"] + req_cols_cyc], on="grid_id")
    closure["cycling_required_accessible_count"] = closure[req_cols_cyc].sum(axis=1)
    closure["n_still_missing_with_cycling"] = 0
    for c, miscol in zip(REQUIRED, ["food_missing", "healthcare_missing", "education_missing"]):
        still_missing = closure[miscol] & ~closure[f"{c}_access_15min"]
        closure["n_still_missing_with_cycling"] += still_missing.astype(int)

    def closure_status(row):
        if row["n_still_missing_with_cycling"] == 0:
            return "FULLY_CLOSED_BY_CYCLING"
        if row["n_still_missing_with_cycling"] < row["n_required_categories_missing_15min"]:
            return "PARTIALLY_CLOSED_BY_CYCLING"
        return "UNCHANGED_BY_CYCLING"

    closure["closure_status"] = closure.apply(closure_status, axis=1)
    closure_pop = closure.merge(v2, on="grid_id")
    closure_summary = []
    for status, g in closure_pop.groupby("closure_status"):
        closure_summary.append({
            "closure_status": status, "n_cells": len(g), "pct_of_deficit_cells": round(len(g) / len(closure_pop) * 100, 2),
            "population": round(float(g["population_calibrated"].sum()), 1),
        })
    closure_summary_df = pd.DataFrame(closure_summary)
    print(closure_summary_df.to_string(index=False))
    closure_pop.drop(columns=["population_calibrated"]).to_csv(OUT_DIR / "walking_deficit_closure.csv", index=False)
    print(f"[save] {OUT_DIR / 'walking_deficit_closure.csv'}")

    print("\n[Section 11] High-value active-mobility gain cells (interpretable fields, NO arbitrary score)...")
    hv = comp.merge(gain_df[["grid_id"] + [f"{c}_time_reduction_min" for c in REQUIRED] +
                             [f"{c}_walk_inaccessible_cycle_accessible" for c in REQUIRED]], on="grid_id")
    hv["categories_gained_required"] = hv["cycling_required_categories_accessible_15min"] - hv["walking_required_categories_accessible_15min"]
    hv["categories_gained_required"] = hv["categories_gained_required"].clip(lower=0)
    # Data-driven population threshold: median of POPULATED cells (descriptive, not a score cutoff)
    pop_median_nonzero = float(v2.loc[v2["population_calibrated"] > 0, "population_calibrated"].median())
    hv["meaningful_population"] = hv["population_calibrated"] >= pop_median_nonzero
    hv["substantial_cycling_improvement"] = (hv["access_class"] == "CYCLE_ONLY_GAIN") | (hv["categories_gained_required"] >= 1)
    hv["high_value_gain_cell"] = hv["meaningful_population"] & hv["substantial_cycling_improvement"]

    out_cols = ["grid_id", "district", "population_calibrated",
                "walking_required_categories_accessible_15min", "cycling_required_categories_accessible_15min",
                "categories_gained_required", "WALKING_COMPLETE_15MIN_ACCESS", "CYCLING_COMPLETE_15MIN_ACCESS",
                "access_class"] + [f"{c}_time_reduction_min" for c in REQUIRED] + \
               [f"{c}_walk_inaccessible_cycle_accessible" for c in REQUIRED] + \
               ["meaningful_population", "substantial_cycling_improvement", "high_value_gain_cell"]
    hv[out_cols].to_parquet(OUT_DIR / "active_mobility_gain_cells.parquet")
    n_hv = int(hv["high_value_gain_cell"].sum())
    pop_hv = float(hv.loc[hv["high_value_gain_cell"], "population_calibrated"].sum())
    print(f"  high_value_gain_cell threshold: population >= {pop_median_nonzero:.1f} (median of populated cells) "
          f"AND (CYCLE_ONLY_GAIN OR >=1 required category gained)")
    print(f"  {n_hv} cells ({n_hv/len(hv)*100:.2f}%), population {pop_hv:,.0f} ({pop_hv/total_pop*100:.2f}%)")
    print(f"[save] {OUT_DIR / 'active_mobility_gain_cells.parquet'}")

    print("\n[Summary] Writing population_cycling_accessibility_summary.json...")
    summary = {
        "population_layer_caveat": "Calibrated 2020 population vs 2026 network/destination snapshot -- same "
            "temporal caveat as Phase 8.",
        "total_calibrated_population_2020": round(total_pop, 1),
        "cycling_complete_15min_access": {
            "n_cells": n_complete_cyc, "pct_cells": round(n_complete_cyc / len(cyc_prox) * 100, 2),
            "population": round(pop_complete_cyc, 1), "pct_population": round(pop_complete_cyc / total_pop * 100, 2),
        },
        "walk_vs_cycle_access_class_summary": class_summary_df.to_dict(orient="records"),
        "category_gain_summary": cat_gain_summary.to_dict(orient="records"),
        "largest_marginal_cycling_gain": largest_marginal.to_dict(),
        "walking_deficit_closure_summary": closure_summary_df.to_dict(orient="records"),
        "high_value_gain_cells": {
            "definition": "population >= median populated-cell population AND "
                           "(CYCLE_ONLY_GAIN access class OR >=1 required category gained within 15min) -- "
                           "descriptive filter, NOT a weighted/arbitrary score.",
            "n_cells": n_hv, "pct_cells": round(n_hv / len(hv) * 100, 2),
            "population": round(pop_hv, 1), "pct_population": round(pop_hv / total_pop * 100, 2),
        },
    }
    (OUT_DIR / "population_cycling_accessibility_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"[save] {OUT_DIR / 'population_cycling_accessibility_summary.json'}")


if __name__ == "__main__":
    main()
