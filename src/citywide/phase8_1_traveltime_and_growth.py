"""Phase 8.1 step 5: nearest required-service travel-time distributions and
the 5/10/15-minute accessibility growth curve. Descriptive validation only
-- does not recompute accessibility or change the 15-minute definition.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

APP_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city"
VAL_DIR = APP_DIR / "validation"
REQUIRED = ["A_food_groceries", "B_healthcare", "C_education"]
REQUIRED_LABELS = {"A_food_groceries": "Food/Groceries", "B_healthcare": "Healthcare", "C_education": "Education"}


def traveltime_stats(vals: pd.Series, pop: pd.Series | None = None) -> dict:
    reachable = vals.dropna()
    n_total = len(vals)
    n_reachable = len(reachable)
    stats = {
        "n_cells_total": n_total, "n_cells_reachable_within_15min": n_reachable,
        "pct_unreachable_within_15min": round((n_total - n_reachable) / n_total * 100, 2),
    }
    if n_reachable:
        stats.update({
            "median_min": round(float(reachable.median()), 2), "p25_min": round(float(reachable.quantile(0.25)), 2),
            "p75_min": round(float(reachable.quantile(0.75)), 2), "p90_min": round(float(reachable.quantile(0.9)), 2),
            "p95_min": round(float(reachable.quantile(0.95)), 2),
            "pct_within_5min": round((reachable <= 5).mean() * 100, 2),
            "pct_within_10min": round((reachable <= 10).mean() * 100, 2),
            "pct_within_15min": round((reachable <= 15).mean() * 100, 2),
        })
    if pop is not None:
        total_pop = float(pop.sum())
        reachable_pop = pop[vals.notna()]
        stats["pct_population_unreachable_within_15min"] = round((total_pop - float(reachable_pop.sum())) / total_pop * 100, 2) if total_pop else None
        if len(reachable_pop):
            w = reachable_pop.to_numpy()
            v = vals[vals.notna()].to_numpy()
            order = np.argsort(v)
            v_sorted, w_sorted = v[order], w[order]
            cum = np.cumsum(w_sorted)
            total_w = cum[-1]

            def weighted_pct(p):
                idx = np.searchsorted(cum, p * total_w)
                idx = min(idx, len(v_sorted) - 1)
                return round(float(v_sorted[idx]), 2)

            stats.update({
                "population_weighted_median_min": weighted_pct(0.5), "population_weighted_p25_min": weighted_pct(0.25),
                "population_weighted_p75_min": weighted_pct(0.75), "population_weighted_p90_min": weighted_pct(0.9),
                "population_weighted_p95_min": weighted_pct(0.95),
                "pct_population_within_5min": round(float(w_sorted[v_sorted <= 5].sum()) / total_pop * 100, 2),
                "pct_population_within_10min": round(float(w_sorted[v_sorted <= 10].sum()) / total_pop * 100, 2),
                "pct_population_within_15min": round(float(w_sorted[v_sorted <= 15].sum()) / total_pop * 100, 2),
            })
    return stats


def main() -> None:
    print("=" * 72)
    print("Phase 8.1 step 5: nearest-service travel times + accessibility growth curve")
    print("=" * 72)

    nearest = pd.read_parquet(APP_DIR / "grid_nearest_service_times.parquet")
    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet", columns=["grid_id", "population_calibrated"])
    quality = pd.read_parquet(VAL_DIR / "corrected_accessibility_quality_flags.parquet")
    acc5 = pd.read_parquet(APP_DIR / "grid_accessibility_5min.parquet")
    acc10 = pd.read_parquet(APP_DIR / "grid_accessibility_10min.parquet")
    acc15 = pd.read_parquet(APP_DIR / "grid_accessibility_15min.parquet")
    proximity = pd.read_parquet(APP_DIR / "grid_proximity_summary.parquet")

    df = nearest.merge(v2, on="grid_id").merge(quality[["grid_id", "corrected_quality_flag"]], on="grid_id")
    reliable_mask = df["corrected_quality_flag"].isin(["RELIABLE", "RELIABLE_SEPARATE_COMPONENT"])
    df_reliable = df[reliable_mask]
    print(f"\nUsing {reliable_mask.sum()}/{len(df)} quality-reliable cells for travel-time distributions "
          f"(denominator B from step 3)")

    print("\n[1/2] Travel-time distributions (required categories)...")
    tt_rows = []
    tt_full = {}
    for cat in REQUIRED:
        col = f"{cat}_nearest_time_min"
        all_stats = traveltime_stats(df[col], df["population_calibrated"])
        reliable_stats = traveltime_stats(df_reliable[col], df_reliable["population_calibrated"])
        tt_full[cat] = {"all_cells": all_stats, "quality_reliable_cells": reliable_stats}
        row = {"category": REQUIRED_LABELS[cat], **{f"all_{k}": v for k, v in all_stats.items()},
               **{f"reliable_{k}": v for k, v in reliable_stats.items()}}
        tt_rows.append(row)
        print(f"\n  {REQUIRED_LABELS[cat]} (all cells): median={all_stats.get('median_min')} p25={all_stats.get('p25_min')} "
              f"p75={all_stats.get('p75_min')} p90={all_stats.get('p90_min')} p95={all_stats.get('p95_min')} "
              f"unreachable={all_stats['pct_unreachable_within_15min']}%")
        print(f"  {REQUIRED_LABELS[cat]} (pop-weighted, all cells): median={all_stats.get('population_weighted_median_min')} "
              f"p90={all_stats.get('population_weighted_p90_min')} pop_unreachable={all_stats.get('pct_population_unreachable_within_15min')}%")

    pd.DataFrame(tt_rows).to_csv(VAL_DIR / "required_service_travel_time_stats.csv", index=False)
    print(f"\n  saved required_service_travel_time_stats.csv")

    print("\n[2/2] Accessibility growth curve 5 -> 10 -> 15 min...")
    growth_rows = []
    for cat in REQUIRED + ["COMPLETE"]:
        for t_min, acc_df in [(5, acc5), (10, acc10), (15, acc15)]:
            if cat == "COMPLETE":
                prox_t = pd.read_parquet(APP_DIR / "grid_proximity_summary.parquet")
                access_mask = prox_t[f"COMPLETE_{t_min}MIN_ACCESS"] if f"COMPLETE_{t_min}MIN_ACCESS" in prox_t.columns else None
                merged_t = prox_t.merge(v2, on="grid_id")
                n_access = int(merged_t[f"COMPLETE_{t_min}MIN_ACCESS"].sum())
                pop_access = float(merged_t.loc[merged_t[f"COMPLETE_{t_min}MIN_ACCESS"], "population_calibrated"].sum())
            else:
                merged_t = acc_df.merge(v2, on="grid_id")
                access_col = f"{cat}_access_{t_min}min"
                n_access = int(merged_t[access_col].sum())
                pop_access = float(merged_t.loc[merged_t[access_col], "population_calibrated"].sum())
            n_total = len(merged_t)
            total_pop = float(merged_t["population_calibrated"].sum())
            growth_rows.append({
                "category": cat, "threshold_min": t_min, "n_cells_accessible": n_access,
                "pct_cells_accessible": round(n_access / n_total * 100, 2),
                "population_accessible": round(pop_access, 1),
                "pct_population_accessible": round(pop_access / total_pop * 100, 2),
            })

    growth_df = pd.DataFrame(growth_rows)
    marginal_rows = []
    for cat in REQUIRED + ["COMPLETE"]:
        sub = growth_df[growth_df["category"] == cat].set_index("threshold_min")
        gain_5_10_cells = sub.loc[10, "pct_cells_accessible"] - sub.loc[5, "pct_cells_accessible"]
        gain_10_15_cells = sub.loc[15, "pct_cells_accessible"] - sub.loc[10, "pct_cells_accessible"]
        gain_5_10_pop = sub.loc[10, "pct_population_accessible"] - sub.loc[5, "pct_population_accessible"]
        gain_10_15_pop = sub.loc[15, "pct_population_accessible"] - sub.loc[10, "pct_population_accessible"]
        marginal_rows.append({"category": cat, "gain_5to10_pct_cells": round(gain_5_10_cells, 2),
                               "gain_10to15_pct_cells": round(gain_10_15_cells, 2),
                               "gain_5to10_pct_population": round(gain_5_10_pop, 2),
                               "gain_10to15_pct_population": round(gain_10_15_pop, 2)})
        print(f"  {cat}: cells 5/10/15min = {sub.loc[5,'pct_cells_accessible']}/{sub.loc[10,'pct_cells_accessible']}/{sub.loc[15,'pct_cells_accessible']}% "
              f"(gains +{gain_5_10_cells:.2f} / +{gain_10_15_cells:.2f}); "
              f"pop = {sub.loc[5,'pct_population_accessible']}/{sub.loc[10,'pct_population_accessible']}/{sub.loc[15,'pct_population_accessible']}% "
              f"(gains +{gain_5_10_pop:.2f} / +{gain_10_15_pop:.2f})")

    growth_df.to_csv(VAL_DIR / "accessibility_growth_5_10_15.csv", index=False)
    marginal_df = pd.DataFrame(marginal_rows)
    marginal_df.to_csv(VAL_DIR / "accessibility_growth_marginal_gains.csv", index=False)
    print(f"\n  saved accessibility_growth_5_10_15.csv, accessibility_growth_marginal_gains.csv")

    # Flag suspicious patterns
    concerns = []
    for _, r in marginal_df.iterrows():
        if r["gain_10to15_pct_population"] > 30:
            concerns.append(f"{r['category']}: large 10->15min population jump (+{r['gain_10to15_pct_population']}pp) -- investigate for cliff behavior")
        if r["gain_5to10_pct_population"] < 1 and r["gain_10to15_pct_population"] > 15:
            concerns.append(f"{r['category']}: near-zero growth until 15min then a jump -- investigate")
    print("\n  suspicious-pattern flags:", concerns if concerns else "none found")

    full_tt_output = {"travel_time_distributions": tt_full, "growth_curve": growth_rows, "marginal_gains": marginal_rows,
                       "suspicious_pattern_flags": concerns}
    (VAL_DIR / "traveltime_and_growth_full.json").write_text(json.dumps(full_tt_output, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
