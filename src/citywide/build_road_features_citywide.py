"""Phase 7A: citywide road-network features from the local OSM PBF extract.

Acquisition-method change ONLY -- analytical definitions are unchanged from
src.features.road_features.compute_road_features:
  - highway classification: osm_tag_config.MAJOR_ROAD_HIGHWAY_CLASSES /
    LOCAL_ROAD_HIGHWAY_CLASSES / NOT_WALKABLE_HIGHWAY_CLASSES /
    NOT_CYCLE_ACCESSIBLE_HIGHWAY_CLASSES (verbatim, unmodified)
  - grid aggregation: gpd.overlay(grid, edges) + groupby-sum (verbatim
    logic, copied here because the source data is no longer a graph object)
  - intersection definition: a node where >=3 distinct street segments meet
    in the undirected road network (verbatim definition)

Two independent readers of data/raw/osm/pbf/road_network_extract.osm.pbf are
used, per the validated Phase 7A design (see
phase7a_intersection_regression_test.py for the regression that justified
this split):

  1. Geometry path (this module's `load_road_lines` / `compute_length_features`):
     GDAL's native OSM driver "lines" layer via pyogrio. This is a plain,
     one-row-per-way table (no directional duplication -- unlike an OSMnx
     MultiDiGraph, a two-way street is NOT represented twice here), so no
     to_undirected()-style deduplication step is needed before summing
     lengths. Sufficient for every length/class/density feature.

  2. Topology path (`compute_intersections`): pyrosm.OSM.get_network(nodes=True)
     provides genuine OSM-node-based u/v edge endpoints. Node degree is the
     count of a node id's appearances across the concatenated u and v
     columns -- validated on the pilot districts (98.6% exact per-cell
     agreement with the frozen OSMnx-graph G_u.degree() baseline, max abs
     cell diff 2, total diff 0.032%; see phase7a_intersection_regression.json)
     to reproduce real undirected-graph degree semantics (self-loops count
     twice, parallel edges each contribute, no directed-edge inflation --
     get_network()'s edges are ~half of what to_graph() produces, confirming
     they are not direction-duplicated).

323 of 245,089 raw highway ways (0.13%) are closed-way polygonal highway
areas (e.g. highway=pedestrian plazas with area=yes) that GDAL classifies
into the "multipolygons" layer instead of "lines". These are EXCLUDED here,
consistent with the pilot's own OSMnx graph (network_type="all" fetches
ways for a routable network and does not represent closed polygonal areas
as line edges either) -- not a silent drop, see qa diagnostics.

Outputs:
  data/processed/citywide/features/road_features_citywide.parquet
  data/processed/citywide/qa/road_qa_citywide.json
  data/processed/citywide/qa/coverage_gate_road.json
"""

from __future__ import annotations

import json

import geopandas as gpd
import pandas as pd
import pyogrio
from pyrosm import OSM

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.coverage_gate import coverage_report, print_report
from src.features import osm_tag_config as tags
from src.features.road_features import _highway_class
from src.utils import config as cfg

ROAD_PBF = cfg.DATA_RAW / "osm" / "pbf" / "road_network_extract.osm.pbf"
PBF_META = cfg.DATA_RAW / "osm" / "pbf" / "turkey-latest.osm.pbf.meta.json"


def load_citywide_grid() -> gpd.GeoDataFrame:
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 22322, f"expected the frozen citywide grid (22,322 cells), found {len(grid)}"
    assert grid["grid_id"].is_unique
    return grid


