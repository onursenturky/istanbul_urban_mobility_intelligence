"""Phase 7A: pct_road_network_with_cycle_infrastructure, previously deferred
(citywide cycling features were built İBB-only, with this one column left
as status="PENDING_ROAD_NETWORK" because the road network was 0/39 -- see
build_cycling_features_citywide.py).

Acquisition-method change ONLY. compute_pct_road_with_cycle_infra takes a
plain `road_graph_undirected_edges` GeoDataFrame (only .geometry is used) --
it never required a graph object itself, so the PBF-derived road "lines"
layer (already loaded/validated in build_road_features_citywide.py) is used
directly, with no adapter needed. The cycling network is the SAME İBB-only
network already used for every other citywide cycling feature (loaded
identically via load_ibb_lines), so this column's cycling-infrastructure
side stays fully consistent with the rest of the frozen cycling feature set.

Outputs:
  data/processed/citywide/features/cycling_road_overlap_citywide.parquet
  data/processed/citywide/qa/cycling_road_overlap_qa_citywide.json
"""

from __future__ import annotations

import json

import geopandas as gpd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.build_road_features_citywide import load_road_lines
from src.features.cycling_infrastructure_features import compute_pct_road_with_cycle_infra, load_ibb_lines
from src.utils import config as cfg

IBB_BIKE_PATHS_PATH = cfg.DATA_RAW / "cycling" / "ibb_bisiklet_yollari.geojson"


def load_citywide_grid() -> gpd.GeoDataFrame:
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 22322, f"expected the frozen citywide grid (22,322 cells), found {len(grid)}"
    assert grid["grid_id"].is_unique
    return grid


def main() -> None:
    print("=" * 72)
    print("Citywide pct_road_network_with_cycle_infrastructure (39 districts, PBF-derived roads)")
    print("=" * 72)

    grid = load_citywide_grid()

    print("\n[1/3] İBB cycling network (same source as all other citywide cycling features)...")
    ibb_network, ibb_diag = load_ibb_lines(IBB_BIKE_PATHS_PATH)
    ibb_network["length_m"] = ibb_network.geometry.length
    ibb_network = ibb_network[ibb_network["length_m"] > 0].copy()
    print(f"  {ibb_diag}")

    print("\n[2/3] Road edges (PBF-derived lines layer, reused from build_road_features_citywide)...")
    edges, lines_diag = load_road_lines()
    print(f"  n_edges_used: {lines_diag['n_used_highway_ways']}")

    print("\n[3/3] compute_pct_road_with_cycle_infra() (UNMODIFIED)...")
    result = compute_pct_road_with_cycle_infra(ibb_network, edges, grid)

    missing = set(grid["grid_id"]) - set(result["grid_id"])
    assert not missing, f"{len(missing)} grid cells disappeared during cycling-road-overlap processing"
    assert len(result) == 22322 and result["grid_id"].is_unique

    base = grid[["grid_id", "district", "geometry"]]
    overlap_gdf = gpd.GeoDataFrame(base.merge(result, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)

    n_districts_present = overlap_gdf["district"].nunique()
    n_nan = int(overlap_gdf["pct_road_network_with_cycle_infrastructure"].isna().sum())
    n_zero_road_but_valid_pct = int(
        ((overlap_gdf["pct_road_network_with_cycle_infrastructure"].notna())
         & (overlap_gdf["pct_road_network_with_cycle_infrastructure"] == 0)).sum()
    )
    valid_vals = overlap_gdf["pct_road_network_with_cycle_infrastructure"].dropna()
    n_gt100 = int((valid_vals > 100).sum())
    n_lt0 = int((valid_vals < 0).sum())
    nonzero_cells = overlap_gdf[overlap_gdf["pct_road_network_with_cycle_infrastructure"] > 0]

    qa = {
        "ibb_network_diagnostics": ibb_diag,
        "road_lines_diagnostics": lines_diag,
        "n_grid_cells": len(overlap_gdf),
        "n_districts_present": n_districts_present,
        "n_cells_nan_no_road_in_cell": n_nan,
        "pct_cells_nan": round(n_nan / len(overlap_gdf) * 100, 3),
        "n_cells_zero_pct_has_road_no_cycle_infra_nearby": n_zero_road_but_valid_pct,
        "n_cells_pct_gt_100_should_be_0": n_gt100,
        "n_cells_pct_lt_0_should_be_0": n_lt0,
        "pct_stats_over_valid_cells": valid_vals.describe().round(3).to_dict(),
        "n_cells_with_any_cycle_overlap": len(nonzero_cells),
        "note_on_nan": "NaN means the cell has zero (Phase 7A PBF-derived) road length -- distinct from a cell "
        "that HAS roads but none near cycling infrastructure (which correctly gets 0.0), matching the "
        "existing function's own np.where(road_length_total_m > 0, ..., np.nan) semantics.",
    }

    out_dir = cfg.DATA_FEATURES
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cycling_road_overlap_citywide.parquet"
    overlap_gdf.to_parquet(out_path)
    print(f"\n[save] {out_path}")

    qa_dir = cfg.DATA_PROCESSED / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_path = qa_dir / "cycling_road_overlap_qa_citywide.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {qa_path}")

    print("\n--- SUMMARY ---")
    print(f"Districts present: {n_districts_present}/39")
    print(f"NaN cells (zero road length): {n_nan} ({qa['pct_cells_nan']}%)")
    print(f"Cells with pct out of [0,100] range: {n_gt100 + n_lt0}")
    print(f"Cells with any cycle-infra overlap (>0%): {len(nonzero_cells)}")
    print(f"Mean pct (valid cells): {valid_vals.mean():.3f}%")


if __name__ == "__main__":
    main()
