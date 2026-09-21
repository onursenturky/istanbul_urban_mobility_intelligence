"""Phase 3A orchestrator: OSM urban feature engineering for the 514-cell grid.

Loads the cached raw OSM layers (fetched by src.data.fetch_osm_data),
computes POI/building/road/green-space features per grid cell, merges them
onto the canonical Phase 2 grid, runs QA checks, and writes:
  - data/processed/features/osm_urban_features.parquet (+ .geojson)
  - data/processed/features/osm_feature_dictionary.csv
  - outputs/maps/osm_{poi_density,building_coverage,road_density,green_area}.png

Run from the project root:
    .venv/bin/python -m src.features.build_osm_features
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.data.fetch_osm_data import fetch_buildings, fetch_landuse, fetch_pois, fetch_road_network, get_query_polygon
from src.features import osm_feature_dictionary as feat_dict
from src.features import osm_tag_config as tags
from src.features.building_features import compute_building_features
from src.features.greenspace_features import compute_greenspace_features
from src.features.poi_features import compute_poi_features
from src.features.road_features import compute_road_features
from src.utils import config as cfg


def load_grid() -> gpd.GeoDataFrame:
    path = cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg"
    grid = gpd.read_file(path)
    assert grid.crs.to_string() == cfg.METRIC_CRS, f"expected {cfg.METRIC_CRS}, got {grid.crs}"
    assert len(grid) == 514, f"expected the canonical 514-cell V1 grid, found {len(grid)} cells"
    assert grid["grid_id"].is_unique, "grid_id must be unique"
    return grid


def _assert_all_grid_ids_present(df: pd.DataFrame, grid_ids: pd.Index, label: str) -> None:
    missing = set(grid_ids) - set(df["grid_id"])
    assert not missing, f"{label}: {len(missing)} grid cells disappeared during processing"
    assert len(df) == len(grid_ids), f"{label}: row count {len(df)} != {len(grid_ids)} grid cells"


def compute_all_features(grid: gpd.GeoDataFrame) -> tuple[pd.DataFrame, dict]:
    _, poly_ll = get_query_polygon()

    pois_raw = fetch_pois(poly_ll)
    buildings_raw = fetch_buildings(poly_ll)
    landuse_raw = fetch_landuse(poly_ll)
    G_raw = fetch_road_network(poly_ll)

    grid_ids = grid["grid_id"]

    poi_df, poi_diag = compute_poi_features(pois_raw, grid)
    _assert_all_grid_ids_present(poi_df, grid_ids, "poi_features")

    bld_df, bld_diag = compute_building_features(buildings_raw, grid)
    _assert_all_grid_ids_present(bld_df, grid_ids, "building_features")

    road_df, road_diag = compute_road_features(G_raw, grid)
    _assert_all_grid_ids_present(road_df, grid_ids, "road_features")

    green_df, green_diag = compute_greenspace_features(landuse_raw, grid)
    _assert_all_grid_ids_present(green_df, grid_ids, "greenspace_features")

    base = grid[["grid_id", "district", "land_area_m2", "geometry"]].copy()
    merged = base.merge(poi_df, on="grid_id", how="left")
    merged = merged.merge(bld_df, on="grid_id", how="left")
    merged = merged.merge(road_df, on="grid_id", how="left")
    merged = merged.merge(green_df, on="grid_id", how="left")
    _assert_all_grid_ids_present(merged, grid_ids, "final merge")
    assert merged["grid_id"].is_unique

    diagnostics = {
        "poi": poi_diag,
        "buildings": bld_diag,
        "road_network": road_diag,
        "greenspace_landuse": green_diag,
        "acquisition": {
            "n_pois_raw": len(pois_raw),
            "n_buildings_raw": len(buildings_raw),
            "n_landuse_polygons_raw": len(landuse_raw),
            "n_road_edges_directed_raw": len(G_raw.edges),
            "n_road_nodes_raw": len(G_raw.nodes),
        },
    }
    return merged, diagnostics


def run_qa(features: gpd.GeoDataFrame, diagnostics: dict) -> dict:
    numeric_cols = [
        c for c in features.columns
        if c not in ("grid_id", "district", "geometry") and pd.api.types.is_numeric_dtype(features[c])
    ]

    missing_by_feature = {c: int(features[c].isna().sum()) for c in numeric_cols if features[c].isna().any()}

    desc = features[numeric_cols].describe().T[["min", "50%", "mean", "max"]]
    desc = desc.rename(columns={"50%": "median"})
    descriptive_stats = desc.round(4).to_dict(orient="index")

    poi_by_category = {c: int(features[c].sum()) for c in tags.POI_CATEGORIES}
    pct_zero_poi = float((features["total_poi_count"] == 0).mean() * 100)

    flagged = []
    for c in numeric_cols:
        vals = features[c]
        mu, sigma = vals.mean(), vals.std()
        if sigma == 0 or np.isnan(sigma):
            continue
        z = (vals - mu) / sigma
        extreme = features.loc[z.abs() > 4, ["grid_id"]].copy()
        if len(extreme):
            extreme["feature"] = c
            extreme["value"] = vals.loc[extreme.index]
            extreme["z_score"] = z.loc[extreme.index]
            flagged.append(extreme)
    flagged_df = (
        pd.concat(flagged, ignore_index=True).sort_values("z_score", ascending=False)
        if flagged else pd.DataFrame(columns=["grid_id", "feature", "value", "z_score"])
    )

    invalid_geometries = {
        "pois_repaired": diagnostics["poi"]["invalid_geometries_repaired"],
        "buildings_repaired": diagnostics["buildings"]["invalid_geometries_repaired"],
        "landuse_repaired": diagnostics["greenspace_landuse"]["invalid_landuse_geometries_repaired"],
    }

    qa = {
        "n_grid_rows": len(features),
        "grid_id_unique": bool(features["grid_id"].is_unique),
        "total_osm_pois_downloaded": diagnostics["acquisition"]["n_pois_raw"],
        "poi_by_category": poi_by_category,
        "pct_grids_with_zero_poi": pct_zero_poi,
        "total_building_count": int(features["building_count"].sum()),
        "total_building_footprint_area_m2": float(features["building_footprint_area_m2"].sum()),
        "total_road_length_km": float(features["road_length_m"].sum() / 1000),
        "total_green_area_m2": float(features["green_area_m2"].sum()),
        "missing_values_by_feature": missing_by_feature,
        "descriptive_stats": descriptive_stats,
        "n_extreme_value_cells_flagged": len(flagged_df),
        "top_flagged_cells": flagged_df.head(20).to_dict(orient="records"),
        "duplicate_pois_removed": diagnostics["poi"]["n_duplicate_pois_removed"],
        "uncategorized_pois_dropped": diagnostics["poi"]["n_uncategorized_dropped"],
        "invalid_geometries_repaired": invalid_geometries,
        "n_cells_building_coverage_over_100pct": diagnostics["buildings"]["n_cells_with_coverage_ratio_over_100pct"],
        "landuse_entropy_computed": diagnostics["greenspace_landuse"]["landuse_entropy_computed"],
        "mean_landuse_data_coverage_pct": diagnostics["greenspace_landuse"]["mean_landuse_data_coverage_pct"],
    }
    return qa


def save_outputs(features: gpd.GeoDataFrame) -> dict:
    cfg.DATA_FEATURES.mkdir(parents=True, exist_ok=True)
    paths = {
        "parquet": cfg.DATA_FEATURES / "osm_urban_features.parquet",
        "geojson": cfg.DATA_FEATURES / "osm_urban_features.geojson",
        "feature_dictionary": cfg.DATA_FEATURES / "osm_feature_dictionary.csv",
    }
    features.to_parquet(paths["parquet"])
    features.to_crs(cfg.STORAGE_CRS).to_file(paths["geojson"], driver="GeoJSON")
    feat_dict.as_dataframe().to_csv(paths["feature_dictionary"], index=False)
    return paths


def _map_extent(districts_gdf: gpd.GeoDataFrame):
    minx, miny, maxx, maxy = districts_gdf.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    return (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)


def _plot_choropleth(features, districts_gdf, column, title, cmap, out_path, extent):
    fig, ax = plt.subplots(figsize=(10, 10))
    features.plot(column=column, cmap=cmap, ax=ax, legend=True, edgecolor="#666666", linewidth=0.1)
    districts_gdf.boundary.plot(ax=ax, linewidth=1.4, color="black", zorder=3)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_title(title)
    ax.set_axis_off()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def make_validation_maps(features: gpd.GeoDataFrame) -> dict:
    districts_gdf = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    extent = _map_extent(districts_gdf)
    cfg.OUTPUTS_MAPS.mkdir(parents=True, exist_ok=True)

    specs = [
        ("poi_density_km2", "Total POI density (per km^2)", "YlOrRd", "osm_poi_density.png"),
        ("building_coverage_ratio", "Building coverage ratio", "Oranges", "osm_building_coverage.png"),
        ("road_density_km_per_km2", "Road density (km per km^2)", "Blues", "osm_road_density.png"),
        ("green_area_ratio", "Green area ratio", "Greens", "osm_green_area.png"),
    ]
    paths = {}
    for column, title, cmap, filename in specs:
        out_path = cfg.OUTPUTS_MAPS / filename
        _plot_choropleth(features, districts_gdf, column, title, cmap, out_path, extent)
        paths[column] = out_path
    return paths


def main() -> None:
    print("=" * 72)
    print("Istanbul Urban Mobility Intelligence — Phase 3A: OSM Urban Features")
    print("=" * 72)

    grid = load_grid()
    features, diagnostics = compute_all_features(grid)
    qa = run_qa(features, diagnostics)

    output_paths = save_outputs(features)
    map_paths = make_validation_maps(features)

    print("\n--- ACQUISITION SUMMARY ---")
    print(json.dumps(diagnostics["acquisition"], indent=2))

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

    with open(cfg.DATA_FEATURES / "osm_features_qa_report.json", "w", encoding="utf-8") as f:
        json.dump({"diagnostics": diagnostics, "qa": qa}, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nFull QA report saved -> {cfg.DATA_FEATURES / 'osm_features_qa_report.json'}")


if __name__ == "__main__":
    main()
