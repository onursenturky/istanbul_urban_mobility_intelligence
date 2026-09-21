"""Phase 7B: citywide V2 master feature table.

Builds on the frozen V1 master table (urban_mobility_features_citywide.parquet,
READ-ONLY here, never modified) by:
  1. Copying every V1 column verbatim EXCEPT the two PENDING_DEPENDENCY status
     sentinels (road_grade_status, pct_road_network_with_cycle_infrastructure_status),
     which are dropped since Phase 7A resolved both dependencies.
  2. Left-joining the four Phase 7A output families (road network, land-use/
     green-space, road-grade, cycling-road overlap) by grid_id.

Because every shared (V1-origin) column is copied directly from V1's own
values rather than recomputed, existing-feature integrity holds by
construction; build_v2_impact_audit.py still verifies this explicitly
(never assume -- confirm).

Excluded by design (per Phase 7B instruction 6): typology cluster IDs, MCDA
scores, consensus classes, district rankings, or any other analytical
output -- this is a predictor table only, exactly like V1.

Outputs:
  data/processed/citywide/features/urban_mobility_features_citywide_v2.parquet
  data/processed/citywide/qa/master_feature_v2_qa.json
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

FEATURES_DIR = cfg.DATA_FEATURES
QA_DIR = cfg.DATA_PROCESSED / "qa"

N_EXPECTED_CELLS = 22322
N_EXPECTED_DISTRICTS = 39

V1_PATH = FEATURES_DIR / "urban_mobility_features_citywide.parquet"
STATUS_COLS_TO_DROP = ["road_grade_status", "pct_road_network_with_cycle_infrastructure_status"]

NEW_FAMILIES = {
    "road_network": {
        "path": FEATURES_DIR / "road_features_citywide.parquet",
        "cols": ["road_length_m", "major_road_length_m", "local_road_length_m", "walkable_road_length_m",
                 "cycle_accessible_road_length_m", "road_density_km_per_km2", "intersection_count",
                 "intersection_density_km2"],
    },
    "landuse_greenspace": {
        "path": FEATURES_DIR / "landuse_features_citywide_pbf.parquet",
        "cols": ["green_area_m2", "green_area_ratio", "residential_area_ratio", "commercial_area_ratio",
                 "retail_area_ratio", "industrial_area_ratio", "landuse_data_coverage_pct"],
    },
    "road_grade_resolved": {
        "path": FEATURES_DIR / "road_grade_features_citywide.parquet",
        "cols": ["mean_absolute_road_grade_pct", "median_absolute_road_grade_pct",
                 "pct_road_length_grade_gt_5pct", "pct_road_length_grade_gt_8pct", "road_grade_sample_length_m"],
    },
    "cycling_road_overlap_resolved": {
        "path": FEATURES_DIR / "cycling_road_overlap_citywide.parquet",
        "cols": ["pct_road_network_with_cycle_infrastructure"],
    },
}


def load_family(path) -> gpd.GeoDataFrame:
    return gpd.read_parquet(path)


def main() -> None:
    print("=" * 72)
    print("Phase 7B: citywide V2 master feature table")
    print("=" * 72)

    print(f"\n[1/4] Loading V1 master table (read-only): {V1_PATH}")
    v1 = gpd.read_parquet(V1_PATH)
    assert len(v1) == N_EXPECTED_CELLS
    assert v1["grid_id"].is_unique
    assert v1["district"].nunique() == N_EXPECTED_DISTRICTS
    n_v1_cols = len(v1.columns)
    n_v1_predictors = n_v1_cols - 5  # grid_id, district, cell_area_m2, land_area_m2, geometry
    print(f"  V1: {len(v1)} cells, {n_v1_cols} columns ({n_v1_predictors} predictors incl. 2 pending sentinels)")

    print(f"\n[2/4] Dropping resolved PENDING_DEPENDENCY sentinels: {STATUS_COLS_TO_DROP}")
    for col in STATUS_COLS_TO_DROP:
        assert col in v1.columns, f"expected status column {col} not found in V1"
        assert (v1[col] == "PENDING_ROAD_NETWORK").all(), f"{col}: not all cells were PENDING_ROAD_NETWORK in V1"
    v2 = v1.drop(columns=STATUS_COLS_TO_DROP).copy()

    print("\n[3/4] Joining Phase 7A families...")
    join_diagnostics = {}
    for name, spec in NEW_FAMILIES.items():
        print(f"  [join] {name}: {spec['path'].name}")
        fam = load_family(spec["path"])
        assert len(fam) == N_EXPECTED_CELLS, f"{name}: expected {N_EXPECTED_CELLS} rows, got {len(fam)}"
        assert fam["grid_id"].is_unique, f"{name}: grid_id not unique"
        missing_from_fam = set(v2["grid_id"]) - set(fam["grid_id"])
        assert not missing_from_fam, f"{name}: missing {len(missing_from_fam)} grid_ids present in V2 base"
        assert fam["district"].nunique() == N_EXPECTED_DISTRICTS, f"{name}: does not cover 39 districts"

        missing_cols = [c for c in spec["cols"] if c not in fam.columns]
        assert not missing_cols, f"{name}: expected columns not found: {missing_cols}"

        n_before = len(v2)
        v2 = v2.merge(fam[["grid_id"] + spec["cols"]], on="grid_id", how="left", validate="one_to_one")
        assert len(v2) == n_before, f"{name}: row count changed after join ({n_before} -> {len(v2)})"
        assert v2["grid_id"].is_unique

        n_null_after_join = {c: int(v2[c].isna().sum()) for c in spec["cols"]}
        join_diagnostics[name] = {"cols_added": spec["cols"], "n_null_after_join": n_null_after_join}
        print(f"    added {len(spec['cols'])} columns, nulls after join: {n_null_after_join}")

    n_new_predictors = sum(len(spec["cols"]) for spec in NEW_FAMILIES.values())
    n_v2_predictors = n_v1_predictors - 2 + n_new_predictors
    print(f"\n  V2: {len(v2)} cells, {len(v2.columns)} columns ({n_v2_predictors} predictors)")
    print(f"  predictor delta: {n_v1_predictors} (V1, incl. 2 pending) -> {n_v2_predictors} (V2) "
          f"[-2 resolved sentinels, +{n_new_predictors} new/resolved numeric]")

    print("\n[4/4] QA...")
    num_cols = v2.select_dtypes(include=[np.number]).columns
    inf_counts = {c: int(np.isinf(v2[c]).sum()) for c in num_cols if np.isinf(v2[c]).sum() > 0}
    assert not inf_counts, f"infinities found: {inf_counts}"
    assert len(v2) == N_EXPECTED_CELLS and v2["grid_id"].is_unique
    assert v2["district"].nunique() == N_EXPECTED_DISTRICTS

    qa = {
        "n_cells": len(v2),
        "n_districts": int(v2["district"].nunique()),
        "n_v1_total_columns": n_v1_cols,
        "n_v1_predictors_incl_pending": n_v1_predictors,
        "status_sentinels_dropped": STATUS_COLS_TO_DROP,
        "n_new_predictors_added": n_new_predictors,
        "n_v2_total_columns": len(v2.columns),
        "n_v2_predictors": n_v2_predictors,
        "join_diagnostics": join_diagnostics,
        "infinities_found": inf_counts,
        "excluded_by_design": ["typology cluster IDs", "MCDA scores", "consensus classes", "district rankings",
                                "final communication outputs"],
    }

    out_path = FEATURES_DIR / "urban_mobility_features_citywide_v2.parquet"
    v2.to_parquet(out_path)
    print(f"\n[save] {out_path}")

    qa_path = QA_DIR / "master_feature_v2_qa.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {qa_path}")

    print("\n--- SUMMARY ---")
    print(f"V1 predictors (incl. 2 pending): {n_v1_predictors}")
    print(f"V2 predictors: {n_v2_predictors}")
    print(f"Net new/resolved: +{n_new_predictors - 2}  (2 pending sentinels removed, {n_new_predictors} numeric added)")


if __name__ == "__main__":
    main()
