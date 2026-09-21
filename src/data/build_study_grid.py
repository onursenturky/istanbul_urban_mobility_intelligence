"""Phase 1+2 spatial foundation: pilot study area + 500m grid.

Districts: Kadıköy, Üsküdar, Maltepe. Fetches OSM administrative boundary
relations (cached, never modified after download), builds a dissolved study
area and a 500m x 500m grid clipped to it, assigns each retained cell to a
district by largest spatial overlap, and writes validation outputs.

Run from the project root:
    .venv/bin/python -m src.data.build_study_grid
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
import pandas as pd
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box
from shapely.ops import unary_union

from src.utils import config as cfg


def _coerce_polygonal(geom):
    """make_valid() can return a GeometryCollection on self-intersecting
    input; keep only the polygonal parts so downstream area/overlay ops
    don't silently pick up stray points/lines."""
    if geom is None or geom.is_empty or isinstance(geom, (Polygon, MultiPolygon)):
        return geom
    if isinstance(geom, GeometryCollection):
        polys = [g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))]
        return unary_union(polys) if polys else Polygon()
    return geom


def validate_geometries(gdf: gpd.GeoDataFrame, label: str) -> tuple[gpd.GeoDataFrame, int, int]:
    invalid_before = int((~gdf.geometry.is_valid).sum())
    if invalid_before:
        print(f"[validate:{label}] {invalid_before} invalid geometr(y/ies) found, repairing with make_valid()")
        gdf = gdf.set_geometry(gdf.geometry.make_valid().apply(_coerce_polygonal))
    invalid_after = int((~gdf.geometry.is_valid).sum())
    empty_count = int(gdf.geometry.is_empty.sum())
    print(
        f"[validate:{label}] invalid_before={invalid_before} invalid_after={invalid_after} "
        f"empty={empty_count} total={len(gdf)}"
    )
    return gdf, invalid_before, invalid_after


