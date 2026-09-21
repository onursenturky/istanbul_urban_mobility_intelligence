"""Phase 8, step 4: sanity checks, post-hoc V2 typology summary, citywide
descriptive results, manifest, and summary.
"""

from __future__ import annotations

import hashlib
import json

import geopandas as gpd
import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

APP_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city"
CATEGORIES = ["A_food_groceries", "B_healthcare", "C_education", "D_daily_services",
              "E_retail_shopping", "F_leisure_social", "G_green_recreation", "H_public_transport_access"]
REQUIRED = ["A_food_groceries", "B_healthcare", "C_education"]

SANITY_TEST_POINTS = [
    {"label": "dense_historic_core", "grid_id": "GRID_13704", "district": "Fatih"},
    {"label": "dense_asian_side_core", "grid_id": "GRID_14127", "district": "Üsküdar"},
    {"label": "transit_rich_residential", "grid_id": "GRID_14368", "district": "Üsküdar"},
    {"label": "mixed_use_urban", "grid_id": "GRID_09343", "district": "Arnavutköy"},
    {"label": "peripheral_settlement", "grid_id": "GRID_00001", "district": "Silivri"},
    {"label": "rural_peripheral", "grid_id": "GRID_19932", "district": "Pendik"},
]


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    print("=" * 72)
    print("Phase 8 step 4: sanity checks, typology post-hoc, citywide summary, manifest")
    print("=" * 72)

    acc15 = pd.read_parquet(APP_DIR / "grid_accessibility_15min.parquet")
    acc10 = pd.read_parquet(APP_DIR / "grid_accessibility_10min.parquet")
    acc5 = pd.read_parquet(APP_DIR / "grid_accessibility_5min.parquet")
    nearest = pd.read_parquet(APP_DIR / "grid_nearest_service_times.parquet")
    proximity = pd.read_parquet(APP_DIR / "grid_proximity_summary.parquet")
    deficits = pd.read_parquet(APP_DIR / "accessibility_deficit_classes.parquet")
    quality = pd.read_parquet(APP_DIR / "accessibility_quality_flags.parquet")
    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet",
                          columns=["grid_id", "population_calibrated"])

    print("\n[1/5] Sanity checks on representative + edge cells...")
    merged = proximity.merge(quality[["grid_id", "interpretation_status"]], on="grid_id") \
        .merge(v2, on="grid_id").merge(deficits[["grid_id", "deficit_class"]], on="grid_id")

    # add two more diagnostic cases: highest-population deficit cell, and a known network-problem (Adalar) cell
    high_pop_deficit = merged[~merged["COMPLETE_15MIN_ACCESS"]].sort_values("population_calibrated", ascending=False).iloc[0]
    adalar_cell = merged[merged["district"] == "Adalar"].iloc[0]

    cases = list(SANITY_TEST_POINTS)
    cases.append({"label": "high_population_accessibility_deficit", "grid_id": high_pop_deficit["grid_id"], "district": high_pop_deficit["district"]})
    cases.append({"label": "known_network_problem_area_adalar", "grid_id": adalar_cell["grid_id"], "district": adalar_cell["district"]})

    sanity_results = []
    for case in cases:
        gid = case["grid_id"]
        row15 = acc15[acc15["grid_id"] == gid]
        row10 = acc10[acc10["grid_id"] == gid]
        row5 = acc5[acc5["grid_id"] == gid]
        rown = nearest[nearest["grid_id"] == gid]
        rowq = quality[quality["grid_id"] == gid]
        if len(row15) == 0:
            sanity_results.append({**case, "status": "GRID_ID_NOT_FOUND"})
            continue
        result = {**case}
        for t_min, r in [(5, row5), (10, row10), (15, row15)]:
            result[f"categories_accessible_{t_min}min"] = int(sum(r[f"{c}_access_{t_min}min"].iloc[0] for c in CATEGORIES))
            for c in CATEGORIES:
                result[f"{c}_count_{t_min}min"] = int(r[f"{c}_count_{t_min}min"].iloc[0])
        for c in CATEGORIES:
            nt = rown[f"{c}_nearest_time_min"].iloc[0]
            result[f"{c}_nearest_time_min"] = None if pd.isna(nt) else round(float(nt), 2)
        result["network_anchor_quality"] = rowq["walking_snap_quality"].iloc[0] if len(rowq) else None
        result["interpretation_status"] = rowq["interpretation_status"].iloc[0] if len(rowq) else None
        sanity_results.append(result)
        print(f"  [{case['label']}] ({gid}, {case['district']}): categories@15min="
              f"{result['categories_accessible_15min']}/8, status={result['interpretation_status']}")

    (APP_DIR / "sanity_check_cases.json").write_text(json.dumps(sanity_results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  saved sanity_check_cases.json")

    print("\n[2/5] Cross-check: deficit vs network-quality status (is incompleteness a real gap or a network artifact?)...")
    cross = pd.crosstab(merged["deficit_class"], merged["interpretation_status"])
    print(cross.to_string())
    reliable_multi_deficit = int(((merged["deficit_class"] == "MULTI_SERVICE_DEFICIT") & (merged["interpretation_status"] == "RELIABLE")).sum())
    isolated_multi_deficit = int(((merged["deficit_class"] == "MULTI_SERVICE_DEFICIT") & (merged["interpretation_status"] == "ISOLATED_NETWORK_COMPONENT")).sum())
    print(f"  MULTI_SERVICE_DEFICIT cells that are network-RELIABLE (genuine gap): {reliable_multi_deficit}")
    print(f"  MULTI_SERVICE_DEFICIT cells in an isolated network component (quality caveat applies): {isolated_multi_deficit}")

    print("\n[3/5] Typology post-hoc summary (V2 k=5, interpretation only)...")
    typology = pd.read_parquet(cfg.PROJECT_ROOT / "analysis" / "clustering_v2_eight_family" / "cluster_assignments_v2ef.parquet",
                                columns=["grid_id", "cluster"])
    tmerged = merged.merge(typology, on="grid_id")
    by_cluster = tmerged.groupby("cluster").agg(
        n_cells=("grid_id", "size"),
        pct_complete_15min=("COMPLETE_15MIN_ACCESS", "mean"),
        mean_categories_accessible_15min=("categories_accessible_15min", "mean"),
        pop_total=("population_calibrated", "sum"),
    )
    by_cluster["pct_complete_15min"] = (by_cluster["pct_complete_15min"] * 100).round(2)
    by_cluster["mean_categories_accessible_15min"] = by_cluster["mean_categories_accessible_15min"].round(2)
    deficit_by_cluster = pd.crosstab(tmerged["cluster"], tmerged["deficit_class"], normalize="index").round(3) * 100
    print(by_cluster.to_string())
    print("\n  deficit class share (%) by cluster:")
    print(deficit_by_cluster.to_string())

    typo_summary = pd.concat([by_cluster, deficit_by_cluster.add_suffix("_pct")], axis=1).reset_index()
    typo_summary.to_csv(APP_DIR / "typology_accessibility_summary.csv", index=False)
    print(f"  saved typology_accessibility_summary.csv")

    print("\n[4/5] Citywide descriptive results (district summaries, factual, no ranking)...")
    by_district = merged.groupby("district").agg(
        n_cells=("grid_id", "size"), pct_complete_15min=("COMPLETE_15MIN_ACCESS", "mean"),
        pop_total=("population_calibrated", "sum"),
    )
    by_district["pct_complete_15min"] = (by_district["pct_complete_15min"] * 100).round(2)

    pop_summary = json.loads((APP_DIR / "population_accessibility_summary.json").read_text(encoding="utf-8"))
    missing_service_counts = deficits["deficit_class"].value_counts().to_dict()
    most_common_missing = {
        "food": int(deficits["food_missing"].sum()), "healthcare": int(deficits["healthcare_missing"].sum()),
        "education": int(deficits["education_missing"].sum()),
    }

    citywide_results = {
        "n_valid_grid_cells": len(merged),
        "n_cells_complete_15min_access": int(merged["COMPLETE_15MIN_ACCESS"].sum()),
        "pct_cells_complete_15min_access": round(float(merged["COMPLETE_15MIN_ACCESS"].mean() * 100), 2),
        "population_summary": pop_summary,
        "category_accessibility_15min_pct_cells": {c: round(float(acc15[f"{c}_access_15min"].mean() * 100), 2) for c in CATEGORIES},
        "most_common_missing_required_category_counts": most_common_missing,
        "deficit_class_counts": missing_service_counts,
        "n_multi_service_deficit_cells": int(missing_service_counts.get("MULTI_SERVICE_DEFICIT", 0)),
        "n_multi_service_deficit_cells_network_reliable": reliable_multi_deficit,
        "n_multi_service_deficit_cells_isolated_component_caveat": isolated_multi_deficit,
        "population_exposed_to_multi_service_deficit": round(float(merged.loc[merged["deficit_class"] == "MULTI_SERVICE_DEFICIT", "population_calibrated"].sum()), 1),
        "quality_flagged_cells": quality["interpretation_status"].value_counts().to_dict(),
        "district_descriptive_summary_NOT_A_RANKING": by_district.round(2).to_dict(orient="index"),
    }
    (APP_DIR / "15min_city_summary_data.json").write_text(json.dumps(citywide_results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  {citywide_results['n_cells_complete_15min_access']}/{citywide_results['n_valid_grid_cells']} cells "
          f"({citywide_results['pct_cells_complete_15min_access']}%) complete 15-min access")

    print("\n[5/5] Manifest...")
    input_files = {
        "walking_graph": cfg.PROJECT_ROOT / "data" / "processed" / "network" / "walking_graph.pkl",
        "grid_network_anchors": cfg.PROJECT_ROOT / "analysis" / "network_intelligence" / "grid_network_anchors.parquet",
        "v2_master_feature_table": cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet",
        "v2_typology_assignments": cfg.PROJECT_ROOT / "analysis" / "clustering_v2_eight_family" / "cluster_assignments_v2ef.parquet",
        "poi_network_anchors": APP_DIR / "poi_network_anchors.parquet",
    }
    manifest = {
        "version": "15MIN_ISTANBUL_NETWORK_PROXIMITY_V1",
        "methodological_language_used": ["network-based urban proximity", "walking accessibility", "access to everyday needs"],
        "methodological_language_avoided": ["true 15-minute city", "validated quality of life", "causal effect", "behavioral accessibility", "actual walking behavior"],
        "input_hashes": {name: {"path": str(p.relative_to(cfg.PROJECT_ROOT)), "sha256": sha256_of(p)} for name, p in input_files.items() if p.exists()},
        "everyday_needs_taxonomy": {"required": REQUIRED, "optional_contextual": [c for c in CATEGORIES if c not in REQUIRED]},
        "complete_15min_access_definition": "reach >=1 destination in EVERY required category (Food/Groceries, "
                                            "Healthcare, Education) within a 15-minute walk on the mapped pedestrian network",
        "coverage_ratio_definition": "required_categories_accessible / n_required_categories (0-1) -- a "
                                     "transparent DESCRIPTIVE coverage ratio, explicitly NOT an empirically "
                                     "validated score or weighted index",
        "population_layer": "Calibrated 2020 population (WorldPop-based, Phase 3C) -- results describe "
                            "accessibility of the 2020 population's spatial distribution to the CURRENT "
                            "(2026) network/destination snapshot, not a 2026 population estimate",
        "known_quality_limitations": {
            "adalar": "Explicit known network-coverage limitation (Phase 7) -- low accessibility there must NOT "
                      "be interpreted as genuine urban accessibility failure until network representation is resolved.",
            "isolated_network_components": f"{quality['interpretation_status'].eq('ISOLATED_NETWORK_COMPONENT').sum()} "
                "cells anchor to a walking-network fragment disconnected from the largest component (genuine "
                "Bosphorus/water fragmentation, confirmed in Phase 7) -- their accessibility results reflect "
                "local-fragment-only reachability, flagged in accessibility_quality_flags.parquet.",
            "green_recreation_category": "POI-sourced only (not land-use polygons) -- likely undercounts true "
                "green-space access; interpret G_green_recreation results as a lower bound.",
            "daily_services_category": "A new grouping not part of any frozen MCDA category; moderate reliability.",
        },
        "output_paths": [str(p.relative_to(cfg.PROJECT_ROOT)) for p in sorted(APP_DIR.glob("*"))],
        "stop_condition": "Descriptive network-based 15-minute accessibility analysis only -- no weighted MCDA, "
                          "cycling accessibility, transit-inclusive accessibility, predictive ML, equity "
                          "modeling, dashboard, or final visualization styling were performed.",
    }
    (APP_DIR / "15min_city_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    summary = {
        "n_valid_grid_cells": citywide_results["n_valid_grid_cells"],
        "pct_cells_complete_15min_access": citywide_results["pct_cells_complete_15min_access"],
        "pct_population_complete_15min_access": pop_summary["pct_population_with_complete_15min_access"],
        "n_multi_service_deficit_cells": citywide_results["n_multi_service_deficit_cells"],
        "most_common_missing_required_category": max(most_common_missing, key=most_common_missing.get),
        "n_cells_quality_flagged_non_reliable": len(merged) - int((quality["interpretation_status"] == "RELIABLE").sum()),
    }
    (APP_DIR / "15min_city_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[save] {APP_DIR / '15min_city_manifest.json'}")
    print(f"[save] {APP_DIR / '15min_city_summary.json'}")


if __name__ == "__main__":
    main()
