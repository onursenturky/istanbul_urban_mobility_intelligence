"""Phase 3B orchestrator: transit accessibility features for the 514-cell grid.

Loads the cached GTFS feeds (fetched by src.data.fetch_transit_data),
classifies stops into six modes, computes station-count/accessibility/route-
diversity/bus-departure features, merges them onto the canonical Phase 2
grid, verifies Phase 3A features are untouched, runs QA, and writes:
  - data/processed/features/transit_features.parquet
  - data/processed/features/urban_mobility_features.parquet (base + 3A + 3B)
  - data/processed/features/transit_feature_dictionary.csv
  - data/processed/features/transit_qa_report.json
  - outputs/maps/transit_{rail_metro_distance,bus_density,stops_500m,modes_accessible}.png

Run from the project root:
    .venv/bin/python -m src.features.build_transit_features
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.data.fetch_transit_data import fetch_iett_gtfs, fetch_main_gtfs
from src.features import transit_feature_dictionary as feat_dict
from src.features import transit_tag_config as tcfg
from src.features.transit_accessibility import (
    MODE_COUNT_COLS,
    MODE_DISTANCE_COLS,
    compute_distance_and_accessibility_features,
    compute_station_counts,
)
from src.features.transit_infrastructure import load_all_transit_stops
from src.features.transit_service import compute_bus_departures, compute_route_diversity
from src.utils import config as cfg


def load_grid() -> gpd.GeoDataFrame:
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 514, f"expected the canonical 514-cell V1 grid, found {len(grid)}"
    assert grid["grid_id"].is_unique
    return grid


def load_osm_features() -> gpd.GeoDataFrame:
    path = cfg.DATA_FEATURES / "osm_urban_features.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run Phase 3A (src.features.build_osm_features) first.")
    return gpd.read_parquet(path)


def _assert_all_grid_ids_present(df: pd.DataFrame, grid_ids: pd.Index, label: str) -> None:
    missing = set(grid_ids) - set(df["grid_id"])
    assert not missing, f"{label}: {len(missing)} grid cells disappeared during processing"
    assert len(df) == len(grid_ids), f"{label}: row count {len(df)} != {len(grid_ids)} grid cells"


def compute_all_transit_features(grid: gpd.GeoDataFrame) -> tuple[pd.DataFrame, dict]:
    main_dir = fetch_main_gtfs()
    iett_dir = fetch_iett_gtfs()

    stops, load_diag = load_all_transit_stops(main_dir, iett_dir)
    grid_ids = grid["grid_id"]

    counts_df = compute_station_counts(stops, grid)
    _assert_all_grid_ids_present(counts_df, grid_ids, "station_counts")

    dist_df = compute_distance_and_accessibility_features(stops, grid)
    _assert_all_grid_ids_present(dist_df, grid_ids, "distance_accessibility")

    route_df = compute_route_diversity(stops, grid)
    _assert_all_grid_ids_present(route_df, grid_ids, "route_diversity")

    departures_df, departures_diag = compute_bus_departures(iett_dir, stops, grid)
    _assert_all_grid_ids_present(departures_df, grid_ids, "bus_departures")

    merged = counts_df.merge(dist_df, on="grid_id")
    merged = merged.merge(route_df, on="grid_id")
    merged = merged.merge(departures_df, on="grid_id")
    _assert_all_grid_ids_present(merged, grid_ids, "final transit merge")
    assert merged["grid_id"].is_unique

    diagnostics = {"stop_loading": load_diag, "bus_departures": departures_diag, "stops_gdf": stops}
    return merged, diagnostics


def run_qa(transit: pd.DataFrame, grid: gpd.GeoDataFrame, diagnostics: dict) -> dict:
    stops = diagnostics["stops_gdf"]
    numeric_cols = [c for c in transit.columns if c != "grid_id" and pd.api.types.is_numeric_dtype(transit[c])]

    missing_by_feature = {c: int(transit[c].isna().sum()) for c in numeric_cols if transit[c].isna().any()}
    desc = transit[numeric_cols].describe().T[["min", "50%", "mean", "max"]].rename(columns={"50%": "median"})
    descriptive_stats = desc.round(3).to_dict(orient="index")

    flagged = []
    for c in numeric_cols:
        vals = transit[c]
        mu, sigma = vals.mean(), vals.std()
        if sigma == 0 or np.isnan(sigma):
            continue
        z = (vals - mu) / sigma
        extreme = transit.loc[z.abs() > 4, ["grid_id"]].copy()
        if len(extreme):
            extreme["feature"] = c
            extreme["value"] = vals.loc[extreme.index]
            extreme["z_score"] = z.loc[extreme.index]
            flagged.append(extreme)
    flagged_df = (
        pd.concat(flagged, ignore_index=True).sort_values("z_score", ascending=False)
        if flagged else pd.DataFrame(columns=["grid_id", "feature", "value", "z_score"])
    )

    total_by_mode_citywide = stops["mode"].value_counts().to_dict()
    stops_metric = stops.to_crs(cfg.METRIC_CRS)
    study_area = gpd.read_file(cfg.DATA_PROCESSED / "study_area_metric.gpkg").geometry.iloc[0]
    in_study_area = stops_metric[stops_metric.geometry.within(study_area)]
    n_in_study_area_by_mode = in_study_area["mode"].value_counts().to_dict()

    pct_zero_transit = float((transit["total_transit_stop_count"] == 0).mean() * 100)
    pct_within_500m = float((transit["transit_stops_within_500m"] > 0).mean() * 100)
    pct_within_1km_rail = float((transit["rail_stations_within_1000m"] > 0).mean() * 100)

    qa = {
        "n_grid_rows": len(transit),
        "grid_id_unique": bool(transit["grid_id"].is_unique),
        "total_stops_by_mode_citywide": total_by_mode_citywide,
        "stops_inside_study_area_by_mode": n_in_study_area_by_mode,
        "n_stops_with_no_in_scope_route": {
            "main_gtfs": diagnostics["stop_loading"]["main_gtfs"]["n_stops_with_no_in_scope_route"],
            "iett_gtfs": diagnostics["stop_loading"]["iett_gtfs"]["n_stops_with_no_in_scope_route"],
        },
        "n_stops_with_unrecoverable_invalid_coordinates_iett": diagnostics["stop_loading"]["iett_gtfs"].get(
            "n_stops_with_unrecoverable_invalid_coordinates", 0
        ),
        "n_stops_with_mangled_coordinates_recovered_iett": diagnostics["stop_loading"]["iett_gtfs"].get(
            "n_stops_with_mangled_coordinates_recovered", 0
        ),
        "n_duplicate_stops_removed": diagnostics["stop_loading"]["n_duplicate_stops_removed"],
        "pct_grids_with_zero_transit_stop": pct_zero_transit,
        "pct_grids_within_500m_of_transit": pct_within_500m,
        "pct_grids_within_1km_of_rail": pct_within_1km_rail,
        "missing_values_by_feature": missing_by_feature,
        "descriptive_stats": descriptive_stats,
        "n_extreme_value_cells_flagged": len(flagged_df),
        "top_flagged_cells": flagged_df.head(20).to_dict(orient="records"),
        "bus_departures_diagnostics": diagnostics["bus_departures"],
    }
    return qa


def verify_osm_features_unchanged(osm_features: gpd.GeoDataFrame, combined: gpd.GeoDataFrame) -> bool:
    osm_cols = [c for c in osm_features.columns if c not in ("grid_id", "district", "land_area_m2", "geometry")]
    a = osm_features.set_index("grid_id")[osm_cols].sort_index()
    b = combined.set_index("grid_id")[osm_cols].sort_index()
    return a.equals(b)


def save_outputs(transit: gpd.GeoDataFrame, combined: gpd.GeoDataFrame) -> dict:
    cfg.DATA_FEATURES.mkdir(parents=True, exist_ok=True)
    paths = {
        "transit_parquet": cfg.DATA_FEATURES / "transit_features.parquet",
        "combined_parquet": cfg.DATA_FEATURES / "urban_mobility_features.parquet",
        "feature_dictionary": cfg.DATA_FEATURES / "transit_feature_dictionary.csv",
    }
    transit.to_parquet(paths["transit_parquet"])
    combined.to_parquet(paths["combined_parquet"])
    feat_dict.as_dataframe().to_csv(paths["feature_dictionary"], index=False)
    return paths


def _map_extent(districts_gdf: gpd.GeoDataFrame):
    minx, miny, maxx, maxy = districts_gdf.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    return (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)


def make_validation_maps(combined: gpd.GeoDataFrame, stops: gpd.GeoDataFrame) -> dict:
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

    # 1. distance to nearest rail/metro station (min of metro & rail; tram excluded per map title)
    fig, ax = plt.subplots(figsize=(10, 10))
    rail_metro_dist = combined[["distance_to_nearest_metro_m", "distance_to_nearest_rail_m"]].min(axis=1)
    plot_gdf = combined.assign(_d=rail_metro_dist)
    plot_gdf.plot(column="_d", cmap="viridis_r", ax=ax, legend=True, edgecolor="#666666", linewidth=0.1)
    rail_pts = stops[stops["mode"].isin(("metro", "rail"))]
    rail_pts.plot(ax=ax, color="red", markersize=8, zorder=4)
    _base(ax, "Distance to nearest metro/rail station (m)")
    out = cfg.OUTPUTS_MAPS / "transit_rail_metro_distance.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    paths["rail_metro_distance"] = out

    # 2. bus-stop density (bus_stop_count / km^2 of land area) — a plotting-only
    # derived quantity (not a persisted feature), consistent with Phase 3A's
    # poi_density_km2 convention.
    fig, ax = plt.subplots(figsize=(10, 10))
    bus_density = combined["bus_stop_count"] / (combined["land_area_m2"] / 1e6)
    plot_gdf = combined.assign(_d=bus_density)
    plot_gdf.plot(column="_d", cmap="Blues", ax=ax, legend=True, edgecolor="#666666", linewidth=0.1)
    bus_pts = stops[stops["mode"] == "bus"]
    bus_pts.plot(ax=ax, color="#333333", markersize=0.5, alpha=0.4, zorder=4)
    _base(ax, "Bus-stop density (stops per km^2)")
    out = cfg.OUTPUTS_MAPS / "transit_bus_density.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    paths["bus_density"] = out

    # 3. transit stops within 500m
    fig, ax = plt.subplots(figsize=(10, 10))
    combined.plot(column="transit_stops_within_500m", cmap="YlOrRd", ax=ax, legend=True, edgecolor="#666666", linewidth=0.1)
    _base(ax, "Transit stops within 500 m of cell centroid")
    out = cfg.OUTPUTS_MAPS / "transit_stops_within_500m.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    paths["stops_within_500m"] = out

    # 4. number of transit modes accessible
    fig, ax = plt.subplots(figsize=(10, 10))
    combined.plot(column="number_of_transit_modes_accessible", cmap="PuBuGn", ax=ax, legend=True, edgecolor="#666666", linewidth=0.1)
    _base(ax, f"Transit modes accessible within {cfg.TRANSIT_ACCESSIBILITY_RADIUS_M} m")
    out = cfg.OUTPUTS_MAPS / "transit_modes_accessible.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    paths["modes_accessible"] = out

    return paths


def main() -> None:
    print("=" * 72)
    print("Istanbul Urban Mobility Intelligence — Phase 3B: Transit Accessibility")
    print("=" * 72)

    grid = load_grid()
    osm_features = load_osm_features()

    transit_features, diagnostics = compute_all_transit_features(grid)
    stops = diagnostics["stops_gdf"]

    base = grid[["grid_id", "district", "land_area_m2", "geometry"]]
    transit_gdf = gpd.GeoDataFrame(base.merge(transit_features, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)

    combined = osm_features.merge(
        transit_features, on="grid_id", how="left", validate="one_to_one"
    )
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=cfg.METRIC_CRS)

    unchanged = verify_osm_features_unchanged(osm_features, combined)
    assert unchanged, "Phase 3A OSM features changed during the Phase 3B merge — aborting."
    assert len(combined) == 514 and combined["grid_id"].is_unique

    qa = run_qa(transit_features, grid, diagnostics)
    qa["phase_3a_features_unchanged"] = bool(unchanged)

    output_paths = save_outputs(transit_gdf, combined)
    map_paths = make_validation_maps(combined, stops)

    print("\n--- SOURCE SUMMARY ---")
    print(json.dumps({"main_gtfs": tcfg.MAIN_GTFS["dataset_url"], "iett_gtfs": tcfg.IETT_GTFS["dataset_url"]}, indent=2))

    print("\n--- QA REPORT ---")
    qa_printable = {k: v for k, v in qa.items() if k not in ("descriptive_stats", "top_flagged_cells")}
    print(json.dumps(qa_printable, indent=2, default=str))

    print("\n--- DESCRIPTIVE STATS (min / median / mean / max) ---")
    print(json.dumps(qa["descriptive_stats"], indent=2))

    print("\n--- TOP FLAGGED (|z| > 4) CELLS ---")
    print(json.dumps(qa["top_flagged_cells"], indent=2, default=str))

    print("\n--- OUTPUT FILES ---")
    for k, v in output_paths.items():
        print(f"  {k}: {v}")
    for k, v in map_paths.items():
        print(f"  map[{k}]: {v}")

    with open(cfg.DATA_FEATURES / "transit_qa_report.json", "w", encoding="utf-8") as f:
        json.dump(qa, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nFull QA report saved -> {cfg.DATA_FEATURES / 'transit_qa_report.json'}")


if __name__ == "__main__":
    main()
