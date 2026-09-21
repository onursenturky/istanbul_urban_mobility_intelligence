"""Section 3: validate every vectorized optimization against its original
per-cell-loop implementation on the PILOT 514-cell grid, before trusting it
at citywide scale.

Runs on the pilot config (NOT activated to citywide) since the pilot's
cached raw data and known-correct outputs are the ground truth to compare
against. Writes data/processed/citywide/pipeline_optimization_validation.json.
"""

from __future__ import annotations

import json
import time

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd

from src.features import road_features, building_features, road_grade_features, cycling_infrastructure_features as cyc
from src.features import osm_tag_config as tags
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "data" / "processed" / "citywide"


# ---------------------------------------------------------------------
# Legacy (pre-optimization) implementations, reconstructed verbatim from
# the code as it stood before this phase's edits, kept here ONLY for this
# one-time validation run.
# ---------------------------------------------------------------------

def _legacy_road_features(G, grid_gdf):
    n_edges_directed_raw = len(G.edges)
    G_proj = ox.project_graph(G, to_crs=cfg.METRIC_CRS)
    G_u = ox.convert.to_undirected(G_proj)
    edges = ox.graph_to_gdfs(G_u, nodes=False, edges=True).reset_index()
    edges["highway_class"] = edges["highway"].apply(road_features._highway_class)
    edges["is_major"] = edges["highway_class"].isin(tags.MAJOR_ROAD_HIGHWAY_CLASSES)
    edges["is_local"] = edges["highway_class"].isin(tags.LOCAL_ROAD_HIGHWAY_CLASSES)
    edges["is_walkable"] = ~edges["highway_class"].isin(tags.NOT_WALKABLE_HIGHWAY_CLASSES)
    edges["is_cycle"] = ~edges["highway_class"].isin(tags.NOT_CYCLE_ACCESSIBLE_HIGHWAY_CLASSES)

    sindex = edges.sindex
    rows = []
    for grid_id, cell_geom in zip(grid_gdf["grid_id"], grid_gdf.geometry):
        candidate_idx = list(sindex.query(cell_geom, predicate="intersects"))
        if not candidate_idx:
            rows.append({"grid_id": grid_id, "road_length_m": 0.0, "major_road_length_m": 0.0,
                         "local_road_length_m": 0.0, "walkable_road_length_m": 0.0, "cycle_accessible_road_length_m": 0.0})
            continue
        cand = edges.iloc[candidate_idx]
        clipped_len = cand.geometry.intersection(cell_geom).length
        rows.append({
            "grid_id": grid_id, "road_length_m": float(clipped_len.sum()),
            "major_road_length_m": float(clipped_len[cand["is_major"]].sum()),
            "local_road_length_m": float(clipped_len[cand["is_local"]].sum()),
            "walkable_road_length_m": float(clipped_len[cand["is_walkable"]].sum()),
            "cycle_accessible_road_length_m": float(clipped_len[cand["is_cycle"]].sum()),
        })
    return pd.DataFrame(rows).sort_values("grid_id").reset_index(drop=True)


def _legacy_building_area(gdf, grid_gdf):
    sindex = gdf.sindex
    area_rows = []
    for grid_id, cell_geom in zip(grid_gdf["grid_id"], grid_gdf.geometry):
        idx = list(sindex.query(cell_geom, predicate="intersects"))
        if not idx:
            area_rows.append({"grid_id": grid_id, "building_footprint_area_m2": 0.0})
            continue
        clipped = gdf.geometry.iloc[idx].intersection(cell_geom)
        area_rows.append({"grid_id": grid_id, "building_footprint_area_m2": float(clipped.area.sum())})
    return pd.DataFrame(area_rows).sort_values("grid_id").reset_index(drop=True)