def load_road_lines() -> tuple[gpd.GeoDataFrame, dict]:
    print(f"[load] {ROAD_PBF} layer='lines' (GDAL OSM driver, via pyogrio)")
    raw = pyogrio.read_dataframe(str(ROAD_PBF), layer="lines")
    n_raw = len(raw)
    n_osm_id_dup = int(raw["osm_id"].duplicated().sum())
    n_highway_null = int(raw["highway"].isna().sum())

    mp_info = pyogrio.read_dataframe(str(ROAD_PBF), layer="multipolygons")
    n_closed_way_highway_areas = int(mp_info["other_tags"].astype(str).str.contains('"highway"', na=False).sum())

    gdf = raw[raw["highway"].notna()].copy()
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=raw.crs).to_crs(cfg.METRIC_CRS)

    invalid_before = int((~gdf.geometry.is_valid).sum())
    if invalid_before:
        gdf["geometry"] = gdf.geometry.make_valid()
    non_line = ~gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])
    n_non_line_dropped = int(non_line.sum())
    gdf = gdf[~non_line].copy()

    diag = {
        "n_raw_lines_layer_rows": n_raw,
        "n_osm_id_duplicates_in_lines_layer": n_osm_id_dup,
        "n_highway_null_dropped": n_highway_null,
        "n_used_highway_ways": len(gdf),
        "n_closed_way_highway_areas_excluded_polygon_classified": n_closed_way_highway_areas,
        "n_invalid_geometries_repaired": invalid_before,
        "n_non_line_geometries_dropped": n_non_line_dropped,
    }
    return gdf[["osm_id", "highway", "geometry"]], diag


def compute_length_features(edges: gpd.GeoDataFrame, grid_gdf: gpd.GeoDataFrame) -> tuple[pd.DataFrame, dict]:
    """Verbatim port of compute_road_features' geometry/overlay logic
    (src/features/road_features.py), reading `edges` from a plain
    GeoDataFrame instead of ox.graph_to_gdfs(G_u, ...)."""
    assert grid_gdf.crs.to_string() == cfg.METRIC_CRS

    edges = edges.copy()
    edges["highway_class"] = edges["highway"].apply(_highway_class)
    edges["is_major"] = edges["highway_class"].isin(tags.MAJOR_ROAD_HIGHWAY_CLASSES)
    edges["is_local"] = edges["highway_class"].isin(tags.LOCAL_ROAD_HIGHWAY_CLASSES)
    edges["is_walkable"] = ~edges["highway_class"].isin(tags.NOT_WALKABLE_HIGHWAY_CLASSES)
    edges["is_cycle"] = ~edges["highway_class"].isin(tags.NOT_CYCLE_ACCESSIBLE_HIGHWAY_CLASSES)

    overlay = gpd.overlay(
        grid_gdf[["grid_id", "geometry"]], edges[["geometry", "is_major", "is_local", "is_walkable", "is_cycle"]],
        how="intersection", keep_geom_type=False,
    )
    overlay["length_m"] = overlay.geometry.length
    overlay["major_len"] = overlay["length_m"].where(overlay["is_major"], 0.0)
    overlay["local_len"] = overlay["length_m"].where(overlay["is_local"], 0.0)
    overlay["walkable_len"] = overlay["length_m"].where(overlay["is_walkable"], 0.0)
    overlay["cycle_len"] = overlay["length_m"].where(overlay["is_cycle"], 0.0)

    road_df = overlay.groupby("grid_id").agg(
        road_length_m=("length_m", "sum"),
        major_road_length_m=("major_len", "sum"),
        local_road_length_m=("local_len", "sum"),
        walkable_road_length_m=("walkable_len", "sum"),
        cycle_accessible_road_length_m=("cycle_len", "sum"),
    ).reset_index()

    result = grid_gdf[["grid_id", "land_area_m2"]].merge(road_df, on="grid_id", how="left")
    for col in [
        "road_length_m", "major_road_length_m", "local_road_length_m",
        "walkable_road_length_m", "cycle_accessible_road_length_m",
    ]:
        result[col] = result[col].fillna(0.0)
    result["road_density_km_per_km2"] = result["road_length_m"] / 1000 / (result["land_area_m2"] / 1e6)
    result = result.drop(columns=["land_area_m2"])

    diag = {
        "n_edges_used": int(len(edges)),
        "total_road_length_km": float(edges.geometry.length.sum() / 1000),
        "highway_class_counts": edges["highway_class"].value_counts().to_dict(),
    }
    return result, diag


