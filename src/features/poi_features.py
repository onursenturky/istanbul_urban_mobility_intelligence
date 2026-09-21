"""Phase 3A POI feature engineering.

Classifies raw OSM POIs into 12 mutually-exclusive categories (see
osm_tag_config.POI_CATEGORY_RULES), removes node/way duplicates of the same
real-world feature, assigns each remaining POI to exactly one grid cell via
its representative point, and aggregates counts, density, and diversity.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from src.features import osm_tag_config as tags
from src.utils import config as cfg


def _classify_category(gdf: gpd.GeoDataFrame) -> pd.Series:
    category = pd.Series(pd.NA, index=gdf.index, dtype="object")
    for cat_name, key, allowed in tags.POI_CATEGORY_RULES:
        if key not in gdf.columns:
            continue
        unassigned = category.isna()
        col = gdf[key]
        present = col.notna() & unassigned
        if allowed is not None:
            present &= col.isin(allowed)
        category[present] = cat_name
    return category


def _dedup_within_category(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, int]:
    """Drop a POI node within POI_DEDUP_DISTANCE_M of a way/relation of the
    SAME category (same real-world feature mapped twice), keeping the
    polygon/way representation."""
    gdf = gdf.copy()
    gdf["_is_point"] = gdf.geometry.geom_type == "Point"
    gdf["_drop"] = False

    for _, group in gdf.groupby("poi_category"):
        points = group[group["_is_point"]]
        others = group[~group["_is_point"]]
        if len(points) == 0 or len(others) == 0:
            continue
        joined = gpd.sjoin_nearest(
            points[["geometry"]],
            others[["geometry"]],
            how="left",
            max_distance=cfg.POI_DEDUP_DISTANCE_M,
            distance_col="dist_to_way",
        )
        joined = joined[~joined.index.duplicated(keep="first")]
        dup_idx = joined.index[joined["dist_to_way"].notna()]
        gdf.loc[dup_idx, "_drop"] = True

    n_dropped = int(gdf["_drop"].sum())
    gdf = gdf[~gdf["_drop"]].drop(columns=["_is_point", "_drop"])
    return gdf, n_dropped


def _entropy_bits(row: pd.Series) -> float:
    counts = row[tags.POI_CATEGORIES].to_numpy(dtype=float)
    total = counts.sum()
    if total == 0:
        return 0.0
    p = counts[counts > 0] / total
    return float(-(p * np.log2(p)).sum())


def compute_poi_features(
    pois_raw: gpd.GeoDataFrame, grid_gdf: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, dict]:
    assert grid_gdf.crs.to_string() == cfg.METRIC_CRS, "grid must already be in the metric CRS"

    gdf = pois_raw.to_crs(cfg.METRIC_CRS).copy()
    invalid_before = int((~gdf.geometry.is_valid).sum())
    if invalid_before:
        gdf["geometry"] = gdf.geometry.make_valid()
    gdf = gdf[~gdf.geometry.is_empty]

    gdf["poi_category"] = _classify_category(gdf)
    n_uncategorized = int(gdf["poi_category"].isna().sum())
    gdf = gdf[gdf["poi_category"].notna()].copy()

    gdf, n_duplicates_removed = _dedup_within_category(gdf)

    gdf["geometry"] = gdf.geometry.representative_point()
    joined = gpd.sjoin(
        gdf[["poi_category", "geometry"]],
        grid_gdf[["grid_id", "geometry"]],
        predicate="intersects",
        how="inner",
    )
    counts = joined.groupby(["grid_id", "poi_category"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=tags.POI_CATEGORIES, fill_value=0).reset_index()

    result = grid_gdf[["grid_id", "land_area_m2"]].merge(counts, on="grid_id", how="left")
    for c in tags.POI_CATEGORIES:
        result[c] = result[c].fillna(0).astype(int)

    result["total_poi_count"] = result[tags.POI_CATEGORIES].sum(axis=1)
    result["poi_density_km2"] = result["total_poi_count"] / (result["land_area_m2"] / 1e6)
    result["poi_category_count"] = (result[tags.POI_CATEGORIES] > 0).sum(axis=1)
    result["poi_entropy"] = result.apply(_entropy_bits, axis=1)
    result = result.drop(columns=["land_area_m2"])

    diagnostics = {
        "n_pois_raw": int(len(pois_raw)),
        "invalid_geometries_repaired": invalid_before,
        "n_uncategorized_dropped": n_uncategorized,
        "n_duplicate_pois_removed": n_duplicates_removed,
        "n_pois_used": int(len(gdf)),
    }
    return result, diagnostics
