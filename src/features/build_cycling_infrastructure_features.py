"""Phase 3E orchestrator: cycling & micromobility infrastructure features.

Loads cached İBB (authoritative) and OSM (complementary) cycling data,
deduplicates overlapping representations, computes per-cell infrastructure
length/density/distance/parking features, merges onto the canonical Phase 2
grid, verifies Phase 1-3D features are untouched, runs QA, and writes:
  - data/processed/features/cycling_infrastructure_features.parquet
  - data/processed/features/urban_mobility_features.parquet (+ Phase 3E)
  - data/processed/features/cycling_infrastructure_feature_dictionary.csv
  - data/processed/features/cycling_infrastructure_qa_report.json
  - outputs/maps/cycling_{total_density,protected_density,distance}.png

Shared-mobility data is handled entirely separately by
src.data.fetch_shared_mobility_data and never read here.

Run from the project root:
    .venv/bin/python -m src.features.build_cycling_infrastructure_features
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
import pandas as pd

from src.data.fetch_cycling_infrastructure_data import (
    fetch_ibb_bike_paths,
    fetch_ibb_parking,
    fetch_osm_bicycle_parking_for_completeness_check,
    fetch_osm_cycling_ways,
)
from src.features import cycling_infrastructure_feature_dictionary as feat_dict
from src.features.cycling_infrastructure_features import (
    build_combined_network,
    compute_cycling_features,
    compute_network_connectivity,
    compute_pct_road_with_cycle_infra,
    load_ibb_parking,
)
from src.utils import config as cfg


def load_grid() -> gpd.GeoDataFrame:
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 514, f"expected the canonical 514-cell V1 grid, found {len(grid)}"
    assert grid["grid_id"].is_unique
    return grid


def clip_network_to_study_area(network: gpd.GeoDataFrame, study_area_geom) -> gpd.GeoDataFrame:
    """İBB's bike-paths dataset covers all 39 Istanbul districts; without
    this clip, network-level diagnostics (total length, length by category)
    would report city-wide totals rather than the pilot study area's. Per-
    cell features are unaffected either way (each cell's own intersection
    already restricts to itself), but reporting must reflect the study
    area, not the whole city."""
    clipped = network.copy()
    clipped["geometry"] = clipped.geometry.intersection(study_area_geom)
    clipped = clipped[~clipped.geometry.is_empty].copy()
    clipped["length_m"] = clipped.geometry.length
    return clipped[clipped["length_m"] > 0].reset_index(drop=True)


def load_existing_combined() -> gpd.GeoDataFrame:
    path = cfg.DATA_FEATURES / "urban_mobility_features.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run Phase 3A-3D first.")
    return gpd.read_parquet(path)


def _assert_all_grid_ids_present(df: pd.DataFrame, grid_ids: pd.Index, label: str) -> None:
    missing = set(grid_ids) - set(df["grid_id"])
    assert not missing, f"{label}: {len(missing)} grid cells disappeared during processing"
    assert len(df) == len(grid_ids), f"{label}: row count {len(df)} != {len(grid_ids)} grid cells"


def get_undirected_road_edges() -> gpd.GeoDataFrame:
    G = ox.load_graphml(cfg.DATA_RAW / "osm" / "osm_road_network_raw.graphml")
    G_proj = ox.project_graph(G, to_crs=cfg.METRIC_CRS)
    G_u = ox.convert.to_undirected(G_proj)
    return ox.graph_to_gdfs(G_u, nodes=False, edges=True).reset_index()


def osm_parking_completeness_check(ibb_parking: gpd.GeoDataFrame, osm_parking_path) -> dict:
    osm_parking = gpd.read_file(osm_parking_path)
    if len(osm_parking) == 0:
        return {"n_ibb": len(ibb_parking), "n_osm": 0, "n_osm_near_an_ibb_point": 0}
    osm_parking_m = osm_parking.to_crs(cfg.METRIC_CRS)
    ibb_buffer = ibb_parking.geometry.buffer(30).union_all()
    n_near = int(osm_parking_m.geometry.within(ibb_buffer).sum())
    return {
        "n_ibb_bicycle_parking": len(ibb_parking),
        "n_osm_bicycle_parking_in_buffer": len(osm_parking_m),
        "n_osm_points_within_30m_of_an_ibb_point": n_near,
        "note": "OSM used only as a completeness cross-check; not merged into bicycle_parking_count.",
    }


def run_qa(features: gpd.GeoDataFrame, network_diag: dict, connectivity: dict, parking_check: dict) -> dict:
    numeric_cols = [
        c for c in features.columns
        if c not in ("grid_id", "district", "geometry") and pd.api.types.is_numeric_dtype(features[c])
    ]
    desc = features[numeric_cols].describe().T[["min", "50%", "mean", "max"]].rename(columns={"50%": "median"})
    descriptive_stats = desc.round(4).to_dict(orient="index")

    missing_by_feature = {c: int(features[c].isna().sum()) for c in numeric_cols if features[c].isna().any()}

    flagged = []
    for c in numeric_cols:
        vals = features[c].dropna()
        mu, sigma = vals.mean(), vals.std()
        if sigma == 0 or np.isnan(sigma):
            continue
        z = (features[c] - mu) / sigma
        extreme = features.loc[z.abs() > 4, ["grid_id"]].copy()
        if len(extreme):
            extreme["feature"] = c
            extreme["value"] = features[c].loc[extreme.index]
            flagged.append(extreme)
    flagged_df = pd.concat(flagged, ignore_index=True) if flagged else pd.DataFrame(columns=["grid_id", "feature", "value"])

    qa = {
        "network_diagnostics": network_diag,
        "network_connectivity_study_area_wide": connectivity,
        "osm_bicycle_parking_completeness_check": parking_check,
        "n_grid_rows": len(features),
        "grid_id_unique": bool(features["grid_id"].is_unique),
        "total_bicycle_parking_count": int(features["bicycle_parking_count"].sum()),
        "pct_grids_with_zero_cycle_infrastructure": float((features["cycle_infrastructure_length_km"] == 0).mean() * 100),
        "pct_grids_with_zero_protected_cycleway": float((features["protected_cycleway_length_km"] == 0).mean() * 100),
        "missing_values_by_feature": missing_by_feature,
        "descriptive_stats": descriptive_stats,
        "n_extreme_value_cells_flagged": len(flagged_df),
        "top_flagged_cells": flagged_df.head(20).to_dict(orient="records"),
    }
    return qa


def save_outputs(features: gpd.GeoDataFrame, combined: gpd.GeoDataFrame) -> dict:
    cfg.DATA_FEATURES.mkdir(parents=True, exist_ok=True)
    paths = {
        "cycling_parquet": cfg.DATA_FEATURES / "cycling_infrastructure_features.parquet",
        "combined_parquet": cfg.DATA_FEATURES / "urban_mobility_features.parquet",
        "feature_dictionary": cfg.DATA_FEATURES / "cycling_infrastructure_feature_dictionary.csv",
    }
    features.to_parquet(paths["cycling_parquet"])
    combined.to_parquet(paths["combined_parquet"])
    feat_dict.as_dataframe().to_csv(paths["feature_dictionary"], index=False)
    return paths


def _map_extent(districts_gdf: gpd.GeoDataFrame):
    minx, miny, maxx, maxy = districts_gdf.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    return (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)


def make_validation_maps(combined: gpd.GeoDataFrame, network: gpd.GeoDataFrame) -> dict:
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
    combined.plot(column="cycle_infrastructure_density_km_per_km2", cmap="Greens", ax=ax, legend=True, edgecolor="#666666", linewidth=0.1)
    if len(network):
        network.plot(ax=ax, color="darkgreen", linewidth=1.2, zorder=4)
    _base(ax, "Total cycling infrastructure density (km/km^2)\n(underlying geometries overlaid)")
    out = cfg.OUTPUTS_MAPS / "cycling_total_density.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    paths["total_density"] = out

    fig, ax = plt.subplots(figsize=(10, 10))
    combined.plot(column="protected_cycleway_density_km_per_km2", cmap="Blues", ax=ax, legend=True, edgecolor="#666666", linewidth=0.1)
    _base(ax, "Protected/separated cycleway density (km/km^2)")
    out = cfg.OUTPUTS_MAPS / "cycling_protected_density.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    paths["protected_density"] = out

    fig, ax = plt.subplots(figsize=(10, 10))
    combined.plot(column="distance_to_nearest_cycle_infrastructure_m", cmap="OrRd_r", ax=ax, legend=True, edgecolor="#666666", linewidth=0.1)
    _base(ax, "Distance to nearest cycling infrastructure (m)")
    out = cfg.OUTPUTS_MAPS / "cycling_distance.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    paths["distance"] = out

    return paths


def main() -> None:
    print("=" * 72)
    print("Istanbul Urban Mobility Intelligence — Phase 3E: Cycling & Micromobility Infrastructure")
    print("=" * 72)

    grid = load_grid()
    existing_combined = load_existing_combined()
    grid_ids = grid["grid_id"]

    ibb_path = fetch_ibb_bike_paths()
    parking_path = fetch_ibb_parking()
    osm_path = fetch_osm_cycling_ways()
    osm_parking_path = fetch_osm_bicycle_parking_for_completeness_check()

    study_area_geom = gpd.read_file(cfg.DATA_PROCESSED / "study_area_metric.gpkg").geometry.iloc[0]
    network_full, network_diag = build_combined_network(ibb_path, osm_path)
    network = clip_network_to_study_area(network_full, study_area_geom)
    network_diag["study_area_clip"] = {
        "n_geometries_before_clip": len(network_full),
        "n_geometries_after_clip": len(network),
        "total_length_km_within_study_area": float(network["length_m"].sum() / 1000),
        "length_km_by_category_within_study_area": (network.groupby("category")["length_m"].sum() / 1000).round(3).to_dict(),
        "length_km_by_source_within_study_area": (network.groupby("source")["length_m"].sum() / 1000).round(3).to_dict(),
        "note": "network_diag's top-level total_length_km/length_km_by_* (pre-clip) reflect İBB's "
                "city-wide dataset before restricting to this study area; the study_area_clip fields "
                "here are the correct within-study-area totals.",
    }
    parking = load_ibb_parking(parking_path)

    cycling_features, feat_diag = compute_cycling_features(network, parking, grid)
    _assert_all_grid_ids_present(cycling_features, grid_ids, "cycling_features")

    road_edges = get_undirected_road_edges()
    pct_road_df = compute_pct_road_with_cycle_infra(network, road_edges, grid)
    _assert_all_grid_ids_present(pct_road_df, grid_ids, "pct_road_with_cycle_infra")

    cycling_features = cycling_features.merge(pct_road_df, on="grid_id", how="left")
    assert cycling_features["grid_id"].is_unique

    connectivity = compute_network_connectivity(network)
    parking_check = osm_parking_completeness_check(parking, osm_parking_path)

    qa = run_qa(
        grid[["grid_id"]].merge(cycling_features, on="grid_id"), network_diag, connectivity, parking_check
    )

    base = grid[["grid_id", "district", "land_area_m2", "geometry"]]
    cycling_gdf = gpd.GeoDataFrame(base.merge(cycling_features, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)

    # Idempotency: if this script already ran once, urban_mobility_features.parquet
    # already carries these exact Phase 3E column names — drop the old copies
    # before merging so re-running recomputes them cleanly rather than
    # colliding into pandas' _x/_y suffixes. Every other (Phase 1-3D) column
    # is left untouched, and prior_cols_for_check captures that pre-drop set
    # for the unchanged-features assertion below.
    prior_cols_for_check = [c for c in existing_combined.columns if c not in ("grid_id", "district", "land_area_m2", "geometry")]
    new_feature_cols = [c for c in cycling_features.columns if c != "grid_id"]
    existing_base = existing_combined.drop(columns=[c for c in new_feature_cols if c in existing_combined.columns])
    prior_cols_for_check = [c for c in prior_cols_for_check if c not in new_feature_cols]

    combined = existing_base.merge(cycling_features, on="grid_id", how="left", validate="one_to_one")
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=cfg.METRIC_CRS)

    unchanged = combined.set_index("grid_id")[prior_cols_for_check].sort_index().equals(
        existing_combined.set_index("grid_id")[prior_cols_for_check].sort_index()
    )
    assert unchanged, "Phase 1-3D features changed during the Phase 3E merge — aborting."
    assert len(combined) == 514 and combined["grid_id"].is_unique
    qa["prior_features_unchanged"] = bool(unchanged)

    output_paths = save_outputs(cycling_gdf, combined)
    map_paths = make_validation_maps(combined, network)

    print("\n--- NETWORK DEDUPLICATION & CATEGORY SUMMARY ---")
    print(json.dumps(network_diag, indent=2, ensure_ascii=False, default=str))

    print("\n--- CONNECTIVITY (study-area-wide) ---")
    print(json.dumps(connectivity, indent=2))

    print("\n--- OSM PARKING COMPLETENESS CHECK ---")
    print(json.dumps(parking_check, indent=2))

    print("\n--- QA REPORT ---")
    qa_printable = {k: v for k, v in qa.items() if k not in ("descriptive_stats", "top_flagged_cells")}
    print(json.dumps(qa_printable, indent=2, default=str))
    print("\ndescriptive_stats:", json.dumps(qa["descriptive_stats"], indent=2))
    print("\ntop_flagged_cells:", json.dumps(qa["top_flagged_cells"], indent=2, default=str))

    print("\n--- OUTPUT FILES ---")
    for k, v in output_paths.items():
        print(f"  {k}: {v}")
    for k, v in map_paths.items():
        print(f"  map[{k}]: {v}")

    with open(cfg.DATA_FEATURES / "cycling_infrastructure_qa_report.json", "w", encoding="utf-8") as f:
        json.dump(qa, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nFull QA report saved -> {cfg.DATA_FEATURES / 'cycling_infrastructure_qa_report.json'}")


if __name__ == "__main__":
    main()