def compute_intersections(grid_gdf: gpd.GeoDataFrame) -> tuple[pd.DataFrame, dict]:
    """Validated lightweight method (see phase7a_intersection_regression_test.py):
    node degree = count of appearances across concatenated u/v edge endpoint
    columns from pyrosm.get_network(), thresholded at >=3."""
    print(f"[load] {ROAD_PBF} via pyrosm.OSM.get_network(nodes=True) for topology")
    osm = OSM(str(ROAD_PBF))
    nodes, edges = osm.get_network(network_type="all", nodes=True)
    print(f"    get_network(): {len(nodes):,} nodes, {len(edges):,} edges")

    nodes_m = nodes.to_crs(cfg.METRIC_CRS)
    edges_m = edges.to_crs(cfg.METRIC_CRS)

    degree_counts = pd.concat([edges_m["u"], edges_m["v"]]).value_counts()
    node_degree = nodes_m["id"].map(degree_counts).fillna(0)
    intersections = nodes_m[node_degree >= 3].copy()
    n_intersections_total = len(intersections)
    print(f"    n_intersections_total (degree>=3): {n_intersections_total:,}")

    joined = gpd.sjoin(
        intersections[["geometry"]], grid_gdf[["grid_id", "geometry"]], predicate="intersects", how="inner"
    )
    counts = joined.groupby("grid_id").size().rename("intersection_count").reset_index()

    result = grid_gdf[["grid_id", "land_area_m2"]].merge(counts, on="grid_id", how="left")
    result["intersection_count"] = result["intersection_count"].fillna(0).astype(int)
    result["intersection_density_km2"] = result["intersection_count"] / (result["land_area_m2"] / 1e6)
    result = result.drop(columns=["land_area_m2"])

    diag = {
        "n_nodes_get_network": int(len(nodes)),
        "n_edges_get_network": int(len(edges)),
        "n_intersections_total": int(n_intersections_total),
        "method": "pyrosm get_network u/v degree>=3 (validated vs OSMnx graph degree on pilot: "
                  "98.638% exact per-cell agreement, max abs diff 2, total diff 0.032%)",
    }
    return result, diag


