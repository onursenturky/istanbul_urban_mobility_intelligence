"""Population validation audit — calibration step.

Adds district-constrained calibrated population as NEW columns alongside
the untouched raw WorldPop features (renamed-with-alias pattern, same as
the Phase 3B rail_stations_within_1000m rename):
  - population_worldpop_raw, population_density_worldpop_raw_km2  (= existing
    population / population_density_km2, copied, never overwritten)
  - population_calibrated, population_density_calibrated_km2       (new)

Run from the project root:
    .venv/bin/python -m src.features.build_population_calibration
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.data.fetch_population_data import fetch_worldpop_raster
from src.features import population_source_config as pcfg
from src.features.population_calibration import calibrate_population_to_grid, compute_calibration_factors
from src.utils import config as cfg


def main() -> None:
    print("=" * 72)
    print("Population validation audit — district-constrained calibration")
    print("=" * 72)

    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert len(grid) == 514 and grid["grid_id"].is_unique
    districts = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    study_area = gpd.read_file(cfg.DATA_PROCESSED / "study_area_metric.gpkg").geometry.iloc[0]

    pop_features = gpd.read_parquet(cfg.DATA_FEATURES / "population_features.parquet")
    combined = gpd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features.parquet")
    raster_path = fetch_worldpop_raster()

    factors = compute_calibration_factors(pop_features, grid, pcfg.OFFICIAL_DISTRICT_POPULATION_2020)
    print("\n--- CALIBRATION FACTORS (grid-based district totals) ---")
    print(json.dumps(factors, indent=2, ensure_ascii=False))

    calibrated, calib_diag = calibrate_population_to_grid(raster_path, grid, study_area, districts, factors)
    assert len(calibrated) == 514 and calibrated["grid_id"].is_unique

    # Add new columns without touching the existing raw ones.
    for df_name, df in [("population_features", pop_features), ("combined", combined)]:
        assert "population" in df.columns and "population_density_km2" in df.columns
        df["population_worldpop_raw"] = df["population"]
        df["population_density_worldpop_raw_km2"] = df["population_density_km2"]

    pop_features = pop_features.merge(calibrated, on="grid_id", how="left", validate="one_to_one")
    combined = combined.merge(calibrated, on="grid_id", how="left", validate="one_to_one")

    assert pop_features["population"].equals(pop_features["population_worldpop_raw"])
    assert combined["population_density_km2"].equals(combined["population_density_worldpop_raw_km2"])
    assert len(pop_features) == 514 and len(combined) == 514
    assert pop_features["grid_id"].is_unique and combined["grid_id"].is_unique
    for c in ["population_calibrated", "population_density_calibrated_km2"]:
        assert pop_features[c].isna().sum() == 0
        assert combined[c].isna().sum() == 0

    # --- Validation report ---
    merged_district = grid[["grid_id", "district"]].merge(
        pop_features[["grid_id", "population_worldpop_raw", "population_calibrated"]], on="grid_id"
    )
    by_district = merged_district.groupby("district")[["population_worldpop_raw", "population_calibrated"]].sum()

    district_report = {}
    for district, official_pop in pcfg.OFFICIAL_DISTRICT_POPULATION_2020.items():
        raw = by_district.loc[district, "population_worldpop_raw"]
        cal = by_district.loc[district, "population_calibrated"]
        district_report[district] = {
            "raw_worldpop_total": round(raw, 1),
            "official_total": official_pop,
            "calibration_factor": round(factors[district]["calibration_factor"], 4),
            "calibrated_total": round(cal, 1),
            "residual_error_pct": round((cal - official_pop) / official_pop * 100, 4),
        }

    total_before = float(pop_features["population_worldpop_raw"].sum())
    total_after = float(pop_features["population_calibrated"].sum())

    print("\n--- CALIBRATION VALIDATION ---")
    print(json.dumps(district_report, indent=2, ensure_ascii=False))
    print(f"\nTotal study-area population BEFORE calibration: {total_before:,.1f}")
    print(f"Total study-area population AFTER calibration:  {total_after:,.1f}")
    print(f"Diagnostics: {calib_diag}")

    # --- Save ---
    pop_features.to_parquet(cfg.DATA_FEATURES / "population_features.parquet")
    combined.to_parquet(cfg.DATA_FEATURES / "urban_mobility_features.parquet")

    audit_report = {
        "calibration_factors_by_district": factors,
        "district_validation": district_report,
        "total_population_before_calibration": total_before,
        "total_population_after_calibration": total_after,
        "n_cells_spanning_multiple_districts_handled_by_split": calib_diag["n_cells_spanning_multiple_districts_in_pixel_overlay"],
    }
    with open(cfg.DATA_FEATURES / "population_calibration_audit.json", "w", encoding="utf-8") as f:
        json.dump(audit_report, f, indent=2, ensure_ascii=False, default=str)

    # --- Comparison maps ---
    minx, miny, maxx, maxy = districts.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    extent = (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)

    def _base(ax, title):
        districts.boundary.plot(ax=ax, linewidth=1.4, color="black", zorder=3)
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        ax.set_title(title)
        ax.set_axis_off()

    vmax = max(combined["population_density_worldpop_raw_km2"].max(), combined["population_density_calibrated_km2"].max())

    fig, ax = plt.subplots(figsize=(10, 10))
    combined.plot(column="population_density_worldpop_raw_km2", cmap="magma_r", vmin=0, vmax=vmax, ax=ax, legend=True, edgecolor="#666666", linewidth=0.1)
    _base(ax, "Raw WorldPop population density (people/km^2)")
    fig.savefig(cfg.OUTPUTS_MAPS / "population_density_raw_worldpop.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 10))
    combined.plot(column="population_density_calibrated_km2", cmap="magma_r", vmin=0, vmax=vmax, ax=ax, legend=True, edgecolor="#666666", linewidth=0.1)
    _base(ax, "District-calibrated population density (people/km^2)")
    fig.savefig(cfg.OUTPUTS_MAPS / "population_density_calibrated.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    pct_adjustment = (
        (combined["population_calibrated"] - combined["population_worldpop_raw"])
        / combined["population_worldpop_raw"].replace(0, np.nan) * 100
    )
    fig, ax = plt.subplots(figsize=(10, 10))
    plot_gdf = combined.assign(_d=pct_adjustment)
    vabs = float(np.nanmax(np.abs(pct_adjustment)))
    plot_gdf.plot(column="_d", cmap="RdBu_r", vmin=-vabs, vmax=vabs, ax=ax, legend=True, edgecolor="#666666", linewidth=0.1, missing_kwds={"color": "lightgrey"})
    _base(ax, "Calibration adjustment: % change from raw to calibrated population\n(blue = reduced, red = increased)")
    fig.savefig(cfg.OUTPUTS_MAPS / "population_calibration_adjustment_pct.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    print("\n--- OUTPUT FILES ---")
    print(f"  updated: {cfg.DATA_FEATURES / 'population_features.parquet'}")
    print(f"  updated: {cfg.DATA_FEATURES / 'urban_mobility_features.parquet'}")
    print(f"  new:     {cfg.DATA_FEATURES / 'population_calibration_audit.json'}")
    print(f"  map:     {cfg.OUTPUTS_MAPS / 'population_density_raw_worldpop.png'}")
    print(f"  map:     {cfg.OUTPUTS_MAPS / 'population_density_calibrated.png'}")
    print(f"  map:     {cfg.OUTPUTS_MAPS / 'population_calibration_adjustment_pct.png'}")


if __name__ == "__main__":
    main()
