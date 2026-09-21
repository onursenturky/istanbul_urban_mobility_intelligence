"""Phase 8.1 step 6: required-category bottleneck analysis (which
required category, or combination, causes COMPLETE_15MIN_ACCESS failure),
and descriptive threshold sensitivity at 10/15/20 minutes for the three
required categories only.

The 20-minute figure is a NEW, lightweight query using the EXISTING
walking graph, EXISTING destination anchors, and EXISTING cutoff-Dijkstra
engine (src/network/accessibility.py) -- no network rebuild, no new POI
taxonomy, just a larger cutoff on already-frozen inputs, restricted to the
3 required categories to keep it cheap. This does NOT change the official
15-minute COMPLETE_15MIN_ACCESS definition anywhere.
"""

from __future__ import annotations

import json
import time
from collections import Counter

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.network import accessibility, network_builder
from src.utils import config as cfg

APP_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city"
VAL_DIR = APP_DIR / "validation"
REQUIRED = ["A_food_groceries", "B_healthcare", "C_education"]
REQUIRED_SHORT = {"A_food_groceries": "FOOD", "B_healthcare": "HEALTHCARE", "C_education": "EDUCATION"}


def main() -> None:
    print("=" * 72)
    print("Phase 8.1 step 6: bottleneck analysis + threshold sensitivity (10/15/20 min)")
    print("=" * 72)

    acc15 = pd.read_parquet(APP_DIR / "grid_accessibility_15min.parquet")
    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet", columns=["grid_id", "population_calibrated"])
    merged = acc15.merge(v2, on="grid_id")

    print("\n[1/2] Bottleneck combinations (which required category fails)...")

    def bottleneck(row):
        missing = [REQUIRED_SHORT[c] for c in REQUIRED if not row[f"{c}_access_15min"]]
        if not missing:
            return "COMPLETE"
        return "+".join(missing)

    merged["bottleneck"] = merged.apply(bottleneck, axis=1)
    bottleneck_cells = merged["bottleneck"].value_counts()
    bottleneck_pop = merged.groupby("bottleneck")["population_calibrated"].sum().round(1)
    bottleneck_df = pd.DataFrame({"n_cells": bottleneck_cells, "population": bottleneck_pop}).fillna(0)
    bottleneck_df["pct_cells"] = (bottleneck_df["n_cells"] / len(merged) * 100).round(2)
    bottleneck_df["pct_population"] = (bottleneck_df["population"] / merged["population_calibrated"].sum() * 100).round(2)
    bottleneck_df = bottleneck_df.sort_values("n_cells", ascending=False).reset_index()
    bottleneck_df = bottleneck_df.rename(columns={bottleneck_df.columns[0]: "bottleneck_combination"})
    print(bottleneck_df.to_string(index=False))

    incomplete = bottleneck_df[bottleneck_df["bottleneck_combination"] != "COMPLETE"]
    most_common_by_cells = incomplete.iloc[0]
    most_common_by_pop = incomplete.sort_values("population", ascending=False).iloc[0]
    print(f"\n  most common bottleneck by cell count: {most_common_by_cells['bottleneck_combination']} "
          f"({most_common_by_cells['n_cells']} cells)")
    print(f"  most common bottleneck by population: {most_common_by_pop['bottleneck_combination']} "
          f"({most_common_by_pop['population']:,.0f} people)")

    bottleneck_df.to_csv(VAL_DIR / "required_category_bottlenecks.csv", index=False)
    print(f"  saved required_category_bottlenecks.csv")

    print("\n[2/2] Threshold sensitivity: running a NEW lightweight 20-min query (required categories only)...")
    G_walk = network_builder.load_graph("walking_graph")
    anchors = pd.read_parquet(cfg.PROJECT_ROOT / "analysis" / "network_intelligence" / "grid_network_anchors.parquet")
    dest = pd.read_parquet(APP_DIR / "poi_network_anchors.parquet")
    dest_ok = dest[(dest["snap_status"] == "OK") & (dest["poi_category"].isin(REQUIRED))]
    dest_nodes_by_cat = {cat: Counter(dest_ok[dest_ok["poi_category"] == cat]["network_node"].tolist()) for cat in REQUIRED}

    t0 = time.time()
    rows_20min = []
    for _, row in anchors.iterrows():
        origin = row["walking_anchor_node"]
        reachable = accessibility.reachable_from_node(G_walk, origin, "travel_time_walk_s", 20 * 60)
        rec = {"grid_id": row["grid_id"]}
        for cat in REQUIRED:
            node_counts = dest_nodes_by_cat[cat]
            rec[f"{cat}_access_20min"] = any(n in reachable for n in node_counts)
        rows_20min.append(rec)
    elapsed = time.time() - t0
    print(f"  20-min query done in {elapsed:.1f}s for {len(anchors)} origins")

    acc20 = pd.DataFrame(rows_20min).merge(v2, on="grid_id")
    acc10 = pd.read_parquet(APP_DIR / "grid_accessibility_10min.parquet").merge(v2, on="grid_id")
    acc15_v = acc15.merge(v2, on="grid_id")

    sens_rows = []
    for cat in REQUIRED:
        for t_min, df_t in [(10, acc10), (15, acc15_v), (20, acc20)]:
            col = f"{cat}_access_{t_min}min"
            n_access = int(df_t[col].sum())
            pop_access = float(df_t.loc[df_t[col], "population_calibrated"].sum())
            sens_rows.append({"category": REQUIRED_SHORT[cat], "threshold_min": t_min,
                               "pct_cells_accessible": round(n_access / len(df_t) * 100, 2),
                               "pct_population_accessible": round(pop_access / df_t["population_calibrated"].sum() * 100, 2)})
    sens_df = pd.DataFrame(sens_rows)
    print(sens_df.to_string(index=False))

    # cliff check: is the 10->15 or 15->20 jump disproportionate?
    cliff_flags = []
    for cat in [REQUIRED_SHORT[c] for c in REQUIRED]:
        sub = sens_df[sens_df["category"] == cat].set_index("threshold_min")
        j1 = sub.loc[15, "pct_population_accessible"] - sub.loc[10, "pct_population_accessible"]
        j2 = sub.loc[20, "pct_population_accessible"] - sub.loc[15, "pct_population_accessible"]
        if j2 > j1 * 1.5 and j2 > 5:
            cliff_flags.append(f"{cat}: 15->20min gain (+{j2:.1f}pp) notably exceeds 10->15min gain (+{j1:.1f}pp)")
    print(f"\n  threshold-cliff flags: {cliff_flags if cliff_flags else 'none -- accessibility grows smoothly, no cliff at 15min'}")

    sens_df.to_csv(VAL_DIR / "threshold_sensitivity.csv", index=False)
    print(f"  saved threshold_sensitivity.csv")

    output = {
        "bottleneck_summary": bottleneck_df.to_dict(orient="records"),
        "most_common_bottleneck_by_cells": most_common_by_cells.to_dict(),
        "most_common_bottleneck_by_population": most_common_by_pop.to_dict(),
        "threshold_sensitivity": sens_rows,
        "threshold_cliff_flags": cliff_flags,
        "20min_query_runtime_s": round(elapsed, 1),
    }
    (VAL_DIR / "bottleneck_and_threshold_full.json").write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
