"""Phase 6B-V2: compare V2 e-bike baseline outputs against frozen V1
outputs, and summarize by the frozen V2 k=5 typology (post-hoc
interpretation only -- typology membership never entered scoring).
"""

from __future__ import annotations

import json

import pandas as pd
from scipy.stats import spearmanr

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.mcda_phase6b_v2_scoring import load_data
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda_v2" / "phase6b"
V1_PHASE6B_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda" / "phase6b"
V1_PHASE6C_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda" / "phase6c"
V2_TYPOLOGY_PATH = cfg.PROJECT_ROOT / "analysis" / "clustering_v2_eight_family" / "cluster_assignments_v2ef.parquet"

V1_READINESS_COL = "readiness__balanced_equal_dimensions__T1__uf_sat"
V1_OPPORTUNITY_COL = "opportunity__balanced_equal_dimensions__demand_sat"


def main() -> None:
    print("=" * 72)
    print("Phase 6B-V2: V1 <-> V2 e-bike comparison + typology post-hoc summary")
    print("=" * 72)

    v2_readiness = pd.read_parquet(OUT_DIR / "ebike_readiness_baseline.parquet", columns=["grid_id", "district", "ebike_readiness"])
    v2_opportunity = pd.read_parquet(OUT_DIR / "ebike_opportunity_baseline.parquet", columns=["grid_id", "district", "ebike_opportunity"])
    v1_scores = pd.read_parquet(V1_PHASE6B_DIR / "scenario_scores.parquet", columns=["grid_id", V1_READINESS_COL, V1_OPPORTUNITY_COL])
    v1_consensus = pd.read_parquet(V1_PHASE6C_DIR / "consensus_classes.parquet",
                                     columns=["grid_id", "readiness_consensus_class", "opportunity_consensus_class"])
    v2_consensus = pd.read_parquet(OUT_DIR / "consensus_classes.parquet",
                                     columns=["grid_id", "readiness_consensus_class", "opportunity_consensus_class"])

    merged = v2_readiness.merge(v2_opportunity[["grid_id", "ebike_opportunity"]], on="grid_id") \
        .merge(v1_scores, on="grid_id") \
        .merge(v1_consensus, on="grid_id", suffixes=("_v2_unused", "_v1")) \
        .merge(v2_consensus, on="grid_id", suffixes=("_v1", "_v2"))
    assert len(merged) == 22322

    print("\n[1/4] Score correlation...")
    rho_readiness, _ = spearmanr(merged[V1_READINESS_COL], merged["ebike_readiness"])
    rho_opportunity, _ = spearmanr(merged[V1_OPPORTUNITY_COL], merged["ebike_opportunity"])
    print(f"  Spearman rho readiness (V1 vs V2): {rho_readiness:.4f}")
    print(f"  Spearman rho opportunity (V1 vs V2): {rho_opportunity:.4f}")

    print("\n[2/4] Top-decile overlap...")
    v1_r_top = merged[V1_READINESS_COL] >= merged[V1_READINESS_COL].quantile(0.9)
    v2_r_top = merged["ebike_readiness"] >= merged["ebike_readiness"].quantile(0.9)
    jaccard_readiness = (v1_r_top & v2_r_top).sum() / (v1_r_top | v2_r_top).sum()
    v1_o_top = merged[V1_OPPORTUNITY_COL] >= merged[V1_OPPORTUNITY_COL].quantile(0.9)
    v2_o_top = merged["ebike_opportunity"] >= merged["ebike_opportunity"].quantile(0.9)
    jaccard_opportunity = (v1_o_top & v2_o_top).sum() / (v1_o_top | v2_o_top).sum()
    print(f"  Jaccard top-decile readiness: {jaccard_readiness:.4f}")
    print(f"  Jaccard top-decile opportunity: {jaccard_opportunity:.4f}")

    print("\n[3/4] Consensus-class transition (V1 -> V2)...")
    readiness_transition = pd.crosstab(merged["readiness_consensus_class_v1"], merged["readiness_consensus_class_v2"])
    opportunity_transition = pd.crosstab(merged["opportunity_consensus_class_v1"], merged["opportunity_consensus_class_v2"])
    print("  Readiness consensus class transition:")
    print(readiness_transition.to_string())
    print("\n  Opportunity consensus class transition:")
    print(opportunity_transition.to_string())

    print("\n[4/4] Spatial distribution of change + attribution...")
    df_full = load_data()
    attr_cols = ["intersection_density_km2", "local_road_length_m", "cycle_accessible_road_length_m",
                 "mean_absolute_road_grade_pct", "cycle_infrastructure_density_km_per_km2_ibb_only"]
    merged_attr = merged.merge(df_full[["grid_id"] + attr_cols + ["distance_to_nearest_transit_m", "transit_stops_within_500m"]], on="grid_id")
    merged_attr["readiness_diff"] = merged_attr["ebike_readiness"] - merged_attr[V1_READINESS_COL]
    merged_attr["opportunity_diff"] = merged_attr["ebike_opportunity"] - merged_attr[V1_OPPORTUNITY_COL]

    big_increase = merged_attr.nlargest(500, "readiness_diff")
    big_decrease = merged_attr.nsmallest(500, "readiness_diff")
    attribution = {}
    for feat in attr_cols:
        attribution[feat] = {
            "median_big_readiness_increase_cells": round(float(big_increase[feat].median()), 4),
            "median_big_readiness_decrease_cells": round(float(big_decrease[feat].median()), 4),
            "median_all_cells": round(float(merged_attr[feat].median()), 4),
        }
    print("  Attribution (median feature values among the 500 largest readiness increases vs decreases vs citywide):")
    for feat, v in attribution.items():
        print(f"    {feat}: increase={v['median_big_readiness_increase_cells']} decrease={v['median_big_readiness_decrease_cells']} citywide={v['median_all_cells']}")

    by_district_diff = merged_attr.groupby("district")["readiness_diff"].mean().sort_values(ascending=False)
    print("\n  Top 5 districts by mean readiness increase (V2 - V1):", by_district_diff.head(5).round(3).to_dict())
    print("  Bottom 5 districts by mean readiness change (V2 - V1):", by_district_diff.tail(5).round(3).to_dict())

    comparison_output = {
        "spearman_rho_readiness": round(float(rho_readiness), 4),
        "spearman_rho_opportunity": round(float(rho_opportunity), 4),
        "jaccard_top_decile_readiness": round(float(jaccard_readiness), 4),
        "jaccard_top_decile_opportunity": round(float(jaccard_opportunity), 4),
        "readiness_consensus_transition": readiness_transition.to_dict(),
        "opportunity_consensus_transition": opportunity_transition.to_dict(),
        "attribution_top500_readiness_changes": attribution,
        "by_district_mean_readiness_change": by_district_diff.round(4).to_dict(),
        "note": "V1 reference = readiness__balanced_equal_dimensions__T1__uf_sat / "
                "opportunity__balanced_equal_dimensions__demand_sat (V1's own balanced-scenario baseline variant). "
                "Difference is NOT framed as V2 being 'better' -- only as attributable new information "
                "(Street Connectivity, road grade, simplified transit representation, unchanged cycling "
                "representation) changing where readiness/opportunity concentrate.",
    }
    (OUT_DIR / "v1_v2_ebike_comparison.json").write_text(json.dumps(comparison_output, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[save] {OUT_DIR / 'v1_v2_ebike_comparison.json'}")

    print("\n" + "=" * 72)
    print("Typology post-hoc summary (V2 k=5, interpretation only)")
    print("=" * 72)
    typology = pd.read_parquet(V2_TYPOLOGY_PATH, columns=["grid_id", "cluster"])
    tsum = merged.merge(typology, on="grid_id")
    by_cluster = tsum.groupby("cluster").agg(
        n_cells=("grid_id", "size"),
        mean_readiness=("ebike_readiness", "mean"), mean_opportunity=("ebike_opportunity", "mean"),
    )
    by_cluster["pct_robust_high_readiness"] = tsum.groupby("cluster")["readiness_consensus_class_v2"].apply(lambda x: (x == "ROBUST_HIGH").mean() * 100)
    by_cluster["pct_robust_high_opportunity"] = tsum.groupby("cluster")["opportunity_consensus_class_v2"].apply(lambda x: (x == "ROBUST_HIGH").mean() * 100)
    print(by_cluster.round(3).to_string())

    typology_summary = {"by_cluster": by_cluster.round(4).to_dict(orient="index"),
                         "note": "Typology membership was NEVER used as a scoring input -- this is post-hoc "
                                 "interpretation only, cross-tabulating already-computed scores against the "
                                 "independently-derived V2 k=5 typology."}
    (OUT_DIR / "typology_posthoc_summary.json").write_text(json.dumps(typology_summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[save] {OUT_DIR / 'typology_posthoc_summary.json'}")


if __name__ == "__main__":
    main()