def _legacy_road_grade(edges, grid):
    sindex = edges.sindex
    records = []
    for grid_id, cell_geom in zip(grid["grid_id"], grid.geometry):
        idx = list(sindex.query(cell_geom, predicate="intersects"))
        if idx:
            cand = edges.iloc[idx]
            clipped_len = cand.geometry.intersection(cell_geom).length.to_numpy()
            keep = clipped_len > 0
            lengths, grades = clipped_len[keep], cand["grade_pct"].to_numpy()[keep]
        else:
            lengths, grades = np.array([]), np.array([])
        total_len = lengths.sum()
        if total_len == 0:
            records.append({"grid_id": grid_id, "mean_absolute_road_grade_pct": np.nan,
                             "median_absolute_road_grade_pct": np.nan, "pct_road_length_grade_gt_5pct": np.nan,
                             "pct_road_length_grade_gt_8pct": np.nan, "road_grade_sample_length_m": 0.0})
            continue
        mean_grade = float(np.average(grades, weights=lengths))
        order = np.argsort(grades)
        sorted_grades, sorted_lengths = grades[order], lengths[order]
        cum = np.cumsum(sorted_lengths)
        median_grade = float(sorted_grades[np.searchsorted(cum, total_len / 2)])
        pct_gt5 = float(lengths[grades > 5].sum() / total_len * 100)
        pct_gt8 = float(lengths[grades > 8].sum() / total_len * 100)
        records.append({"grid_id": grid_id, "mean_absolute_road_grade_pct": mean_grade,
                         "median_absolute_road_grade_pct": median_grade, "pct_road_length_grade_gt_5pct": pct_gt5,
                         "pct_road_length_grade_gt_8pct": pct_gt8, "road_grade_sample_length_m": total_len})
    return pd.DataFrame(records).sort_values("grid_id").reset_index(drop=True)


def _legacy_cycling_length(network, grid):
    sindex = network.sindex
    protected = network[network["category"] == "protected_separated"]
    protected_sindex = protected.sindex if len(protected) else None
    rows = []
    for grid_id, cell_geom, land_area_m2 in zip(grid["grid_id"], grid.geometry, grid["land_area_m2"]):
        idx = list(sindex.query(cell_geom, predicate="intersects"))
        total_len = sum(network.geometry.iloc[idx].intersection(cell_geom).length) if idx else 0.0
        prot_len = 0.0
        if protected_sindex is not None:
            pidx = list(protected_sindex.query(cell_geom, predicate="intersects"))
            if pidx:
                prot_len = sum(protected.geometry.iloc[pidx].intersection(cell_geom).length)
        rows.append({"grid_id": grid_id, "cycle_infrastructure_length_km": total_len / 1000,
                     "protected_cycleway_length_km": prot_len / 1000})
    return pd.DataFrame(rows).sort_values("grid_id").reset_index(drop=True)


def _legacy_pct_road_cycle_infra(network, road_edges, grid):
    infra_buffer = network.geometry.buffer(cfg.CYCLING_DEDUP_BUFFER_M).union_all() if len(network) else None
    sindex = road_edges.sindex
    rows = []
    for grid_id, cell_geom in zip(grid["grid_id"], grid.geometry):
        idx = list(sindex.query(cell_geom, predicate="intersects"))
        if not idx:
            rows.append({"grid_id": grid_id, "road_length_with_cycle_infra_m": 0.0, "road_length_total_m": 0.0})
            continue
        clipped = road_edges.geometry.iloc[idx].intersection(cell_geom)
        total = clipped.length.sum()
        with_infra = clipped.intersection(infra_buffer).length.sum() if infra_buffer is not None else 0.0
        rows.append({"grid_id": grid_id, "road_length_with_cycle_infra_m": with_infra, "road_length_total_m": total})
    df = pd.DataFrame(rows).sort_values("grid_id").reset_index(drop=True)
    df["pct"] = np.where(df["road_length_total_m"] > 0, df["road_length_with_cycle_infra_m"] / df["road_length_total_m"] * 100, np.nan)
    return df


# ---------------------------------------------------------------------

def _compare(old: pd.DataFrame, new: pd.DataFrame, cols: list[str], key="grid_id") -> dict:
    old_s = old.sort_values(key).reset_index(drop=True)
    new_s = new.sort_values(key).reset_index(drop=True)
    assert list(old_s[key]) == list(new_s[key]), "grid_id sets/order differ between old and new"
    diffs = {}
    for c in cols:
        a, b = old_s[c].to_numpy(dtype=float), new_s[c].to_numpy(dtype=float)
        both_nan = np.isnan(a) & np.isnan(b)
        d = np.abs(a - b)
        d[both_nan] = 0.0
        diffs[c] = float(np.nanmax(d))
    return diffs