def fetch_raw_boundaries(raw_filename: str = "osm_district_boundaries_raw.geojson") -> gpd.GeoDataFrame:
    """`raw_filename` defaults to the pilot's original cache name; a citywide
    run passes a different name since DATA_RAW is shared between pilot and
    citywide configs (GTFS/population/cycling raw data is meant to be
    reused) but the district SET differs, so the cached boundary fetch must
    not collide."""
    raw_dir = cfg.DATA_RAW / "boundaries"
    raw_path = raw_dir / raw_filename
    meta_path = raw_dir / raw_filename.replace(".geojson", ".meta.json")

    if raw_path.exists():
        print(f"[cache] loading raw boundaries from {raw_path} (not re-fetched)")
        return gpd.read_file(raw_path)

    print("[fetch] querying OSM (Nominatim /lookup via osmnx) for district relations...")
    names = list(cfg.DISTRICTS.keys())
    osm_ids = [f"R{v}" for v in cfg.DISTRICTS.values()]
    gdf = ox.geocode_to_gdf(osm_ids, by_osmid=True)
    if len(gdf) != len(names):
        raise RuntimeError(
            f"Expected {len(names)} boundary relations, got {len(gdf)} back from OSM. "
            "Aborting rather than silently proceeding with a mismatched fetch."
        )
    gdf = gdf.reset_index(drop=True)
    # osmnx.geocode_to_gdf preserves input order for by_osmid lookups (verified
    # empirically); assign our canonical district names positionally and cross-check.
    gdf["district"] = names
    for expected, returned in zip(names, gdf["name"]):
        if returned != expected:
            print(f"[WARN] OSM name mismatch: requested '{expected}', OSM returned '{returned}'")

    raw_dir.mkdir(parents=True, exist_ok=True)
    gdf.to_file(raw_path, driver="GeoJSON")
    meta_path.write_text(
        json.dumps(
            {
                "source": cfg.BOUNDARY_SOURCE,
                "license": cfg.BOUNDARY_LICENSE,
                "retrieved_date": cfg.BOUNDARY_RETRIEVAL_DATE,
                "fetch_method": "osmnx.geocode_to_gdf(by_osmid=True) -> Nominatim /lookup",
                "osm_relations": cfg.DISTRICTS,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"[cache] wrote raw boundaries -> {raw_path}")
    return gdf


def prepare_districts(raw_gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict]:
    gdf, inv_raw_before, inv_raw_after = validate_geometries(raw_gdf.copy(), "districts_raw_4326")
    gdf = gdf.to_crs(cfg.METRIC_CRS)
    gdf, inv_proj_before, inv_proj_after = validate_geometries(gdf, "districts_after_reprojection")

    gdf["osm_relation_id"] = gdf["osm_id"].astype(int)
    gdf["source"] = cfg.BOUNDARY_SOURCE
    gdf["license"] = cfg.BOUNDARY_LICENSE
    gdf["retrieved_date"] = cfg.BOUNDARY_RETRIEVAL_DATE
    gdf["area_m2"] = gdf.geometry.area

    gdf = gdf[["district", "osm_relation_id", "source", "license", "retrieved_date", "area_m2", "geometry"]]
    gdf = gdf.reset_index(drop=True)

    validation = {
        "invalid_raw_before_repair": inv_raw_before,
        "invalid_raw_after_repair": inv_raw_after,
        "invalid_reprojected_before_repair": inv_proj_before,
        "invalid_reprojected_after_repair": inv_proj_after,
    }
    return gdf, validation


def build_study_area(districts_gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict]:
    dissolved = districts_gdf.geometry.union_all()
    gdf = gpd.GeoDataFrame(
        {
            "district_count": [len(districts_gdf)],
            "districts": [", ".join(sorted(districts_gdf["district"]))],
            "area_m2": [dissolved.area],
        },
        geometry=[dissolved],
        crs=cfg.METRIC_CRS,
    )
    gdf, inv_before, inv_after = validate_geometries(gdf, "study_area_dissolved")
    return gdf, {"invalid_dissolved_before_repair": inv_before, "invalid_dissolved_after_repair": inv_after}


def build_grid(study_area_geom, resolution: int) -> gpd.GeoDataFrame:
    minx, miny, maxx, maxy = study_area_geom.bounds
    minx = np.floor(minx / resolution) * resolution
    miny = np.floor(miny / resolution) * resolution
    xs = np.arange(minx, maxx + resolution, resolution)
    ys = np.arange(miny, maxy + resolution, resolution)
    cells = [box(x, y, x + resolution, y + resolution) for x in xs for y in ys]
    grid = gpd.GeoDataFrame({"geometry": cells}, crs=cfg.METRIC_CRS)
    print(f"[grid] bounding-box fishnet generated: {len(grid)} candidate {resolution}m cells")
    return grid


def clip_and_filter_grid(grid: gpd.GeoDataFrame, study_area_geom, threshold: float) -> gpd.GeoDataFrame:
    grid = grid.copy()
    grid["cell_area_m2"] = grid.geometry.area
    grid["geometry"] = grid.geometry.intersection(study_area_geom)
    grid["land_area_m2"] = grid.geometry.area
    grid["pct_in_study_area"] = grid["land_area_m2"] / grid["cell_area_m2"] * 100

    before = len(grid)
    grid = grid[(grid["pct_in_study_area"] >= threshold * 100) & (~grid.geometry.is_empty)].copy()
    print(
        f"[grid] {before} candidate cells -> {len(grid)} retained "
        f"at >={threshold:.0%} land-intersection threshold"
    )
    return grid.reset_index(drop=True)


def assign_district(
    grid: gpd.GeoDataFrame, districts_gdf: gpd.GeoDataFrame, ambiguous_ratio: float
) -> gpd.GeoDataFrame:
    overlay = gpd.overlay(
        grid[["grid_id", "geometry"]],
        districts_gdf[["district", "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    overlay["overlap_area_m2"] = overlay.geometry.area
    overlay = overlay[overlay["overlap_area_m2"] > 0]
    overlay["rank"] = overlay.groupby("grid_id")["overlap_area_m2"].rank(method="first", ascending=False)

    primary = overlay[overlay["rank"] == 1][["grid_id", "district", "overlap_area_m2"]].rename(
        columns={"overlap_area_m2": "district_overlap_m2"}
    )
    secondary = overlay[overlay["rank"] == 2][["grid_id", "district", "overlap_area_m2"]].rename(
        columns={"district": "second_district", "overlap_area_m2": "second_overlap_m2"}
    )
    total_overlap = overlay.groupby("grid_id")["overlap_area_m2"].sum().rename("total_district_overlap_m2")

    grid = grid.merge(primary, on="grid_id", how="left")
    grid = grid.merge(secondary, on="grid_id", how="left")
    grid = grid.merge(total_overlap, on="grid_id", how="left")

    grid["second_overlap_m2"] = grid["second_overlap_m2"].fillna(0.0)
    grid["district_overlap_pct"] = grid["district_overlap_m2"] / grid["land_area_m2"] * 100
    grid["second_overlap_pct"] = grid["second_overlap_m2"] / grid["land_area_m2"] * 100
    grid["ambiguous_district"] = (grid["second_overlap_m2"] > 0) & (
        grid["second_overlap_m2"] / grid["district_overlap_m2"] >= ambiguous_ratio
    )
    # diagnostic: adjacent OSM district polygons should tile the union with no
    # gap/overlap; a large mismatch here flags a boundary topology issue.
    grid["overlap_vs_land_diff_m2"] = grid["land_area_m2"] - grid["total_district_overlap_m2"]

    grid = grid.drop(columns=["district_overlap_m2", "total_district_overlap_m2"])
    return grid


def save_outputs(
    districts_gdf: gpd.GeoDataFrame, study_area_gdf: gpd.GeoDataFrame, grid_gdf: gpd.GeoDataFrame
) -> dict:
    cfg.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

    final_grid_cols = [
        "grid_id",
        "district",
        "cell_area_m2",
        "land_area_m2",
        "pct_in_study_area",
        "district_overlap_pct",
        "ambiguous_district",
        "second_district",
        "second_overlap_pct",
        "overlap_vs_land_diff_m2",
        "geometry",
    ]
    grid_gdf = grid_gdf[final_grid_cols]

    paths = {
        "districts": cfg.DATA_PROCESSED / "districts.geojson",
        "study_area": cfg.DATA_PROCESSED / "study_area.geojson",
        "grid": cfg.DATA_PROCESSED / "mobility_grid_500m.geojson",
    }
    # GeoJSON (RFC 7946) is WGS84 by convention; all metric attributes above
    # were already computed in cfg.METRIC_CRS before this reprojection, so
    # reprojecting geometry here does not change any area/percentage value.
    districts_gdf.to_crs(cfg.STORAGE_CRS).to_file(paths["districts"], driver="GeoJSON")
    study_area_gdf.to_crs(cfg.STORAGE_CRS).to_file(paths["study_area"], driver="GeoJSON")
    grid_gdf.to_crs(cfg.STORAGE_CRS).to_file(paths["grid"], driver="GeoJSON")

    # Metric-CRS copies for Phase 3+ feature engineering (avoids re-reprojecting
    # a 500m grid on every downstream join).
    districts_gdf.to_file(cfg.DATA_PROCESSED / "districts_metric.gpkg", driver="GPKG")
    study_area_gdf.to_file(cfg.DATA_PROCESSED / "study_area_metric.gpkg", driver="GPKG")
    grid_gdf.to_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg", driver="GPKG")

    return paths


def make_validation_map(
    districts_gdf: gpd.GeoDataFrame, study_area_gdf: gpd.GeoDataFrame, grid_gdf: gpd.GeoDataFrame
):
    fig, ax = plt.subplots(figsize=(11, 11))
    grid_gdf.boundary.plot(ax=ax, linewidth=0.25, color="#888888", zorder=1)
    districts_gdf.plot(
        ax=ax, column="district", cmap="Set2", alpha=0.35, edgecolor="none", zorder=2, legend=True
    )
    districts_gdf.boundary.plot(ax=ax, linewidth=1.6, color="black", zorder=3)
    study_area_gdf.boundary.plot(ax=ax, linewidth=2.5, color="red", zorder=4)
    ax.set_title(
        f"Istanbul Pilot Study Area — Kadıköy, Üsküdar, Maltepe\n"
        f"{cfg.GRID_RESOLUTION_M}m grid, n={len(grid_gdf)} cells, {cfg.METRIC_CRS}"
    )
    ax.set_axis_off()

    cfg.OUTPUTS_MAPS.mkdir(parents=True, exist_ok=True)
    out_path = cfg.OUTPUTS_MAPS / "study_area_validation.png"
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_path


def write_metadata(diagnostics: dict, paths: dict) -> None:
    meta = {
        "pipeline": "src/data/build_study_grid.py",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "boundary_source": cfg.BOUNDARY_SOURCE,
        "boundary_license": cfg.BOUNDARY_LICENSE,
        "boundary_retrieval_date": cfg.BOUNDARY_RETRIEVAL_DATE,
        "osm_relations": cfg.DISTRICTS,
        "metric_crs": cfg.METRIC_CRS,
        "storage_crs": cfg.STORAGE_CRS,
        "grid_resolution_m": cfg.GRID_RESOLUTION_M,
        "intersection_threshold": cfg.INTERSECTION_THRESHOLD,
        "ambiguous_district_ratio": cfg.AMBIGUOUS_DISTRICT_RATIO,
        "diagnostics": diagnostics,
        "output_files": {k: str(v) for k, v in paths.items()},
    }
    path = cfg.DATA_PROCESSED / "pipeline_metadata.json"
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["metadata"] = path


def main(raw_boundary_filename: str = "osm_district_boundaries_raw.geojson") -> None:
    print("=" * 72)
    print("Istanbul Urban Mobility Intelligence — Phase 1+2: Spatial Foundation")
    print(f"Districts ({len(cfg.DISTRICTS)}): {', '.join(cfg.DISTRICTS)}")
    print("=" * 72)

    raw_gdf = fetch_raw_boundaries(raw_boundary_filename)
    districts_gdf, district_validation = prepare_districts(raw_gdf)
    study_area_gdf, study_area_validation = build_study_area(districts_gdf)
    study_area_geom = study_area_gdf.geometry.iloc[0]

    grid = build_grid(study_area_geom, cfg.GRID_RESOLUTION_M)
    n_before_filter = len(grid)
    grid = clip_and_filter_grid(grid, study_area_geom, cfg.INTERSECTION_THRESHOLD)
    grid, grid_inv_before, grid_inv_after = validate_geometries(grid, "grid_after_clip")

    grid["grid_id"] = [f"GRID_{i:05d}" for i in range(1, len(grid) + 1)]
    assert grid["grid_id"].is_unique, "grid_id uniqueness check failed"

    grid = assign_district(grid, districts_gdf, cfg.AMBIGUOUS_DISTRICT_RATIO)

    paths = save_outputs(districts_gdf, study_area_gdf, grid)
    paths["validation_map"] = make_validation_map(districts_gdf, study_area_gdf, grid)

    cells_per_district = {
        (str(k) if pd.notna(k) else "unassigned"): int(v)
        for k, v in grid["district"].value_counts(dropna=False).items()
    }
    total_study_area_m2 = float(study_area_gdf["area_m2"].iloc[0])
    total_retained_land_m2 = float(grid["land_area_m2"].sum())
    grid_coverage_pct = total_retained_land_m2 / total_study_area_m2 * 100
    n_ambiguous = int(grid["ambiguous_district"].sum())
    n_unassigned = int(grid["district"].isna().sum())
    topology_gap_cells = grid[(grid["overlap_vs_land_diff_m2"].abs() / grid["land_area_m2"]) > 0.01]

    diagnostics = {
        "metric_crs": cfg.METRIC_CRS,
        "storage_crs_for_geojson": cfg.STORAGE_CRS,
        "n_grid_cells_before_threshold": n_before_filter,
        "n_grid_cells_retained": len(grid),
        "cells_per_district": cells_per_district,
        "total_study_area_m2": total_study_area_m2,
        "total_study_area_km2": total_study_area_m2 / 1e6,
        "total_retained_land_area_m2": total_retained_land_m2,
        "total_retained_land_area_km2": total_retained_land_m2 / 1e6,
        "grid_coverage_pct": grid_coverage_pct,
        "invalid_geometries": {
            "districts": district_validation,
            "study_area_dissolved": study_area_validation,
            "grid_after_clip_before_repair": grid_inv_before,
            "grid_after_clip_after_repair": grid_inv_after,
        },
        "n_ambiguous_district_cells": n_ambiguous,
        "n_unassigned_cells": n_unassigned,
        "n_topology_gap_cells_over_1pct": int(len(topology_gap_cells)),
    }
    write_metadata(diagnostics, paths)

    print("\n--- DIAGNOSTICS ---")
    print(json.dumps(diagnostics, indent=2, ensure_ascii=False))

    print("\n--- OUTPUT FILES ---")
    for k, v in paths.items():
        print(f"  {k}: {v}")

    flags = []
    if district_validation["invalid_raw_after_repair"] or district_validation["invalid_reprojected_after_repair"]:
        flags.append("Unrepaired invalid district geometries remain after make_valid().")
    if study_area_validation["invalid_dissolved_after_repair"]:
        flags.append("Unrepaired invalid study-area geometry remains after make_valid().")
    if grid_inv_after:
        flags.append("Unrepaired invalid grid geometries remain after clipping.")
    if grid_coverage_pct < 95:
        flags.append(f"Grid coverage is only {grid_coverage_pct:.1f}% of study area — investigate threshold/bounds.")
    if n_unassigned:
        flags.append(f"{n_unassigned} retained cells have no overlapping district despite passing the land threshold.")
    if len(topology_gap_cells) > 0:
        flags.append(
            f"{len(topology_gap_cells)} cells show >1% mismatch between land area and summed district "
            "overlaps — possible gap/overlap between adjacent OSM district polygons."
        )
    for d in cfg.DISTRICTS:
        if cells_per_district.get(d, 0) == 0:
            flags.append(f"District '{d}' received zero grid cells.")

    print("\n--- FLAGS ---")
    if flags:
        for f in flags:
            print(f"  [FLAG] {f}")
    else:
        print("  None.")


if __name__ == "__main__":
    main()
