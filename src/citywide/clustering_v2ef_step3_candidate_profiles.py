"""Phase 5B-V2 step 3: full candidate-k profiling (k=4,5,6,7 -- the
plausible zone identified by step 1's internal metrics/stability and step
2's split-transition analysis; k=3 kept for completeness, k=8-10 already
ruled out by step 1's seed-instability collapse and step 2's dispersed/
tiny-split pattern).

For each candidate k: raw-value percentile cluster profiles across the
full requested domain set (population, POI/activity, building presence,
transit, cycling infra, terrain/road-grade, road/intersection density,
green-space, residential/industrial land-use), family BSS contribution
(reusing the same family mapping as Phase 5A-V2's diagnostic), and spatial
coherence (Queen fragmentation + per-cluster Moran's I).
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from libpysal.weights import Queen
from scipy.stats import percentileofscore

from src.analysis.spatial_diagnostics import binary_cluster_morans_i
from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.clustering_phase5b_step1_kdiagnostics import build_queen_graph, fragmentation_diagnostics
from src.citywide.clustering_v2ef_step1_kdiagnostics import load_v2ef_matrix
from src.utils import config as cfg

FEATURES_DIR = cfg.DATA_FEATURES
V2EF_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering_v2_eight_family"
CANDIDATE_KS = [3, 4, 5, 6, 7]

FULL_PROFILE_FEATURES = [
    "population_density_calibrated_km2",
    "total_poi_count", "poi_density_km2", "poi_entropy",
    "building_count", "building_coverage_ratio",
    "total_transit_stop_count", "distance_to_nearest_transit_m", "bus_departures_per_day",
    "number_of_transit_modes_accessible",
    "cycle_infrastructure_density_km_per_km2_ibb_only", "distance_to_nearest_cycle_infrastructure_m_ibb_only",
    "bicycle_parking_count",
    "mean_slope_deg", "mean_absolute_road_grade_pct", "pct_road_length_grade_gt_8pct",
    "road_density_km_per_km2", "intersection_density_km2", "major_road_length_m", "local_road_length_m",
    "green_area_ratio", "residential_area_ratio", "industrial_area_ratio", "landuse_data_coverage_pct",
]

FAMILY_OF_NEW = {
    "has_buildings": "Buildings/Urban Form", "building_coverage_ratio_conditional": "Buildings/Urban Form",
    "major_road_length_m": "Roads", "local_road_length_m": "Roads", "road_density_km_per_km2": "Roads",
    "intersection_density_km2": "Roads", "cycle_accessible_road_density_km_per_km2": "Roads",
    "mean_absolute_road_grade_pct": "Terrain", "pct_road_length_grade_gt_8pct": "Terrain",
    "green_area_ratio": "Land-use/Green Space", "landuse_has_mapped_evidence": "Land-use/Green Space",
    "residential_share_conditional": "Land-use/Green Space", "industrial_share_conditional": "Land-use/Green Space",
}
POI_FEATS = {"hospital_count", "university_count", "school_count", "healthcare_count", "cafe_count",
             "restaurant_count", "bar_pub_count", "supermarket_count", "retail_count", "office_count",
             "tourism_count", "leisure_count", "poi_density_km2", "poi_entropy"}
CYCLING_FEATS = {"cycle_infrastructure_density_km_per_km2_ibb_only", "protected_cycleway_density_km_per_km2_ibb_only",
                  "distance_to_nearest_cycle_infrastructure_m_ibb_only", "distance_to_nearest_bicycle_parking_m",
                  "bicycle_parking_count", "distance_to_nearest_micromobility_parking_m", "micromobility_parking_count"}
TERRAIN_FEATS = {"mean_elevation_m", "mean_slope_deg", "pct_area_slope_3_6deg", "pct_area_slope_6_10deg"}


def family_of(feature: str) -> str:
    if feature in FAMILY_OF_NEW:
        return FAMILY_OF_NEW[feature]
    if feature in POI_FEATS:
        return "POI"
    if feature in CYCLING_FEATS:
        return "Cycling"
    if feature in TERRAIN_FEATS:
        return "Terrain"
    if feature == "population_density_calibrated_km2":
        return "Population"
    return "Transit"


def raw_percentile_profile(raw_df: pd.DataFrame, labels: np.ndarray) -> pd.DataFrame:
    df = raw_df.copy()
    df["cluster"] = labels
    rows = []
    for feat in FULL_PROFILE_FEATURES:
        citywide_vals = df[feat].dropna().to_numpy()
        for cl, g in df.groupby("cluster"):
            vals = g[feat].dropna()
            if len(vals) == 0:
                continue
            median = float(vals.median())
            q1, q3 = float(vals.quantile(0.25)), float(vals.quantile(0.75))
            pct = float(percentileofscore(citywide_vals, median, kind="mean"))
            rows.append({"cluster": int(cl), "feature": feat, "raw_median": median, "raw_q1": q1, "raw_q3": q3,
                         "citywide_percentile_of_cluster_median": round(pct, 1)})
    return pd.DataFrame(rows)


def bss_by_feature(X: np.ndarray, labels: np.ndarray, feature_names: list[str]) -> pd.Series:
    global_mean = X.mean(axis=0)
    bss = np.zeros(X.shape[1])
    for cl in np.unique(labels):
        mask = labels == cl
        cl_mean = X[mask].mean(axis=0)
        bss += mask.sum() * (cl_mean - global_mean) ** 2
    return pd.Series(bss, index=feature_names)


def main() -> None:
    print("=" * 72)
    print("Phase 5B-V2 step 3: candidate-k profiling (raw profiles, family BSS, spatial coherence)")
    print("=" * 72)

    labels_df = pd.read_parquet(V2EF_DIR / "_candidate_k_labels_v2ef.parquet")
    grid_df, X, feature_cols = load_v2ef_matrix()
    raw_df = pd.read_parquet(FEATURES_DIR / "urban_mobility_features_citywide_v2.parquet",
                              columns=["grid_id"] + FULL_PROFILE_FEATURES).merge(grid_df[["grid_id"]], on="grid_id")

    full_graph = build_queen_graph(grid_df)
    w = Queen.from_dataframe(grid_df, use_index=False)

    families = sorted(set(family_of(f) for f in feature_cols))
    family_feature_map = {fam: [c for c in feature_cols if family_of(c) == fam] for fam in families}

    all_results = {}
    for k in CANDIDATE_KS:
        print(f"\n--- k={k} ---")
        labels = labels_df[f"k{k}"].to_numpy()
        sizes = np.bincount(labels)

        profile = raw_percentile_profile(raw_df, labels)
        top_dist = {}
        for cl, g in profile.groupby("cluster"):
            g2 = g.assign(dev=(g["citywide_percentile_of_cluster_median"] - 50).abs()).sort_values("dev", ascending=False)
            top_dist[int(cl)] = g2.head(6)[["feature", "raw_median", "citywide_percentile_of_cluster_median"]].to_dict(orient="records")

        bss = bss_by_feature(X, labels, feature_cols)
        bss_pct = (bss / bss.sum() * 100)
        family_bss = {fam: round(float(bss_pct.reindex(cols).sum()), 2) for fam, cols in family_feature_map.items() if cols}
        top10 = bss_pct.sort_values(ascending=False).head(10).round(2).to_dict()

        frag = fragmentation_diagnostics(full_graph, labels)
        morans = binary_cluster_morans_i(labels, w)
        moran_summary = {cl: {"morans_i": m["morans_i"], "interpretation": m["interpretation"]} for cl, m in morans.items()}

        print(f"  sizes: {sizes.tolist()} ({(sizes/len(labels)*100).round(1).tolist()}%)")
        print(f"  family BSS: {family_bss}")
        print(f"  top5 individual BSS: {dict(list(top10.items())[:5])}")
        for cl, m in moran_summary.items():
            print(f"    {cl}: I={m['morans_i']} ({m['interpretation']})")

        all_results[f"k{k}"] = {
            "cluster_sizes": sizes.tolist(),
            "cluster_pct": (sizes / len(labels) * 100).round(2).tolist(),
            "top_distinguishing_raw_by_cluster": top_dist,
            "family_bss_pct": family_bss,
            "top10_individual_bss_pct": top10,
            "spatial_fragmentation": frag,
            "morans_i_per_cluster": moran_summary,
        }

    out_path = V2EF_DIR / "candidate_k_full_profiles_v2ef.json"
    out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[save] {out_path}")


if __name__ == "__main__":
    main()
