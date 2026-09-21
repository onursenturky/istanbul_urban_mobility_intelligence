"""Phase 7A: citywide road-grade features, previously deferred (0/39 roads).

Acquisition-method change ONLY. src.features.road_grade_features.prepare_road_edges
takes a graph G solely to reach `ox.project_graph -> to_undirected ->
graph_to_gdfs`, i.e. to obtain a plain, non-direction-duplicated edges
GeoDataFrame with a `geometry` column in the metric CRS. The PBF-derived
road "lines" layer (data/raw/osm/pbf/road_network_extract.osm.pbf, already
loaded and validated in build_road_features_citywide.py -- one row per OSM
way, no directional duplication) is exactly that, so this module ports
prepare_road_edges' logic AFTER that point verbatim (length filter,
bilinear DEM sampling at each segment's endpoints, grade_pct calculation)
rather than constructing an OSMnx graph. compute_road_grade_features itself
is reused UNMODIFIED (it never took a graph in the first place).

Same cached Copernicus GLO-30 DEM tiles already fetched for
build_terrain_features_citywide.py (data/raw/dem/) are reused unchanged --
no re-fetch.

Outputs:
  data/processed/citywide/features/road_grade_features_citywide.parquet
  data/processed/citywide/qa/road_grade_qa_citywide.json
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.build_road_features_citywide import load_road_lines
from src.citywide.build_terrain_features_citywide import citywide_tiles_needed, fetch_citywide_dem_tiles
from src.features.road_grade_features import _sample_bilinear, compute_road_grade_features
from src.features.terrain_features import load_and_reproject_dem
from src.utils import config as cfg


def load_citywide_grid() -> gpd.GeoDataFrame:
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 22322, f"expected the frozen citywide grid (22,322 cells), found {len(grid)}"
    assert grid["grid_id"].is_unique
    return grid


def prepare_road_edges_from_pbf(edges: gpd.GeoDataFrame, elevation: np.ndarray, transform) -> tuple[gpd.GeoDataFrame, dict]:
    """Verbatim port of road_grade_features.prepare_road_edges, starting
    from the point where that function has a plain edges GeoDataFrame."""
    edges = edges.copy()
    edges["length_m"] = edges.geometry.length

    n_raw = len(edges)
    too_short = edges["length_m"] < cfg.MIN_ROAD_SEGMENT_LENGTH_M
    n_excluded_short = int(too_short.sum())
    edges = edges[~too_short].copy()

    start_pts = edges.geometry.apply(lambda g: g.coords[0])
    end_pts = edges.geometry.apply(lambda g: g.coords[-1])
    elev_start = _sample_bilinear(elevation, transform, [p[0] for p in start_pts], [p[1] for p in start_pts])
    elev_end = _sample_bilinear(elevation, transform, [p[0] for p in end_pts], [p[1] for p in end_pts])

    valid_elev = np.isfinite(elev_start) & np.isfinite(elev_end)
    n_excluded_invalid_elev = int((~valid_elev).sum())
    edges = edges[valid_elev].copy()
    elev_start, elev_end = elev_start[valid_elev], elev_end[valid_elev]

    edges["grade_pct"] = np.abs(elev_end - elev_start) / edges["length_m"].to_numpy() * 100
    n_suspicious = int((edges["grade_pct"] > cfg.ROAD_GRADE_SUSPICIOUS_THRESHOLD_PCT).sum())

    diagnostics = {
        "n_edges_total": n_raw,
        "n_excluded_short_segments": n_excluded_short,
        "n_excluded_invalid_elevation": n_excluded_invalid_elev,
        "n_edges_used_for_grade": len(edges),
        "n_suspicious_grade_segments_over_threshold": n_suspicious,
        "suspicious_threshold_pct": cfg.ROAD_GRADE_SUSPICIOUS_THRESHOLD_PCT,
        "min_segment_length_m": cfg.MIN_ROAD_SEGMENT_LENGTH_M,
    }
    return edges[["geometry", "length_m", "grade_pct"]], diagnostics


def main() -> None:
    print("=" * 72)
    print("Citywide road-grade features (39 districts, 22,322-cell grid, PBF-derived)")
    print("=" * 72)

    grid = load_citywide_grid()
    study_area = gpd.read_file(cfg.DATA_PROCESSED / "study_area_metric.gpkg").geometry.iloc[0]

    print("\n[1/4] DEM tiles (reusing cache from Phase citywide terrain)...")
    tiles_needed = citywide_tiles_needed(study_area)
    tile_paths = fetch_citywide_dem_tiles(study_area)
    elevation, transform, dem_diag = load_and_reproject_dem(tile_paths, study_area)
    print(f"  tiles: {tiles_needed}")
    print(f"  reprojected shape: {dem_diag['reprojected_shape']}, valid pixels: {dem_diag['n_valid_pixels']:,}")

    print("\n[2/4] Road edges (PBF-derived lines layer, reused from build_road_features_citywide)...")
    edges, lines_diag = load_road_lines()
    print(f"  {lines_diag}")

    print("\n[3/4] Grade computation (bilinear DEM sampling at segment endpoints)...")
    grade_edges, prep_diag = prepare_road_edges_from_pbf(edges, elevation, transform)
    print(f"  {prep_diag}")

    grade_features = compute_road_grade_features(grade_edges, grid)
    missing = set(grid["grid_id"]) - set(grade_features["grid_id"])
    assert not missing, f"{len(missing)} grid cells disappeared during road-grade processing"
    assert len(grade_features) == 22322 and grade_features["grid_id"].is_unique

    base = grid[["grid_id", "district", "geometry"]]
    grade_gdf = gpd.GeoDataFrame(base.merge(grade_features, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)

    print("\n[4/4] QA...")
    n_districts_present = grade_gdf["district"].nunique()
    n_cells_no_grade_sample = int((grade_gdf["road_grade_sample_length_m"] == 0).sum())
    no_sample_by_district = grade_gdf[grade_gdf["road_grade_sample_length_m"] == 0]["district"].value_counts().to_dict()

    grade_cols = ["mean_absolute_road_grade_pct", "median_absolute_road_grade_pct", "pct_road_length_grade_gt_5pct", "pct_road_length_grade_gt_8pct"]
    desc = grade_gdf[grade_cols].describe().T[["min", "50%", "mean", "max"]].rename(columns={"50%": "median"}).round(3).to_dict(orient="index")

    extreme_grade_cells = grade_gdf.loc[grade_gdf["mean_absolute_road_grade_pct"] > 20, ["grid_id", "district", "mean_absolute_road_grade_pct"]]
    negative_or_gt100 = grade_gdf[(grade_gdf["mean_absolute_road_grade_pct"] < 0) | (grade_gdf["mean_absolute_road_grade_pct"] > 100)]

    qa = {
        "dem_reused_from_cache": True,
        "dem_tiles": tiles_needed,
        "dem_reprojected_shape": dem_diag["reprojected_shape"],
        "road_lines_diagnostics": lines_diag,
        "grade_preparation_diagnostics": prep_diag,
        "n_grid_cells": len(grade_gdf),
        "n_districts_present": n_districts_present,
        "n_cells_zero_grade_sample_length": n_cells_no_grade_sample,
        "pct_cells_zero_grade_sample_length": round(n_cells_no_grade_sample / len(grade_gdf) * 100, 3),
        "zero_grade_sample_cells_by_district": no_sample_by_district,
        "grade_stats": desc,
        "n_cells_mean_grade_gt_20pct": len(extreme_grade_cells),
        "extreme_grade_cells": extreme_grade_cells.to_dict(orient="records"),
        "n_cells_grade_out_of_valid_range": len(negative_or_gt100),
        "note_zero_grade_sample": "road_grade_sample_length_m==0 means no road segment in that cell survived the "
        "MIN_ROAD_SEGMENT_LENGTH_M filter and/or had valid DEM coverage at both endpoints -- these cells' grade "
        "columns are NaN (missing), never silently 0, distinguishing 'no data' from 'flat road'.",
    }

    out_dir = cfg.DATA_FEATURES
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "road_grade_features_citywide.parquet"
    grade_gdf.to_parquet(out_path)
    print(f"\n[save] {out_path}")

    qa_dir = cfg.DATA_PROCESSED / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_path = qa_dir / "road_grade_qa_citywide.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {qa_path}")

    print("\n--- SUMMARY ---")
    print(f"Districts present: {n_districts_present}/39")
    print(f"Cells with zero grade sample length (NaN grade, not 0): {n_cells_no_grade_sample} ({qa['pct_cells_zero_grade_sample_length']}%)")
    print(f"Mean absolute road grade citywide: {grade_gdf['mean_absolute_road_grade_pct'].mean():.2f}%")
    print(f"Cells with mean grade > 20% (extreme, review): {len(extreme_grade_cells)}")
    print(f"Cells with grade out of valid [0,100] range: {len(negative_or_gt100)}")


if __name__ == "__main__":
    main()
