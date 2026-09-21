"""Phase 3E cycling infrastructure feature engineering.

Pipeline: load İBB (authoritative) + OSM (complementary) cycling geometries,
categorize each into one of five protection-level buckets using only what
each source actually states (see cycling_source_config.py docstring),
deduplicate overlapping representations of the same physical facility, then
compute per-cell length/density/distance/parking features.

Deduplication (two passes, both via buffer-overlap, never by assuming an
OSM tag equals an İBB record):
  1. OSM road-attribute cycleway=* segments vs. OSM standalone
     highway=cycleway ways — a road's own attribute is dropped if most of
     it lies within CYCLING_DEDUP_BUFFER_M of a standalone cycleway (the
     standalone geometry is kept as the more precisely-digitized one).
  2. Remaining OSM geometries vs. İBB's official lines — İBB is
     authoritative, so an OSM segment mostly overlapping an İBB "Mevcut"
     line is dropped; non-overlapping OSM geometries are kept and tagged
     source="osm" as genuine complementary infrastructure.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from src.features import cycling_source_config as ccfg
from src.utils import config as cfg


def _validate(gdf: gpd.GeoDataFrame, label: str) -> tuple[gpd.GeoDataFrame, int]:
    invalid = int((~gdf.geometry.is_valid).sum())
    if invalid:
        gdf = gdf.set_geometry(gdf.geometry.make_valid())
    print(f"[validate:{label}] invalid={invalid} total={len(gdf)}")
    return gdf, invalid


def load_ibb_lines(path) -> tuple[gpd.GeoDataFrame, dict]:
    gdf = gpd.read_file(path)
    n_raw = len(gdf)
    gdf["category"] = gdf["PRJ_ASAMA"].map(ccfg.IBB_STAGE_TO_CATEGORY)
    n_excluded_not_existing = int(gdf["category"].isna().sum())
    gdf = gdf[gdf["category"].notna()].copy()
    gdf["source"] = "ibb"
    gdf["reference_year"] = gdf["YAPIM_YILI"]
    gdf, n_invalid = _validate(gdf, "ibb_bike_paths")
    gdf = gdf.to_crs(cfg.METRIC_CRS)
    gdf = gdf[["source", "category", "reference_year", "geometry"]]
    diag = {"n_raw": n_raw, "n_excluded_not_existing": n_excluded_not_existing, "n_invalid_repaired": n_invalid, "n_used": len(gdf)}
    return gdf, diag


def load_osm_lines(path) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict]:
    """Returns (standalone, road_attribute) BEFORE dedup."""
    raw = gpd.read_file(path)
    n_raw = len(raw)

    is_standalone = raw.get("highway") == "cycleway"
    standalone = raw[is_standalone].copy()
    foot = standalone.get("foot") if "foot" in standalone.columns else pd.Series(index=standalone.index, dtype=object)
    standalone["category"] = np.select(
        [foot == "no", foot.isin(["designated", "yes"])],
        ["protected_separated", "shared_path"],
        default="other_unknown",
    )
    standalone["source"] = "osm"

    road_rows = []
    non_standalone = raw[~is_standalone]
    for key in ccfg.OSM_CYCLEWAY_KEYS:
        if key not in non_standalone.columns:
            continue
        sub = non_standalone[non_standalone[key].notna() & ~non_standalone[key].isin(ccfg.OSM_CYCLEWAY_EXCLUDE_VALUES)].copy()
        if len(sub) == 0:
            continue
        sub["category"] = sub[key].map(ccfg.OSM_CYCLEWAY_VALUE_TO_CATEGORY).fillna("other_unknown")
        sub["source"] = "osm"
        sub["_tag_key"] = key
        sub["_tag_value"] = sub[key]
        road_rows.append(sub[["category", "source", "_tag_key", "_tag_value", "geometry"]])
    road_attribute = pd.concat(road_rows, ignore_index=True) if road_rows else gpd.GeoDataFrame(columns=["category", "source", "geometry"], geometry="geometry", crs=raw.crs)
    road_attribute = gpd.GeoDataFrame(road_attribute, geometry="geometry", crs=raw.crs)

    standalone, n_inv1 = _validate(standalone[["source", "category", "geometry"]], "osm_standalone")
    road_attribute, n_inv2 = _validate(road_attribute, "osm_road_attribute")
    standalone = standalone.to_crs(cfg.METRIC_CRS)
    road_attribute = road_attribute.to_crs(cfg.METRIC_CRS)

    diag = {
        "n_raw_osm_ways": n_raw, "n_standalone_cycleway": len(standalone),
        "n_road_attribute_segments": len(road_attribute), "n_invalid_repaired": n_inv1 + n_inv2,
    }
    return standalone, road_attribute, diag


def _drop_overlapping(candidates: gpd.GeoDataFrame, reference: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, int]:
    """Drop rows in `candidates` where most of their length lies within
    CYCLING_DEDUP_BUFFER_M of any geometry in `reference`."""
    if len(reference) == 0 or len(candidates) == 0:
        return candidates, 0
    ref_buffer = reference.geometry.buffer(cfg.CYCLING_DEDUP_BUFFER_M).union_all()
    overlap_frac = candidates.geometry.intersection(ref_buffer).length / candidates.geometry.length.replace(0, np.nan)
    is_duplicate = overlap_frac.fillna(0) > cfg.CYCLING_DEDUP_OVERLAP_THRESHOLD
    n_dropped = int(is_duplicate.sum())
    return candidates[~is_duplicate].copy(), n_dropped


def build_combined_network(ibb_path, osm_path) -> tuple[gpd.GeoDataFrame, dict]:
    ibb, ibb_diag = load_ibb_lines(ibb_path)
    standalone, road_attribute, osm_diag = load_osm_lines(osm_path)

    road_attribute_deduped, n_dup_osm_internal = _drop_overlapping(road_attribute, standalone)
    osm_combined = pd.concat(
        [standalone[["source", "category", "geometry"]], road_attribute_deduped[["source", "category", "geometry"]]],
        ignore_index=True,
    )
    osm_combined = gpd.GeoDataFrame(osm_combined, geometry="geometry", crs=cfg.METRIC_CRS)

    osm_final, n_dup_osm_vs_ibb = _drop_overlapping(osm_combined, ibb)

    ibb_out = ibb[["source", "category", "geometry"]].copy()
    combined = pd.concat([ibb_out, osm_final], ignore_index=True)
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=cfg.METRIC_CRS)
    combined["length_m"] = combined.geometry.length
    combined = combined[combined["length_m"] > 0].copy()

    diagnostics = {
        "ibb": ibb_diag,
        "osm": osm_diag,
        "n_osm_road_attribute_dropped_as_duplicate_of_standalone": n_dup_osm_internal,
        "n_osm_dropped_as_duplicate_of_ibb": n_dup_osm_vs_ibb,
        "n_final_geometries": len(combined),
        "total_length_km": float(combined["length_m"].sum() / 1000),
        "length_km_by_category": (combined.groupby("category")["length_m"].sum() / 1000).round(3).to_dict(),
        "length_km_by_source": (combined.groupby("source")["length_m"].sum() / 1000).round(3).to_dict(),
    }
    return combined, diagnostics


def load_ibb_parking(path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    gdf = gdf[gdf["Park_Tipi"] == "Bisiklet Park Alanı"].copy()
    gdf = gdf.to_crs(cfg.METRIC_CRS)
    return gdf[["Park_Alani", "Ilce", "geometry"]]


def compute_cycling_features(
    network: gpd.GeoDataFrame, parking: gpd.GeoDataFrame, grid: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, dict]:
    assert grid.crs.to_string() == cfg.METRIC_CRS
    from scipy.spatial import cKDTree

    # Vectorized clip via gpd.overlay instead of a per-cell Python loop
    # (identical semantics: each infra geometry clipped to each cell it
    # overlaps, summed per cell; protected subset computed the same way).
    # See data/processed/citywide/pipeline_optimization_validation.json.
    protected = network[network["category"] == "protected_separated"]

    def _clipped_length_per_cell(geoms: gpd.GeoDataFrame, colname: str) -> pd.DataFrame:
        if len(geoms) == 0:
            return pd.DataFrame({"grid_id": pd.Series(dtype=object), colname: pd.Series(dtype=float)})
        ov = gpd.overlay(grid[["grid_id", "geometry"]], geoms[["geometry"]], how="intersection", keep_geom_type=False)
        ov[colname] = ov.geometry.length
        return ov.groupby("grid_id")[colname].sum().reset_index()

    total_df = _clipped_length_per_cell(network, "total_len_m")
    prot_df = _clipped_length_per_cell(protected, "prot_len_m")

    result = grid[["grid_id", "land_area_m2"]].merge(total_df, on="grid_id", how="left")
    result = result.merge(prot_df, on="grid_id", how="left")
    result["total_len_m"] = result["total_len_m"].fillna(0.0)
    result["prot_len_m"] = result["prot_len_m"].fillna(0.0)

    result["cycle_infrastructure_length_km"] = result["total_len_m"] / 1000
    result["cycle_infrastructure_density_km_per_km2"] = result["cycle_infrastructure_length_km"] / (result["land_area_m2"] / 1e6)
    result["protected_cycleway_length_km"] = result["prot_len_m"] / 1000
    result["protected_cycleway_density_km_per_km2"] = result["protected_cycleway_length_km"] / (result["land_area_m2"] / 1e6)
    result = result.drop(columns=["land_area_m2", "total_len_m", "prot_len_m"])

    centroids = grid.geometry.centroid
    centroid_xy = np.column_stack([centroids.x.to_numpy(), centroids.y.to_numpy()])

    if len(network):
        # Vectorized nearest-geometry distance via sjoin_nearest (spatial-
        # indexed) instead of a per-centroid Python-level distance scan —
        # same "true distance to the nearest infra LINE" semantics.
        centroid_gdf = gpd.GeoDataFrame(
            {"grid_id": grid["grid_id"].values}, geometry=gpd.points_from_xy(centroid_xy[:, 0], centroid_xy[:, 1]),
            crs=cfg.METRIC_CRS,
        )
        nearest = gpd.sjoin_nearest(centroid_gdf, network[["geometry"]], distance_col="dist")
        nearest = nearest[~nearest.index.duplicated(keep="first")].set_index("grid_id")["dist"]
        dists = grid["grid_id"].map(nearest).to_numpy()
    else:
        dists = np.full(len(grid), np.nan)
    result["distance_to_nearest_cycle_infrastructure_m"] = dists

    if len(parking):
        park_xy = np.column_stack([parking.geometry.x.to_numpy(), parking.geometry.y.to_numpy()])
        tree = cKDTree(park_xy)
        park_dist, _ = tree.query(centroid_xy, k=1)
    else:
        park_dist = np.full(len(grid), np.nan)
    result["distance_to_nearest_bicycle_parking_m"] = park_dist

    joined = gpd.sjoin(parking[["geometry"]], grid[["grid_id", "geometry"]], predicate="intersects", how="inner") if len(parking) else None
    parking_counts = joined.groupby("grid_id").size() if joined is not None else pd.Series(dtype=int)
    result = result.merge(parking_counts.rename("bicycle_parking_count"), on="grid_id", how="left")
    result["bicycle_parking_count"] = result["bicycle_parking_count"].fillna(0).astype(int)

    diagnostics = {"n_parking_used": len(parking), "n_infra_geometries_used": len(network)}
    return result, diagnostics


def compute_pct_road_with_cycle_infra(network: gpd.GeoDataFrame, road_graph_undirected_edges: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> pd.DataFrame:
    """Share of each cell's (Phase 3A) road network length lying within
    CYCLING_DEDUP_BUFFER_M of any cycling-infrastructure geometry."""
    assert grid.crs.to_string() == cfg.METRIC_CRS
    infra_buffer = network.geometry.buffer(cfg.CYCLING_DEDUP_BUFFER_M).union_all() if len(network) else None

    # Vectorized clip via gpd.overlay instead of a per-cell Python loop —
    # identical semantics (each road edge clipped to each cell, and to the
    # infra buffer, summed per cell). See
    # data/processed/citywide/pipeline_optimization_validation.json.
    overlay = gpd.overlay(
        grid[["grid_id", "geometry"]], road_graph_undirected_edges[["geometry"]],
        how="intersection", keep_geom_type=False,
    )
    overlay["road_length_total_m"] = overlay.geometry.length
    overlay["road_length_with_cycle_infra_m"] = (
        overlay.geometry.intersection(infra_buffer).length if infra_buffer is not None else 0.0
    )
    agg = overlay.groupby("grid_id").agg(
        road_length_with_cycle_infra_m=("road_length_with_cycle_infra_m", "sum"),
        road_length_total_m=("road_length_total_m", "sum"),
    ).reset_index()
    df = grid[["grid_id"]].merge(agg, on="grid_id", how="left")
    df["road_length_with_cycle_infra_m"] = df["road_length_with_cycle_infra_m"].fillna(0.0)
    df["road_length_total_m"] = df["road_length_total_m"].fillna(0.0)
    df["pct_road_network_with_cycle_infrastructure"] = np.where(
        df["road_length_total_m"] > 0, df["road_length_with_cycle_infra_m"] / df["road_length_total_m"] * 100, np.nan
    )
    return df[["grid_id", "pct_road_network_with_cycle_infrastructure"]]


def compute_network_connectivity(network: gpd.GeoDataFrame, snap_tolerance_m: float = 5.0) -> dict:
    """Study-area-wide descriptive connectivity stats (not a per-cell score,
    per the instruction to avoid an arbitrary connectivity metric)."""
    import networkx as nx
    from shapely.geometry import Point

    G = nx.Graph()
    for geom, length in zip(network.geometry, network["length_m"]):
        lines = geom.geoms if geom.geom_type == "MultiLineString" else [geom]
        for line in lines:
            coords = list(line.coords)
            a = (round(coords[0][0] / snap_tolerance_m), round(coords[0][1] / snap_tolerance_m))
            b = (round(coords[-1][0] / snap_tolerance_m), round(coords[-1][1] / snap_tolerance_m))
            G.add_edge(a, b, length_m=Point(coords[0]).distance(Point(coords[-1])))

    components = list(nx.connected_components(G))
    comp_lengths = []
    for comp in components:
        sub = G.subgraph(comp)
        comp_lengths.append(sum(d["length_m"] for _, _, d in sub.edges(data=True)))

    return {
        "n_disconnected_components": len(components),
        "largest_component_length_km": round(max(comp_lengths) / 1000, 3) if comp_lengths else 0.0,
        "snap_tolerance_m": snap_tolerance_m,
        "note": "Endpoint-graph connectivity on the final deduplicated network; nodes snapped at "
                f"{snap_tolerance_m}m to merge near-coincident endpoints. Reported study-area-wide, "
                "not decomposed per grid cell, since connectivity is a network-level property.",
    }
