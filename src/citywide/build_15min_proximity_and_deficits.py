"""Phase 8, step 3: core proximity measures, REQUIRED/OPTIONAL category
split, COMPLETE_15MIN_ACCESS, population-weighted accessibility, deficit
diagnostics, and quality-aware interpretation flags.

REQUIRED vs OPTIONAL classification (conceptual necessity AND source
reliability -- neither alone):
  REQUIRED:  A_food_groceries, B_healthcare, C_education
             (all three: GOOD source reliability, and represent
             conventional universal everyday necessities in accessibility
             frameworks -- not forced merely to inflate the metric)
  OPTIONAL / CONTEXTUAL: D_daily_services (new/moderate-reliability
             grouping), E_retail_shopping (discretionary), F_leisure_social
             (discretionary), G_green_recreation (LIMITED reliability --
             POI-only undercounts true green access, explicitly not
             forced into REQUIRED), H_public_transport_access (an enabler
             of other trips more than an everyday-need destination itself)

COMPLETE_15MIN_ACCESS = True only if a cell reaches >=1 destination in
EVERY required category within 15 minutes.

The population layer is CALIBRATED 2020 population (WorldPop-based,
calibrated in Phase 3C) -- results below describe the accessibility of the
SPATIAL DISTRIBUTION of the calibrated 2020 population to the CURRENT
(2026 snapshot) network/destination data, not a 2026 population estimate.
"""

from __future__ import annotations

import json

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.network import network_builder
from src.utils import config as cfg

APP_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city"
CATEGORIES = ["A_food_groceries", "B_healthcare", "C_education", "D_daily_services",
              "E_retail_shopping", "F_leisure_social", "G_green_recreation", "H_public_transport_access"]
REQUIRED = ["A_food_groceries", "B_healthcare", "C_education"]
OPTIONAL = [c for c in CATEGORIES if c not in REQUIRED]


def build_proximity_summary(acc5, acc10, acc15) -> pd.DataFrame:
    base = acc15[["grid_id", "district"]].copy()
    for t_min, df in [(5, acc5), (10, acc10), (15, acc15)]:
        access_cols = [f"{c}_access_{t_min}min" for c in CATEGORIES]
        base[f"categories_accessible_{t_min}min"] = df[access_cols].sum(axis=1).to_numpy()
        req_cols = [f"{c}_access_{t_min}min" for c in REQUIRED]
        base[f"required_categories_accessible_{t_min}min"] = df[req_cols].sum(axis=1).to_numpy()
        base[f"COMPLETE_{t_min}MIN_ACCESS"] = (df[req_cols].sum(axis=1) == len(REQUIRED)).to_numpy()
        base[f"required_coverage_ratio_{t_min}min"] = (base[f"required_categories_accessible_{t_min}min"] / len(REQUIRED)).round(4)
    return base


def build_deficit_classes(acc15: pd.DataFrame, nearest: pd.DataFrame) -> pd.DataFrame:
    df = acc15[["grid_id", "district"]].copy()
    missing_flags = {}
    for c in REQUIRED:
        missing_flags[c] = ~acc15[f"{c}_access_15min"].to_numpy()
    n_missing = np.sum(list(missing_flags.values()), axis=0)
    df["n_required_categories_missing_15min"] = n_missing
    df["food_missing"] = missing_flags["A_food_groceries"]
    df["healthcare_missing"] = missing_flags["B_healthcare"]
    df["education_missing"] = missing_flags["C_education"]

    def classify(row):
        n = row["n_required_categories_missing_15min"]
        if n == 0:
            return "NONE_COMPLETE_ACCESS"
        if n >= 2:
            return "MULTI_SERVICE_DEFICIT"
        if row["food_missing"]:
            return "FOOD_DEFICIT"
        if row["healthcare_missing"]:
            return "HEALTHCARE_DEFICIT"
        if row["education_missing"]:
            return "EDUCATION_DEFICIT"
        return "UNKNOWN"

    df["deficit_class"] = df.apply(classify, axis=1)
    for c in REQUIRED:
        df[f"{c}_nearest_time_min"] = nearest[f"{c}_nearest_time_min"].to_numpy()
    return df


def build_quality_flags(anchors: pd.DataFrame, G_walk) -> pd.DataFrame:
    comps = list(nx.connected_components(G_walk))
    comps_sorted = sorted(comps, key=len, reverse=True)
    largest = comps_sorted[0]
    node_to_in_largest = {n: True for n in largest}

    df = anchors[["grid_id", "district", "walking_anchor_node", "walking_snap_quality", "walking_has_local_node"]].copy()
    df["in_largest_walking_component"] = df["walking_anchor_node"].map(lambda n: node_to_in_largest.get(n, False))
    df["is_adalar"] = df["district"] == "Adalar"

    def interp_status(row):
        if row["is_adalar"]:
            return "KNOWN_NETWORK_LIMITATION_ADALAR"
        if row["walking_snap_quality"] == "QUESTIONABLE":
            return "QUESTIONABLE_ANCHOR"
        if not row["in_largest_walking_component"]:
            return "ISOLATED_NETWORK_COMPONENT"
        return "RELIABLE"

    df["interpretation_status"] = df.apply(interp_status, axis=1)
    return df[["grid_id", "district", "walking_snap_quality", "walking_has_local_node",
               "in_largest_walking_component", "is_adalar", "interpretation_status"]]


