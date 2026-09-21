"""Citywide population features (Section 4, family 1 of 4 not requiring
new Overpass requests).

Reuses the pilot's mass-preserving areal-weighting allocation
(src.features.population_features.allocate_population_to_grid) and
district-constrained calibration (src.features.population_calibration)
UNCHANGED -- same WorldPop constrained 2020 raster (already downloaded
country-wide, so covers Istanbul citywide with no new fetch), same
pixel x grid (x district, for calibration) overlay method, same formulas.

Only the grid/study-area/district inputs are citywide (39 districts,
22,322 cells) instead of the 3-district pilot.

Calibration data availability: unlike the pilot phase (which only had
official 2020 TÜİK/ADNKS totals for 3 districts), the same source already
used for the pilot -- İBB's "Nüfus Bilgileri" open dataset
(data/raw/population/ibb_nufus_bilgileri_tuik_sourced.xlsx), itself sourced
from TÜİK ADNKS -- covers ALL 39 Istanbul districts back to 2007. This is
used directly for full citywide calibration; no per-district factor is
invented or extrapolated from the pilot's 3 districts. One district-name
normalization is required: the spreadsheet spells the district "Kağıthane"
(no circumflex) where this project's OSM-derived boundary layer spells it
"Kâğıthane" (with circumflex) -- confirmed to be the same district (same
ilce_kodu / position in the 39-district list), so this is a spelling
alias, not a data substitution.

Raw WorldPop population/density are preserved as separate columns from the
calibrated ones, exactly as in the pilot (population_worldpop_raw /
population_density_worldpop_raw_km2 vs population_calibrated /
population_density_calibrated_km2).

Outputs:
  data/processed/citywide/features/population_features_citywide.parquet
  data/processed/citywide/qa/population_qa_citywide.json
  data/processed/citywide/qa/coverage_gate_population.json
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.coverage_gate import coverage_report, print_report
from src.data.fetch_population_data import fetch_worldpop_raster
from src.features import population_source_config as pcfg
from src.features.population_calibration import calibrate_population_to_grid, compute_calibration_factors
from src.features.population_features import allocate_population_to_grid
from src.utils import config as cfg

# Same source spreadsheet the pilot used, now read for all 39 districts
# rather than just the 3 pilot ones. Same year (2020, matching the WorldPop
# raster's reference year) and same provenance (TÜİK ADNKS via İBB open data).
IBB_POPULATION_XLSX = cfg.DATA_RAW / "population" / "ibb_nufus_bilgileri_tuik_sourced.xlsx"
DISTRICT_NAME_ALIASES = {"Kağıthane": "Kâğıthane"}  # spreadsheet spelling -> grid/OSM spelling


def load_citywide_official_population_2020() -> dict:
    df = pd.read_excel(IBB_POPULATION_XLSX)
    d2020 = df[df["Yıl"] == 2020].copy()
    value_cols = [c for c in df.columns if c not in ("Yıl", "İlçe", "ilce_kodu")]
    d2020["total_pop"] = d2020[value_cols].sum(axis=1)
    d2020["İlçe"] = d2020["İlçe"].replace(DISTRICT_NAME_ALIASES)
    official = dict(zip(d2020["İlçe"], d2020["total_pop"].astype(int)))
    assert len(official) == 39, f"expected 39 districts in the 2020 population source, got {len(official)}"
    return official


def load_citywide_grid() -> gpd.GeoDataFrame:
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 22322, f"expected the frozen citywide grid (22,322 cells), found {len(grid)}"
    assert grid["grid_id"].is_unique
    return grid


def district_level_external_check(pixels: gpd.GeoDataFrame, districts: gpd.GeoDataFrame, official: dict) -> dict:
    overlay = gpd.overlay(
        districts[["district", "geometry"]], pixels[["population", "pixel_area_m2", "geometry"]],
        how="intersection", keep_geom_type=True,
    )
    overlay["intersection_area_m2"] = overlay.geometry.area
    overlay["allocated_population"] = overlay["population"] * overlay["intersection_area_m2"] / overlay["pixel_area_m2"]
    raster_totals = overlay.groupby("district")["allocated_population"].sum().to_dict()

    comparison = {}
    for district, official_pop in official.items():
        raster_val = raster_totals.get(district, 0.0)
        pct_diff = (raster_val - official_pop) / official_pop * 100 if official_pop else float("nan")
        comparison[district] = {
            "official_2020": official_pop,
            "worldpop_raster_2020": round(raster_val),
            "pct_difference": round(pct_diff, 2),
        }
    return comparison


def main() -> None:
    print("=" * 72)
    print("Citywide population features (39 districts, 22,322-cell grid)")
    print("=" * 72)

    grid = load_citywide_grid()
    districts = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    study_area = gpd.read_file(cfg.DATA_PROCESSED / "study_area_metric.gpkg").geometry.iloc[0]
    official = load_citywide_official_population_2020()
    print(f"Loaded official 2020 population for {len(official)} districts (source: TÜİK ADNKS via İBB Nüfus Bilgileri)")

    raster_path = fetch_worldpop_raster()
    print(f"Using WorldPop raster: {raster_path} (already cached, whole-Turkey, no new fetch)")

    print("\n[1/3] Raw area-weighted allocation...")
    pop_features, pixels, alloc_diag = allocate_population_to_grid(raster_path, grid, study_area)
    print(f"  mass-preservation: source={alloc_diag['source_population_total']:,.1f}, "
          f"allocated={alloc_diag['allocated_population_total']:,.1f}, "
          f"diff={alloc_diag['allocation_difference_pct']:.4f}%")

    print("\n[2/3] Citywide calibration (all 39 districts, same three-way overlay method)...")
    factors = compute_calibration_factors(pop_features, grid, official)
    calibrated, calib_diag = calibrate_population_to_grid(raster_path, grid, study_area, districts, factors)

    pop_features["population_worldpop_raw"] = pop_features["population"]
    pop_features["population_density_worldpop_raw_km2"] = pop_features["population_density_km2"]
    pop_features = pop_features.merge(calibrated, on="grid_id", how="left", validate="one_to_one")
    assert len(pop_features) == 22322 and pop_features["grid_id"].is_unique
    assert pop_features["population_calibrated"].isna().sum() == 0

    print("\n[3/3] QA...")
    district_check = district_level_external_check(pixels, districts, official)
    merged = grid[["grid_id", "district"]].merge(pop_features, on="grid_id")

    numeric_cols = ["population_worldpop_raw", "population_density_worldpop_raw_km2", "population_calibrated", "population_density_calibrated_km2"]
    desc = merged[numeric_cols].describe().T[["min", "50%", "mean", "max"]].rename(columns={"50%": "median"}).round(2).to_dict(orient="index")

    flagged = []
    for c in numeric_cols:
        vals = merged[c]
        mu, sigma = vals.mean(), vals.std()
        if sigma == 0 or np.isnan(sigma):
            continue
        z = (vals - mu) / sigma
        extreme = merged.loc[z.abs() > 4, ["grid_id", "district"]].copy()
        if len(extreme):
            extreme["feature"] = c
            extreme["value"] = vals.loc[extreme.index]
            extreme["z_score"] = z.loc[extreme.index]
            flagged.append(extreme)
    flagged_df = pd.concat(flagged, ignore_index=True) if flagged else pd.DataFrame(columns=["grid_id", "district", "feature", "value", "z_score"])

    residuals = {d: v["pct_difference"] for d, v in district_check.items()}
    worst = sorted(residuals.items(), key=lambda kv: abs(kv[1]), reverse=True)[:5]

    qa = {
        "source_dataset": pcfg.WORLDPOP["dataset_name"],
        "reference_year": pcfg.WORLDPOP["reference_year"],
        "calibration_source": "TÜİK ADNKS 2020 district totals via İBB 'Nüfus Bilgileri' open dataset, all 39 districts",
        "district_name_aliases_applied": DISTRICT_NAME_ALIASES,
        "n_grid_cells": len(pop_features),
        "n_districts": 39,
        "mass_preservation": alloc_diag,
        "n_cells_spanning_multiple_districts_handled_by_split": calib_diag["n_cells_spanning_multiple_districts_in_pixel_overlay"],
        "population_by_district_calibrated": merged.groupby("district")["population_calibrated"].sum().round(1).to_dict(),
        "district_external_sanity_check_vs_official": district_check,
        "worst_5_district_residuals_pct": worst,
        "n_zero_population_cells_raw": int((pop_features["population_worldpop_raw"] == 0).sum()),
        "pct_zero_population_cells_raw": float((pop_features["population_worldpop_raw"] == 0).mean() * 100),
        "descriptive_stats": desc,
        "n_extreme_value_cells_flagged": len(flagged_df),
        "top_flagged_cells": flagged_df.sort_values("z_score", ascending=False).head(20).to_dict(orient="records") if len(flagged_df) else [],
        "missing_values": {c: int(pop_features[c].isna().sum()) for c in numeric_cols},
        "total_population_before_calibration": float(pop_features["population_worldpop_raw"].sum()),
        "total_population_after_calibration": float(pop_features["population_calibrated"].sum()),
        "known_limitations": pcfg.WORLDPOP["known_limitations"],
        "completeness_status": "COMPLETE -- all 39 districts calibrated using official citywide totals (not extrapolated from the 3-district pilot)",
    }

    out_dir = cfg.DATA_FEATURES
    out_dir.mkdir(parents=True, exist_ok=True)
    base = grid[["grid_id", "district", "geometry"]]
    pop_gdf = gpd.GeoDataFrame(base.merge(pop_features, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)
    out_path = out_dir / "population_features_citywide.parquet"
    pop_gdf.to_parquet(out_path)
    print(f"\n[save] {out_path}")

    qa_dir = cfg.DATA_PROCESSED / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_path = qa_dir / "population_qa_citywide.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {qa_path}")

    value_cols = ["population_worldpop_raw", "population_calibrated", "population_density_calibrated_km2"]
    report = coverage_report(pop_gdf, value_cols)
    print_report(report, "population")
    gate_path = qa_dir / "coverage_gate_population.json"
    gate_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[save] {gate_path}")

    print("\n--- SUMMARY ---")
    print(f"Total citywide population (calibrated): {qa['total_population_after_calibration']:,.0f}")
    print(f"Total citywide population (raw WorldPop): {qa['total_population_before_calibration']:,.0f}")
    print(f"Mass-preservation error in raw allocation: {alloc_diag['allocation_difference_pct']:.4f}%")
    print(f"Worst 5 district calibration residuals (pre-calibration, raw-vs-official): {worst}")


if __name__ == "__main__":
    main()
