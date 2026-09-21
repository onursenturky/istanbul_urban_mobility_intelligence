"""Phase 11, Sections 1-3: the single grid-level synthesis table joining
ONLY already-frozen fields from Phase 8/8.1 (walking), Phase 9 (cycling),
Phase 10 (transit), the V2 typology, and the e-bike application. No
indicator is recomputed here -- this module performs joins and, where
explicitly noted, purely descriptive derived flags (e.g. an analysis-
universe membership boolean), never new routing or new accessibility math.
"""

from __future__ import annotations

import json

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

WALK_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city"
WALK_VAL_DIR = WALK_DIR / "validation"
CYC_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "cycling_accessibility"
TRANSIT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "first_last_mile_transit"
MCDA_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda_v2" / "phase6b"
OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "accessibility_gap_intelligence"

RELIABLE_FLAGS = {"RELIABLE", "RELIABLE_SEPARATE_COMPONENT"}


def main() -> None:
    print("=" * 72)
    print("Phase 11 Sections 1-3: grid-level synthesis table + analysis universes")
    print("=" * 72)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/3] Loading frozen inputs (read-only)...")
    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet",
                          columns=["grid_id", "district", "population_calibrated"])
    typology = pd.read_parquet(cfg.PROJECT_ROOT / "analysis" / "clustering_v2_eight_family" / "cluster_assignments_v2ef.parquet",
                                columns=["grid_id", "cluster"])
    walk_quality = pd.read_parquet(WALK_VAL_DIR / "corrected_accessibility_quality_flags.parquet",
                                    columns=["grid_id", "walking_snap_quality", "component_class", "corrected_quality_flag"]
                                    ).rename(columns={"component_class": "walking_component_class",
                                                       "corrected_quality_flag": "walking_quality_flag"})
    cyc_quality = pd.read_parquet(CYC_DIR / "cycling_accessibility_quality_flags.parquet",
                                   columns=["grid_id", "cycling_snap_quality", "component_class", "corrected_quality_flag"]
                                   ).rename(columns={"component_class": "cycling_component_class",
                                                      "corrected_quality_flag": "cycling_quality_flag"})

    walk_nearest = pd.read_parquet(WALK_DIR / "grid_nearest_service_times.parquet",
                                    columns=["grid_id", "A_food_groceries_nearest_time_min",
                                             "B_healthcare_nearest_time_min", "C_education_nearest_time_min"]
                                    ).rename(columns={"A_food_groceries_nearest_time_min": "walk_food_nearest_min",
                                                       "B_healthcare_nearest_time_min": "walk_healthcare_nearest_min",
                                                       "C_education_nearest_time_min": "walk_education_nearest_min"})
    walk_prox = pd.read_parquet(WALK_DIR / "grid_proximity_summary.parquet",
                                 columns=["grid_id", "categories_accessible_15min", "required_categories_accessible_15min",
                                          "COMPLETE_15MIN_ACCESS"]
                                 ).rename(columns={"categories_accessible_15min": "walk_categories_accessible_15min",
                                                    "required_categories_accessible_15min": "walk_required_categories_accessible_15min",
                                                    "COMPLETE_15MIN_ACCESS": "WALKING_COMPLETE_15MIN_ACCESS"})
    walk_deficit = pd.read_parquet(WALK_DIR / "accessibility_deficit_classes.parquet",
                                    columns=["grid_id", "food_missing", "healthcare_missing", "education_missing", "deficit_class"])

    cyc_nearest = pd.read_parquet(CYC_DIR / "cycling_nearest_service_times.parquet",
                                   columns=["grid_id", "A_food_groceries_nearest_time_min",
                                            "B_healthcare_nearest_time_min", "C_education_nearest_time_min"]
                                   ).rename(columns={"A_food_groceries_nearest_time_min": "cycle_food_nearest_min",
                                                      "B_healthcare_nearest_time_min": "cycle_healthcare_nearest_min",
                                                      "C_education_nearest_time_min": "cycle_education_nearest_min"})
    wc_comp = pd.read_parquet(CYC_DIR / "walking_cycling_complete_access_comparison.parquet",
                               columns=["grid_id", "cycling_categories_accessible_15min",
                                        "cycling_required_categories_accessible_15min", "CYCLING_COMPLETE_15MIN_ACCESS", "access_class"]
                               ).rename(columns={"access_class": "everyday_needs_mode_access_class"})
    wc_comp["CYCLE_ONLY_GAIN"] = wc_comp["everyday_needs_mode_access_class"] == "CYCLE_ONLY_GAIN"

    walk_gen = pd.read_parquet(TRANSIT_DIR / "walking_general_transit_accessibility.parquet",
                                columns=["grid_id", "nearest_time_min"]).rename(columns={"nearest_time_min": "walk_general_transit_nearest_min"})
    cyc_gen = pd.read_parquet(TRANSIT_DIR / "cycling_general_transit_accessibility.parquet",
                               columns=["grid_id", "nearest_time_min"]).rename(columns={"nearest_time_min": "cycle_general_transit_nearest_min"})
    walk_fixed = pd.read_parquet(TRANSIT_DIR / "walking_fixed_transit_accessibility.parquet",
                                  columns=["grid_id", "nearest_time_min"]).rename(columns={"nearest_time_min": "walk_fixed_transit_nearest_min"})
    cyc_fixed = pd.read_parquet(TRANSIT_DIR / "cycling_fixed_transit_accessibility.parquet",
                                 columns=["grid_id", "nearest_time_min"]).rename(columns={"nearest_time_min": "cycle_fixed_transit_nearest_min"})
    gen_comp = pd.read_parquet(TRANSIT_DIR / "general_transit_mode_comparison.parquet",
                                columns=["grid_id", "access_class_10min"]).rename(columns={"access_class_10min": "general_transit_mode_access_class_10min"})
    gen_comp["CYCLE_ONLY_TRANSIT_GAIN"] = gen_comp["general_transit_mode_access_class_10min"] == "CYCLE_ONLY_TRANSIT_GAIN"
    transit_gap = pd.read_parquet(TRANSIT_DIR / "transit_gap_diagnostics.parquet",
                                   columns=["grid_id", "gap_class", "transit_data_quality_class", "quality_uncertainty_flag"]
                                   ).rename(columns={"gap_class": "transit_gap_class", "quality_uncertainty_flag": "transit_quality_uncertainty_flag"})

    ebike_opp = pd.read_parquet(MCDA_DIR / "ebike_opportunity_baseline.parquet", columns=["grid_id", "ebike_opportunity"])
    ebike_read = pd.read_parquet(MCDA_DIR / "ebike_readiness_baseline.parquet", columns=["grid_id", "ebike_readiness"])
    ebike_consensus = pd.read_parquet(MCDA_DIR / "consensus_classes.parquet",
                                       columns=["grid_id", "readiness_consensus_class", "opportunity_consensus_class"])

    print("\n[2/3] Joining into one grid-level synthesis table (left joins from the full V2 grid, 22,322 cells)...")
    df = v2.merge(typology, on="grid_id", how="left") \
           .merge(walk_quality, on="grid_id", how="left") \
           .merge(cyc_quality, on="grid_id", how="left") \
           .merge(walk_nearest, on="grid_id", how="left") \
           .merge(walk_prox, on="grid_id", how="left") \
           .merge(walk_deficit[["grid_id", "food_missing", "healthcare_missing", "education_missing", "deficit_class"]], on="grid_id", how="left") \
           .merge(cyc_nearest, on="grid_id", how="left") \
           .merge(wc_comp[["grid_id", "cycling_categories_accessible_15min", "cycling_required_categories_accessible_15min",
                           "CYCLING_COMPLETE_15MIN_ACCESS", "CYCLE_ONLY_GAIN"]], on="grid_id", how="left") \
           .merge(walk_gen, on="grid_id", how="left") \
           .merge(cyc_gen, on="grid_id", how="left") \
           .merge(walk_fixed, on="grid_id", how="left") \
           .merge(cyc_fixed, on="grid_id", how="left") \
           .merge(gen_comp[["grid_id", "CYCLE_ONLY_TRANSIT_GAIN"]], on="grid_id", how="left") \
           .merge(transit_gap, on="grid_id", how="left") \
           .merge(ebike_opp, on="grid_id", how="left") \
           .merge(ebike_read, on="grid_id", how="left") \
           .merge(ebike_consensus, on="grid_id", how="left")
    assert len(df) == 22322, f"expected 22322 grid cells, got {len(df)}"
    assert df["grid_id"].is_unique, "grid_id must be unique in the synthesis table"
    print(f"  synthesis table: {len(df)} rows, {len(df.columns)} columns")

    print("\n[3/3] Defining analysis universes (uncertainty kept distinct from deficit -- no NaN->0 conversion)...")
    df["everyday_access_reliable"] = df["walking_quality_flag"].isin(RELIABLE_FLAGS) & df["cycling_quality_flag"].isin(RELIABLE_FLAGS)
    df["transit_access_reliable"] = df["transit_quality_uncertainty_flag"] == "RELIABLE"
    df["strict_synthesis_reliable"] = df["everyday_access_reliable"] & df["transit_access_reliable"]

    total_pop = float(df["population_calibrated"].sum())
    universe_coverage = {}
    for label, mask in [("RAW_UNIVERSE", pd.Series(True, index=df.index)),
                         ("EVERYDAY_ACCESS_RELIABLE", df["everyday_access_reliable"]),
                         ("TRANSIT_ACCESS_RELIABLE", df["transit_access_reliable"]),
                         ("STRICT_SYNTHESIS_RELIABLE", df["strict_synthesis_reliable"])]:
        n_cells = int(mask.sum())
        pop = float(df.loc[mask, "population_calibrated"].sum())
        universe_coverage[label] = {
            "n_cells": n_cells, "pct_cells": round(n_cells / len(df) * 100, 2),
            "population": round(pop, 1), "pct_population": round(pop / total_pop * 100, 2),
        }
        print(f"  {label}: {n_cells}/{len(df)} cells ({universe_coverage[label]['pct_cells']}%), "
              f"population {pop:,.0f} ({universe_coverage[label]['pct_population']}%)")

    df.to_parquet(OUT_DIR / "accessibility_gap_grid_synthesis.parquet")
    print(f"\n[save] {OUT_DIR / 'accessibility_gap_grid_synthesis.parquet'}")

    coverage_out = {
        "total_calibrated_population_2020": round(total_pop, 1),
        "definitions": {
            "RAW_UNIVERSE": "All 22,322 grid cells.",
            "EVERYDAY_ACCESS_RELIABLE": "Cells where BOTH walking and cycling network quality flags permit "
                "interpretation (RELIABLE or RELIABLE_SEPARATE_COMPONENT, per Phase 8.1/Phase 9's own corrected "
                "classification) -- excludes QUESTIONABLE_ANCHOR, SMALL_COMPONENT_CAUTION, KNOWN_NETWORK_LIMITATION_ADALAR.",
            "TRANSIT_ACCESS_RELIABLE": "Cells flagged RELIABLE by Phase 10's own quality_uncertainty_flag, which "
                "already combines network-quality AND transit-feed/data-coverage adequacy.",
            "STRICT_SYNTHESIS_RELIABLE": "Intersection of EVERYDAY_ACCESS_RELIABLE and TRANSIT_ACCESS_RELIABLE -- "
                "the universe used for any claim spanning both domains at once.",
        },
        "coverage": universe_coverage,
        "uncertainty_handling": "NaN nearest-service times and non-RELIABLE quality flags are preserved as-is "
            "throughout this synthesis -- never converted to zero accessibility or a large finite placeholder.",
    }
    (OUT_DIR / "analysis_universe_coverage.json").write_text(json.dumps(coverage_out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {OUT_DIR / 'analysis_universe_coverage.json'}")


if __name__ == "__main__":
    main()