def main() -> None:
    print("=" * 72)
    print("Phase 8 step 3: proximity measures, population accessibility, deficits, quality flags")
    print("=" * 72)

    acc5 = pd.read_parquet(APP_DIR / "grid_accessibility_5min.parquet")
    acc10 = pd.read_parquet(APP_DIR / "grid_accessibility_10min.parquet")
    acc15 = pd.read_parquet(APP_DIR / "grid_accessibility_15min.parquet")
    nearest = pd.read_parquet(APP_DIR / "grid_nearest_service_times.parquet")
    anchors = pd.read_parquet(cfg.PROJECT_ROOT / "analysis" / "network_intelligence" / "grid_network_anchors.parquet")
    grid_districts = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")[["grid_id", "district"]]
    anchors = anchors.merge(grid_districts, on="grid_id", how="left")

    print("\n[1/5] Core proximity summary...")
    proximity = build_proximity_summary(acc5, acc10, acc15)
    proximity.to_parquet(APP_DIR / "grid_proximity_summary.parquet")
    n_complete_15 = int(proximity["COMPLETE_15MIN_ACCESS"].sum())
    print(f"  COMPLETE_15MIN_ACCESS: {n_complete_15}/{len(proximity)} cells ({n_complete_15/len(proximity)*100:.2f}%)")
    print(f"  saved grid_proximity_summary.parquet")

    print("\n[2/5] Deficit diagnostics...")
    deficits = build_deficit_classes(acc15, nearest)
    deficits.to_parquet(APP_DIR / "accessibility_deficit_classes.parquet")
    print(deficits["deficit_class"].value_counts().to_string())
    print(f"  saved accessibility_deficit_classes.parquet")

    print("\n[3/5] Quality/network-coverage flags...")
    G_walk = network_builder.load_graph("walking_graph")
    quality = build_quality_flags(anchors, G_walk)
    quality.to_parquet(APP_DIR / "accessibility_quality_flags.parquet")
    print(quality["interpretation_status"].value_counts().to_string())
    print(f"  saved accessibility_quality_flags.parquet")

    print("\n[4/5] Population-weighted accessibility (CALIBRATED 2020 population)...")
    v2 = pd.read_parquet(cfg.DATA_PROCESSED / "features" / "urban_mobility_features_citywide_v2.parquet",
                          columns=["grid_id", "population_calibrated"])
    pop = proximity.merge(v2, on="grid_id").merge(deficits[["grid_id", "deficit_class"]], on="grid_id")
    total_pop = float(pop["population_calibrated"].sum())

    pop_complete_15 = float(pop.loc[pop["COMPLETE_15MIN_ACCESS"], "population_calibrated"].sum())
    pop_by_category_threshold = {}
    for t_min, df in [(5, acc5), (10, acc10), (15, acc15)]:
        df_pop = df.merge(v2, on="grid_id")
        for c in CATEGORIES:
            key = f"{c}_{t_min}min"
            pop_by_category_threshold[key] = round(float(df_pop.loc[df_pop[f"{c}_access_{t_min}min"], "population_calibrated"].sum()), 1)

    pop_by_n_categories = pop.groupby("required_categories_accessible_15min" if "required_categories_accessible_15min" in pop.columns else "categories_accessible_15min")["population_calibrated"].sum().round(1).to_dict()
    pop_by_deficit = pop.groupby("deficit_class")["population_calibrated"].sum().round(1).to_dict()

    population_summary = {
        "population_layer_caveat": "Population is CALIBRATED 2020 population (WorldPop-based, Phase 3C "
            "calibration). All figures below describe accessibility of the SPATIAL DISTRIBUTION of the "
            "calibrated 2020 population to the CURRENT (2026) network/destination snapshot -- NOT a 2026 "
            "population estimate.",
        "total_calibrated_population_2020": round(total_pop, 1),
        "population_with_complete_15min_access": round(pop_complete_15, 1),
        "pct_population_with_complete_15min_access": round(pop_complete_15 / total_pop * 100, 2),
        "population_lacking_complete_15min_access": round(total_pop - pop_complete_15, 1),
        "population_by_category_and_threshold": pop_by_category_threshold,
        "population_by_n_required_categories_accessible_15min": {str(k): v for k, v in pop_by_n_categories.items()},
        "population_by_deficit_class": pop_by_deficit,
    }
    (APP_DIR / "population_accessibility_summary.json").write_text(json.dumps(population_summary, indent=2, default=str), encoding="utf-8")
    print(f"  population with complete 15-min access: {pop_complete_15:,.0f} / {total_pop:,.0f} "
          f"({population_summary['pct_population_with_complete_15min_access']}%)")
    print(f"  saved population_accessibility_summary.json")

    print("\n[5/5] Category accessibility summary (all cells, descriptive)...")
    cat_summary_rows = []
    for t_min, df in [(5, acc5), (10, acc10), (15, acc15)]:
        for c in CATEGORIES:
            access_col = f"{c}_access_{t_min}min"
            cat_summary_rows.append({
                "category": c, "threshold_min": t_min,
                "n_cells_with_access": int(df[access_col].sum()),
                "pct_cells_with_access": round(float(df[access_col].mean() * 100), 2),
                "required": c in REQUIRED,
            })
    cat_summary = pd.DataFrame(cat_summary_rows)
    cat_summary.to_csv(APP_DIR / "category_accessibility_summary.csv", index=False)
    print(cat_summary[cat_summary["threshold_min"] == 15].to_string(index=False))
    print(f"  saved category_accessibility_summary.csv")


if __name__ == "__main__":
    main()