def main() -> None:
    print("=" * 72)
    print("Section 3 — Pipeline optimization validation (pilot 514-cell grid)")
    print("=" * 72)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert len(grid) == 514

    validations = []

    # --- road_features.compute_road_features ---
    G = ox.load_graphml(cfg.DATA_RAW / "osm" / "osm_road_network_raw.graphml")
    t0 = time.perf_counter(); old_road = _legacy_road_features(G, grid); t_old = time.perf_counter() - t0
    t0 = time.perf_counter(); new_road, _ = road_features.compute_road_features(G, grid); t_new = time.perf_counter() - t0
    cols = ["road_length_m", "major_road_length_m", "local_road_length_m", "walkable_road_length_m", "cycle_accessible_road_length_m"]
    diffs = _compare(old_road, new_road[["grid_id"] + cols], cols)
    validations.append({
        "function": "road_features.compute_road_features (per-cell road length clipping)",
        "previous_implementation": "Python for-loop over grid cells; sindex.query + geometry.intersection per cell",
        "optimized_implementation": "gpd.overlay(grid, edges, how='intersection') + groupby('grid_id').agg(sum)",
        "runtime_old_s": round(t_old, 3), "runtime_new_s": round(t_new, 3),
        "speedup_x": round(t_old / t_new, 2) if t_new > 0 else None,
        "max_abs_difference_by_column": diffs, "tolerance_m": 1e-6,
        "validation_status": "PASS" if max(diffs.values()) < 1e-6 else "FAIL",
    })

    # --- building_features (footprint area clip) ---
    from src.data.fetch_osm_data import fetch_buildings, get_query_polygon
    _, poly_ll = get_query_polygon()
    buildings_raw = fetch_buildings(poly_ll)
    gdf_b = buildings_raw.to_crs(cfg.METRIC_CRS)
    gdf_b = gdf_b[gdf_b.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    gdf_b = gdf_b[gdf_b.geometry.is_valid & ~gdf_b.geometry.is_empty]
    t0 = time.perf_counter(); old_bld = _legacy_building_area(gdf_b, grid); t_old = time.perf_counter() - t0
    t0 = time.perf_counter(); new_bld_full, _ = building_features.compute_building_features(buildings_raw, grid); t_new = time.perf_counter() - t0
    diffs = _compare(old_bld, new_bld_full[["grid_id", "building_footprint_area_m2"]], ["building_footprint_area_m2"])
    validations.append({
        "function": "building_features (per-cell building footprint area clipping)",
        "previous_implementation": "Python for-loop over grid cells; sindex.query + geometry.intersection per cell",
        "optimized_implementation": "gpd.overlay(grid, buildings, how='intersection', keep_geom_type=True) + groupby.sum",
        "runtime_old_s": round(t_old, 3), "runtime_new_s": round(t_new, 3),
        "speedup_x": round(t_old / t_new, 2) if t_new > 0 else None,
        "max_abs_difference_by_column": diffs, "tolerance_m2": 1e-6,
        "validation_status": "PASS" if max(diffs.values()) < 1e-6 else "FAIL",
    })

    # --- road_grade_features ---
    from src.data.fetch_dem_data import fetch_dem_tiles
    from src.features.terrain_features import load_and_reproject_dem
    from src.features.road_grade_features import prepare_road_edges
    study_area = gpd.read_file(cfg.DATA_PROCESSED / "study_area_metric.gpkg").geometry.iloc[0]
    tile_paths = fetch_dem_tiles()
    elevation, transform, _ = load_and_reproject_dem(tile_paths, study_area)
    grade_edges, _ = prepare_road_edges(G, elevation, transform)
    t0 = time.perf_counter(); old_grade = _legacy_road_grade(grade_edges, grid); t_old = time.perf_counter() - t0
    t0 = time.perf_counter(); new_grade = road_grade_features.compute_road_grade_features(grade_edges, grid); t_new = time.perf_counter() - t0
    cols = ["mean_absolute_road_grade_pct", "median_absolute_road_grade_pct", "pct_road_length_grade_gt_5pct", "pct_road_length_grade_gt_8pct", "road_grade_sample_length_m"]
    diffs = _compare(old_grade, new_grade[["grid_id"] + cols], cols)
    validations.append({
        "function": "road_grade_features.compute_road_grade_features",
        "previous_implementation": "Python for-loop over grid cells; sindex.query + intersection, then per-cell weighted stats",
        "optimized_implementation": "gpd.overlay(grid, edges, how='intersection') once, then groupby.apply for the small per-group weighted-median/threshold stats",
        "runtime_old_s": round(t_old, 3), "runtime_new_s": round(t_new, 3),
        "speedup_x": round(t_old / t_new, 2) if t_new > 0 else None,
        "max_abs_difference_by_column": diffs, "tolerance": 1e-6,
        "validation_status": "PASS" if max(diffs.values()) < 1e-6 else "FAIL",
    })

    # --- cycling_infrastructure_features: length + protected length ---
    from src.data.fetch_cycling_infrastructure_data import fetch_ibb_bike_paths, fetch_osm_cycling_ways, fetch_ibb_parking
    from src.features.cycling_infrastructure_features import build_combined_network
    ibb_path = fetch_ibb_bike_paths()
    osm_path = fetch_osm_cycling_ways()
    network_full, _ = build_combined_network(ibb_path, osm_path)
    from src.features.build_cycling_infrastructure_features import clip_network_to_study_area
    network = clip_network_to_study_area(network_full, study_area)
    t0 = time.perf_counter(); old_cyc = _legacy_cycling_length(network, grid); t_old = time.perf_counter() - t0
    t0 = time.perf_counter()
    parking_path = fetch_ibb_parking()
    parking = cyc.load_ibb_parking(parking_path)
    new_cyc, _ = cyc.compute_cycling_features(network, parking, grid)
    t_new = time.perf_counter() - t0
    cols = ["cycle_infrastructure_length_km", "protected_cycleway_length_km"]
    diffs = _compare(old_cyc, new_cyc[["grid_id"] + cols], cols)
    validations.append({
        "function": "cycling_infrastructure_features.compute_cycling_features (length + protected length)",
        "previous_implementation": "Python for-loop over grid cells; sindex.query + intersection per cell, twice (total + protected subset)",
        "optimized_implementation": "gpd.overlay(grid, network/protected, how='intersection') + groupby.sum",
        "runtime_old_s": round(t_old, 3), "runtime_new_s": round(t_new, 3),
        "speedup_x": round(t_old / t_new, 2) if t_new > 0 else None,
        "max_abs_difference_by_column": diffs, "tolerance_km": 1e-9,
        "validation_status": "PASS" if max(diffs.values()) < 1e-9 else "FAIL",
        "note": "runtime_new_s includes the additional sjoin_nearest distance computation and parking join, not isolated to the length-clipping step alone.",
    })

    # --- cycling_infrastructure_features: pct_road_network_with_cycle_infrastructure ---
    road_edges_for_pct = ox.graph_to_gdfs(ox.convert.to_undirected(ox.project_graph(G, to_crs=cfg.METRIC_CRS)), nodes=False, edges=True).reset_index()
    t0 = time.perf_counter(); old_pct = _legacy_pct_road_cycle_infra(network, road_edges_for_pct, grid); t_old = time.perf_counter() - t0
    t0 = time.perf_counter(); new_pct = cyc.compute_pct_road_with_cycle_infra(network, road_edges_for_pct, grid); t_new = time.perf_counter() - t0
    old_pct_renamed = old_pct.rename(columns={"pct": "pct_road_network_with_cycle_infrastructure"})
    diffs = _compare(old_pct_renamed, new_pct, ["pct_road_network_with_cycle_infrastructure"])
    validations.append({
        "function": "cycling_infrastructure_features.compute_pct_road_with_cycle_infra",
        "previous_implementation": "Python for-loop over grid cells; sindex.query + intersection per cell against roads and the infra buffer",
        "optimized_implementation": "gpd.overlay(grid, road_edges, how='intersection') once, then vectorized intersection against the (single) infra buffer geometry, then groupby.sum",
        "runtime_old_s": round(t_old, 3), "runtime_new_s": round(t_new, 3),
        "speedup_x": round(t_old / t_new, 2) if t_new > 0 else None,
        "max_abs_difference_by_column": diffs, "tolerance_pct_points": 1e-6,
        "validation_status": "PASS" if max(diffs.values()) < 1e-6 else "FAIL",
    })

    all_pass = all(v["validation_status"] == "PASS" for v in validations)
    report = {"pilot_grid_n_cells": len(grid), "all_validations_passed": all_pass, "validations": validations}

    out_path = OUT_DIR / "pipeline_optimization_validation.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(json.dumps({k: v for k, v in report.items() if k != "validations"}, indent=2))
    for v in validations:
        print(f"\n{v['function']}")
        print(f"  status={v['validation_status']}  speedup={v.get('speedup_x')}x  max_diff={v['max_abs_difference_by_column']}")
    print(f"\nWritten -> {out_path}")


if __name__ == "__main__":
    main()