def main() -> None:
    print("=" * 72)
    print("Citywide road-network features (39 districts, 22,322-cell grid, PBF-derived)")
    print("=" * 72)

    grid = load_citywide_grid()
    pbf_meta = json.loads(PBF_META.read_text(encoding="utf-8"))

    print("\n[1/4] Geometry path: road lengths / classes / density (GDAL OSM lines layer)...")
    edges, lines_diag = load_road_lines()
    length_features, length_diag = compute_length_features(edges, grid)

    print("\n[2/4] Topology path: intersections (pyrosm get_network u/v degree)...")
    intersection_features, intersection_diag = compute_intersections(grid)

    print("\n[3/4] Merge...")
    result = length_features.merge(intersection_features, on="grid_id", how="outer")
    assert len(result) == 22322 and result["grid_id"].is_unique
    missing = set(grid["grid_id"]) - set(result["grid_id"])
    assert not missing, f"{len(missing)} grid cells disappeared during road feature processing"

    base = grid[["grid_id", "district", "geometry"]]
    road_gdf = gpd.GeoDataFrame(base.merge(result, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)

    print("\n[4/4] QA...")
    length_cols = [
        "road_length_m", "major_road_length_m", "local_road_length_m",
        "walkable_road_length_m", "cycle_accessible_road_length_m", "road_density_km_per_km2",
    ]
    n_districts_present = road_gdf["district"].nunique()

    # Concentration / outlier checks
    total_len_by_district = road_gdf.groupby("district")["road_length_m"].sum().sort_values(ascending=False)
    p99 = road_gdf["road_length_m"].quantile(0.99)
    outlier_cells = road_gdf.loc[road_gdf["road_length_m"] > p99 * 3, ["grid_id", "district", "road_length_m"]]
    # a cell's road length cannot legitimately exceed a generous multiple of its nominal cell diagonal budget;
    # flag (not silently drop) any cell where road_length_m is implausibly large relative to land_area_m2
    cell_area_check = grid.set_index("grid_id")["land_area_m2"]
    road_gdf = road_gdf.merge(cell_area_check.rename("land_area_m2"), on="grid_id")
    implausible_density = road_gdf[road_gdf["road_density_km_per_km2"] > 50]  # >50 km road per km2 is extreme

    n_zero_road_cells = int((road_gdf["road_length_m"] == 0).sum())
    zero_road_by_district = road_gdf[road_gdf["road_length_m"] == 0]["district"].value_counts().to_dict()

    cells_with_intersections_but_no_road = road_gdf[(road_gdf["intersection_count"] > 0) & (road_gdf["road_length_m"] == 0)]

    qa = {
        "pbf_provenance": {
            "source_url": pbf_meta["source_url"],
            "resolved_url": pbf_meta["resolved_url"],
            "pbf_internal_osm_timestamp": pbf_meta["pbf_internal_osm_timestamp"],
            "sha256": pbf_meta["sha256"],
            "license": pbf_meta["license"],
        },
        "lines_layer_diagnostics": lines_diag,
        "length_feature_diagnostics": length_diag,
        "intersection_diagnostics": intersection_diag,
        "n_grid_cells": len(road_gdf),
        "n_districts_present": n_districts_present,
        "road_length_stats_km": road_gdf[length_cols].describe().T[["min", "50%", "mean", "max"]].rename(columns={"50%": "median"}).round(4).to_dict(orient="index"),
        "total_road_length_km_by_district": (total_len_by_district / 1000).round(2).to_dict(),
        "n_cells_zero_road_length": n_zero_road_cells,
        "pct_cells_zero_road_length": round(n_zero_road_cells / len(road_gdf) * 100, 3),
        "zero_road_cells_by_district": zero_road_by_district,
        "n_cells_implausible_road_density_gt_50km_per_km2": len(implausible_density),
        "implausible_density_cells": implausible_density[["grid_id", "district", "road_density_km_per_km2"]].to_dict(orient="records"),
        "n_outlier_cells_road_length_gt_3x_p99": len(outlier_cells),
        "outlier_cells": outlier_cells.to_dict(orient="records"),
        "n_cells_intersections_but_zero_road_length": len(cells_with_intersections_but_no_road),
        "cells_intersections_but_zero_road_length": cells_with_intersections_but_no_road[["grid_id", "district", "intersection_count"]].to_dict(orient="records"),
        "total_intersections_citywide": int(road_gdf["intersection_count"].sum()),
        "total_road_length_km_citywide": float(road_gdf["road_length_m"].sum() / 1000),
    }

    road_gdf = road_gdf.drop(columns=["land_area_m2"])

    out_dir = cfg.DATA_FEATURES
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "road_features_citywide.parquet"
    road_gdf.to_parquet(out_path)
    print(f"\n[save] {out_path}")

    qa_dir = cfg.DATA_PROCESSED / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_path = qa_dir / "road_qa_citywide.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {qa_path}")

    value_cols = ["road_length_m", "intersection_count"]
    report = coverage_report(road_gdf, value_cols)
    print_report(report, "road_network")
    gate_path = qa_dir / "coverage_gate_road.json"
    gate_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[save] {gate_path}")

    print("\n--- SUMMARY ---")
    print(f"Districts present: {n_districts_present}/39")
    print(f"Total road length citywide: {qa['total_road_length_km_citywide']:.1f} km")
    print(f"Total intersections citywide: {qa['total_intersections_citywide']:,}")
    print(f"Cells with zero road length: {n_zero_road_cells} ({qa['pct_cells_zero_road_length']}%)")
    print(f"Implausible density cells (>50 km/km2): {len(implausible_density)}")
    print(f"Outlier cells (>3x p99 road length): {len(outlier_cells)}")
    print(f"Cells with intersections but zero road length (should be 0): {len(cells_with_intersections_but_no_road)}")


if __name__ == "__main__":
    main()
