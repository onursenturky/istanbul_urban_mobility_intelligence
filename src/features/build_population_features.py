"""Phase 3C orchestrator: population features for the 514-cell grid.

Loads the cached WorldPop raster (fetched by src.data.fetch_population_data),
area-weight-allocates it onto the canonical Phase 2 grid, verifies Phase 3A
and Phase 3B features are untouched, runs QA including an external sanity
check against official district totals, and writes:
  - data/processed/features/population_features.parquet
  - data/processed/features/urban_mobility_features.parquet (base + 3A + 3B + 3C)
  - data/processed/features/population_feature_dictionary.csv
  - data/processed/features/population_qa_report.json
  - outputs/maps/population_{count,density,vs_poi_density}.png

Run from the project root:
    .venv/bin/python -m src.features.build_population_features
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.data.fetch_population_data import fetch_worldpop_raster
from src.features import population_feature_dictionary as feat_dict
from src.features import population_source_config as pcfg
from src.features.population_features import allocate_population_to_grid
from src.utils import config as cfg


def load_grid() -> gpd.GeoDataFrame:
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 514, f"expected the canonical 514-cell V1 grid, found {len(grid)}"
    assert grid["grid_id"].is_unique
    return grid


def load_existing_combined() -> gpd.GeoDataFrame:
    path = cfg.DATA_FEATURES / "urban_mobility_features.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run Phase 3A and 3B first.")
    return gpd.read_parquet(path)


def _assert_all_grid_ids_present(df: pd.DataFrame, grid_ids: pd.Index, label: str) -> None:
    missing = set(grid_ids) - set(df["grid_id"])
    assert not missing, f"{label}: {len(missing)} grid cells disappeared during processing"
    assert len(df) == len(grid_ids), f"{label}: row count {len(df)} != {len(grid_ids)} grid cells"


def district_level_external_check(pixels: gpd.GeoDataFrame) -> dict:
    districts = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    overlay = gpd.overlay(
        districts[["district", "geometry"]], pixels[["population", "pixel_area_m2", "geometry"]],
        how="intersection", keep_geom_type=True,
    )
    overlay["intersection_area_m2"] = overlay.geometry.area
    overlay["allocated_population"] = (
        overlay["population"] * overlay["intersection_area_m2"] / overlay["pixel_area_m2"]
    )
    raster_totals = overlay.groupby("district")["allocated_population"].sum().to_dict()

    comparison = {}
    for district, official in pcfg.OFFICIAL_DISTRICT_POPULATION_2020.items():
        raster_val = raster_totals.get(district, 0.0)
        pct_diff = (raster_val - official) / official * 100
        comparison[district] = {
            "official_2020": official,
            "worldpop_raster_2020": round(raster_val),
            "pct_difference": round(pct_diff, 2),
        }
    return {
        "method": "Direct area-weighted intersection of the raster with each district's own polygon "
        "(districts_metric.gpkg) — independent of the 514-cell grid's district-assignment rule, so "
        "this isolates raster-vs-official accuracy from grid-boundary edge effects.",
        "official_source_note": pcfg.OFFICIAL_POPULATION_SOURCE_NOTE,
        "comparison": comparison,
    }


def run_qa(pop_features: pd.DataFrame, grid: gpd.GeoDataFrame, alloc_diag: dict, district_check: dict) -> dict:
    merged = grid[["grid_id", "district"]].merge(pop_features, on="grid_id")
    pop_by_district = merged.groupby("district")["population"].sum().round(1).to_dict()

    numeric_cols = ["population", "population_density_km2"]
    desc = merged[numeric_cols].describe().T[["min", "50%", "mean", "max"]].rename(columns={"50%": "median"})
    descriptive_stats = desc.round(2).to_dict(orient="index")

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
    flagged_df = (
        pd.concat(flagged, ignore_index=True).sort_values("z_score", ascending=False)
        if flagged else pd.DataFrame(columns=["grid_id", "district", "feature", "value", "z_score"])
    )

    qa = {
        "source_dataset": pcfg.WORLDPOP["dataset_name"],
        "reference_year": pcfg.WORLDPOP["reference_year"],
        "native_resolution": pcfg.WORLDPOP["native_resolution"],
        "source_population_total_in_study_area": round(alloc_diag["source_population_total"], 1),
        "allocated_population_total": round(alloc_diag["allocated_population_total"], 1),
        "allocation_difference_pct": round(alloc_diag["allocation_difference_pct"], 3),
        "n_valid_pixels_read": alloc_diag["n_valid_pixels"],
        "n_invalid_or_negative_pixels_beyond_nodata": alloc_diag["n_invalid_or_negative_pixels_beyond_nodata"],
        "population_by_district": pop_by_district,
        "district_external_sanity_check": district_check,
        "n_grids_with_zero_population": int((pop_features["population"] == 0).sum()),
        "pct_grids_with_zero_population": float((pop_features["population"] == 0).mean() * 100),
        "descriptive_stats": descriptive_stats,
        "n_extreme_value_cells_flagged": len(flagged_df),
        "top_flagged_cells": flagged_df.head(20).to_dict(orient="records"),
        "missing_values": {c: int(pop_features[c].isna().sum()) for c in numeric_cols},
    }
    return qa


def verify_prior_features_unchanged(existing: gpd.GeoDataFrame, combined: gpd.GeoDataFrame) -> bool:
    prior_cols = [c for c in existing.columns if c not in ("grid_id", "district", "land_area_m2", "geometry")]
    a = existing.set_index("grid_id")[prior_cols].sort_index()
    b = combined.set_index("grid_id")[prior_cols].sort_index()
    return a.equals(b)


def save_outputs(pop_gdf: gpd.GeoDataFrame, combined: gpd.GeoDataFrame) -> dict:
    cfg.DATA_FEATURES.mkdir(parents=True, exist_ok=True)
    paths = {
        "population_parquet": cfg.DATA_FEATURES / "population_features.parquet",
        "combined_parquet": cfg.DATA_FEATURES / "urban_mobility_features.parquet",
        "feature_dictionary": cfg.DATA_FEATURES / "population_feature_dictionary.csv",
    }
    pop_gdf.to_parquet(paths["population_parquet"])
    combined.to_parquet(paths["combined_parquet"])
    feat_dict.as_dataframe().to_csv(paths["feature_dictionary"], index=False)
    return paths


def _map_extent(districts_gdf: gpd.GeoDataFrame):
    minx, miny, maxx, maxy = districts_gdf.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    return (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)


def make_validation_maps(combined: gpd.GeoDataFrame) -> dict:
    districts_gdf = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    extent = _map_extent(districts_gdf)
    cfg.OUTPUTS_MAPS.mkdir(parents=True, exist_ok=True)
    paths = {}

    def _base(ax, title):
        districts_gdf.boundary.plot(ax=ax, linewidth=1.4, color="black", zorder=3)
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        ax.set_title(title)
        ax.set_axis_off()

    fig, ax = plt.subplots(figsize=(10, 10))
    combined.plot(column="population", cmap="magma_r", ax=ax, legend=True, edgecolor="#666666", linewidth=0.1)
    _base(ax, f"Population per {cfg.GRID_RESOLUTION_M}m cell ({pcfg.WORLDPOP['reference_year']}, WorldPop constrained)")
    out = cfg.OUTPUTS_MAPS / "population_count.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    paths["population_count"] = out

    fig, ax = plt.subplots(figsize=(10, 10))
    combined.plot(column="population_density_km2", cmap="magma_r", ax=ax, legend=True, edgecolor="#666666", linewidth=0.1)
    _base(ax, "Population density (people per km^2)")
    out = cfg.OUTPUTS_MAPS / "population_density.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    paths["population_density"] = out

    if "poi_density_km2" in combined.columns:
        z_pop = (combined["population_density_km2"] - combined["population_density_km2"].mean()) / combined["population_density_km2"].std()
        z_poi = (combined["poi_density_km2"] - combined["poi_density_km2"].mean()) / combined["poi_density_km2"].std()
        diff = z_pop - z_poi
        fig, ax = plt.subplots(figsize=(10, 10))
        plot_gdf = combined.assign(_d=diff)
        vmax = float(np.abs(diff).max())
        plot_gdf.plot(column="_d", cmap="RdBu", vmin=-vmax, vmax=vmax, ax=ax, legend=True, edgecolor="#666666", linewidth=0.1)
        _base(ax, "Residential-heavy (blue) vs activity-heavy (red)\nz(population density) - z(POI density)")
        out = cfg.OUTPUTS_MAPS / "population_vs_poi_density.png"
        fig.savefig(out, dpi=200, bbox_inches="tight")
        plt.close(fig)
        paths["population_vs_poi_density"] = out

    return paths


def main() -> None:
    print("=" * 72)
    print("Istanbul Urban Mobility Intelligence — Phase 3C: Population & Demographic Exposure")
    print("=" * 72)

    grid = load_grid()
    existing_combined = load_existing_combined()
    study_area = gpd.read_file(cfg.DATA_PROCESSED / "study_area_metric.gpkg").geometry.iloc[0]
    grid_ids = grid["grid_id"]

    raster_path = fetch_worldpop_raster()
    pop_features, pixels, alloc_diag = allocate_population_to_grid(raster_path, grid, study_area)
    _assert_all_grid_ids_present(pop_features, grid_ids, "population_allocation")

    district_check = district_level_external_check(pixels)
    qa = run_qa(pop_features, grid, alloc_diag, district_check)

    base = grid[["grid_id", "district", "land_area_m2", "geometry"]]
    pop_gdf = gpd.GeoDataFrame(base.merge(pop_features, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)

    combined = existing_combined.merge(pop_features, on="grid_id", how="left", validate="one_to_one")
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=cfg.METRIC_CRS)

    unchanged = verify_prior_features_unchanged(existing_combined, combined)
    assert unchanged, "Phase 3A/3B features changed during the Phase 3C merge — aborting."
    assert len(combined) == 514 and combined["grid_id"].is_unique
    qa["prior_features_unchanged"] = bool(unchanged)

    output_paths = save_outputs(pop_gdf, combined)
    map_paths = make_validation_maps(combined)

    print("\n--- SOURCE ---")
    print(json.dumps({k: v for k, v in pcfg.WORLDPOP.items() if k != "known_limitations"}, indent=2, ensure_ascii=False))
    print("known_limitations:")
    for lim in pcfg.WORLDPOP["known_limitations"]:
        print(f"  - {lim}")

    print("\n--- MASS-PRESERVATION CHECK ---")
    print(f"  source_population_total (direct study-area intersection): {alloc_diag['source_population_total']:,.1f}")
    print(f"  allocated_population_total (summed across 514 grid cells): {alloc_diag['allocated_population_total']:,.1f}")
    print(f"  allocation_difference_pct: {alloc_diag['allocation_difference_pct']:.3f}%")

    print("\n--- DISTRICT EXTERNAL SANITY CHECK (vs TÜİK ADNKS 2020) ---")
    print(json.dumps(district_check["comparison"], indent=2, ensure_ascii=False))

    print("\n--- QA REPORT ---")
    qa_printable = {k: v for k, v in qa.items() if k not in ("descriptive_stats", "top_flagged_cells", "district_external_sanity_check")}
    print(json.dumps(qa_printable, indent=2, default=str, ensure_ascii=False))

    print("\n--- DESCRIPTIVE STATS (min / median / mean / max) ---")
    print(json.dumps(qa["descriptive_stats"], indent=2))

    print("\n--- TOP FLAGGED (|z| > 4) CELLS ---")
    print(json.dumps(qa["top_flagged_cells"], indent=2, default=str, ensure_ascii=False))

    print("\n--- OUTPUT FILES ---")
    for k, v in output_paths.items():
        print(f"  {k}: {v}")
    for k, v in map_paths.items():
        print(f"  map[{k}]: {v}")

    with open(cfg.DATA_FEATURES / "population_qa_report.json", "w", encoding="utf-8") as f:
        json.dump(qa, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nFull QA report saved -> {cfg.DATA_FEATURES / 'population_qa_report.json'}")


if __name__ == "__main__":
    main()
