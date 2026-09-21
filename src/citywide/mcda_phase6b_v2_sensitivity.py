"""Phase 6B-V2: controlled sensitivity experiment (6 named variants, not a
combinatorial scenario grid) -- robustness testing, not optimization.

Variants:
  BASELINE                  reduced transit + Street Connectivity + road grade (as scored in mcda_phase6b_v2_scoring.py)
  NO_STREET_CONNECTIVITY    Street Connectivity dropped from Readiness, remaining 4 dims renormalized
  NO_ROAD_GRADE             Terrain uses V1's original 3-criterion treatment (no mean_absolute_road_grade_pct)
  EXPANDED_TRANSIT          Transit Accessibility uses V1's original 9-criterion representation
  ALTERNATIVE_CYCLING       Cycling Readiness's primary infra criterion swapped to pct_road_network_with_cycle_infrastructure
  WEIGHT_PERTURBATION       single deterministic +/-20% dimension-weight tilt (Demand -20%, Cycling Readiness +20%,
                             Street Connectivity +20%, Physical Feasibility -20%, Transit unchanged) -- NOT a search
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from itertools import combinations
from scipy.stats import rankdata, spearmanr

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.mcda_phase6b_v2_scoring import (
    BASELINE_DIMENSION_WEIGHTS, compute_cycling, compute_demand, compute_opportunity,
    compute_readiness, compute_street_connectivity, compute_terrain, compute_transit,
    compute_transit_expanded, load_data,
)
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda_v2" / "phase6b"

WEIGHT_PERTURBATION_VECTOR = {
    "Demand/Activity": 0.16, "Transit Accessibility": 0.20, "Cycling Readiness": 0.24,
    "Street Connectivity": 0.24, "Physical Feasibility": 0.16,
}
assert abs(sum(WEIGHT_PERTURBATION_VECTOR.values()) - 1.0) < 1e-9


def main() -> None:
    print("=" * 72)
    print("Phase 6B-V2: controlled sensitivity experiment (6 named variants)")
    print("=" * 72)

    df = load_data()
    demand, _ = compute_demand(df)
    transit_reduced, _ = compute_transit(df)
    transit_expanded = compute_transit_expanded(df)
    cycling_readiness_baseline, cycling_gap_baseline, _ = compute_cycling(df, "cycle_infrastructure_density_km_per_km2_ibb_only")
    cycling_readiness_alt, cycling_gap_alt, _ = compute_cycling(df, "pct_road_network_with_cycle_infrastructure")
    street, _ = compute_street_connectivity(df)
    terrain_with_grade, _ = compute_terrain(df, include_grade=True)
    terrain_no_grade, _ = compute_terrain(df, include_grade=False)

    variants = {}

    def build_variant(name, dims, weights, demand_col, gap_col):
        readiness = compute_readiness(dims, weights)
        opportunity, alpha = compute_opportunity(demand_col, gap_col, weights)
        variants[name] = {"readiness": readiness, "opportunity": opportunity, "alpha": alpha}
        print(f"  {name}: readiness mean={readiness.mean():.4f} median={readiness.median():.4f} | "
              f"opportunity mean={opportunity.mean():.4f} pct_zero={(opportunity==0).mean()*100:.1f}%")

    base_dims = {"Demand/Activity": demand, "Transit Accessibility": transit_reduced,
                 "Cycling Readiness": cycling_readiness_baseline, "Street Connectivity": street,
                 "Physical Feasibility": terrain_with_grade}

    print("\nFitting 6 variants...")
    build_variant("BASELINE", base_dims, BASELINE_DIMENSION_WEIGHTS, demand, cycling_gap_baseline)

    no_street_weights = {k: v for k, v in BASELINE_DIMENSION_WEIGHTS.items() if k != "Street Connectivity"}
    w_sum = sum(no_street_weights.values())
    no_street_weights = {k: v / w_sum for k, v in no_street_weights.items()}
    no_street_dims = {k: v for k, v in base_dims.items() if k != "Street Connectivity"}
    build_variant("NO_STREET_CONNECTIVITY", no_street_dims, no_street_weights, demand, cycling_gap_baseline)

    no_grade_dims = {**base_dims, "Physical Feasibility": terrain_no_grade}
    build_variant("NO_ROAD_GRADE", no_grade_dims, BASELINE_DIMENSION_WEIGHTS, demand, cycling_gap_baseline)

    expanded_transit_dims = {**base_dims, "Transit Accessibility": transit_expanded}
    build_variant("EXPANDED_TRANSIT", expanded_transit_dims, BASELINE_DIMENSION_WEIGHTS, demand, cycling_gap_baseline)

    alt_cycling_dims = {**base_dims, "Cycling Readiness": cycling_readiness_alt}
    build_variant("ALTERNATIVE_CYCLING", alt_cycling_dims, BASELINE_DIMENSION_WEIGHTS, demand, cycling_gap_alt)

    build_variant("WEIGHT_PERTURBATION", base_dims, WEIGHT_PERTURBATION_VECTOR, demand, cycling_gap_baseline)

    # ---- Assemble output table ----
    out = pd.DataFrame({"grid_id": df["grid_id"], "district": df["district"]})
    for name, v in variants.items():
        out[f"readiness__{name}"] = v["readiness"].to_numpy()
        out[f"opportunity__{name}"] = v["opportunity"].to_numpy()
    out.to_parquet(OUT_DIR / "sensitivity_variant_scores.parquet")
    print(f"\n[save] {OUT_DIR / 'sensitivity_variant_scores.parquet'}")

    # ---- Pairwise comparison vs BASELINE ----
    print("\nComparing each variant against BASELINE...")
    readiness_cols = [f"readiness__{n}" for n in variants]
    opportunity_cols = [f"opportunity__{n}" for n in variants]

    def vs_baseline(cols, label):
        rows = []
        base_col = f"{label}__BASELINE"
        base_top_decile = out[base_col] >= out[base_col].quantile(0.9)
        for c in cols:
            if c == base_col:
                continue
            rho, _ = spearmanr(out[base_col], out[c])
            top_decile = out[c] >= out[c].quantile(0.9)
            inter = (base_top_decile & top_decile).sum()
            union = (base_top_decile | top_decile).sum()
            jaccard = inter / union if union else 0.0
            mad = float((out[base_col] - out[c]).abs().mean())
            rows.append({"variant": c.replace(f"{label}__", ""), "spearman_rho_vs_baseline": round(float(rho), 4),
                         "jaccard_top_decile_vs_baseline": round(float(jaccard), 4), "mean_abs_diff_vs_baseline": round(mad, 4)})
        return pd.DataFrame(rows).sort_values("spearman_rho_vs_baseline")

    readiness_sens = vs_baseline(readiness_cols, "readiness")
    opportunity_sens = vs_baseline(opportunity_cols, "opportunity")
    print("\nReadiness sensitivity vs BASELINE:")
    print(readiness_sens.to_string(index=False))
    print("\nOpportunity sensitivity vs BASELINE:")
    print(opportunity_sens.to_string(index=False))

    readiness_sens["target"] = "readiness"
    opportunity_sens["target"] = "opportunity"
    sensitivity_summary = pd.concat([readiness_sens, opportunity_sens], ignore_index=True)
    sensitivity_summary.to_csv(OUT_DIR / "sensitivity_summary.csv", index=False)
    print(f"\n[save] {OUT_DIR / 'sensitivity_summary.csv'}")

    strongest_readiness = readiness_sens.iloc[0]
    strongest_opportunity = opportunity_sens.iloc[0]
    print(f"\nStrongest sensitivity driver (Readiness): {strongest_readiness['variant']} "
          f"(rho={strongest_readiness['spearman_rho_vs_baseline']}, jaccard={strongest_readiness['jaccard_top_decile_vs_baseline']})")
    print(f"Strongest sensitivity driver (Opportunity): {strongest_opportunity['variant']} "
          f"(rho={strongest_opportunity['spearman_rho_vs_baseline']}, jaccard={strongest_opportunity['jaccard_top_decile_vs_baseline']})")

    meta = {
        "variants_tested": list(variants.keys()),
        "weight_perturbation_vector": WEIGHT_PERTURBATION_VECTOR,
        "alpha_by_variant": {n: round(v["alpha"], 4) for n, v in variants.items()},
        "strongest_sensitivity_driver_readiness": strongest_readiness.to_dict(),
        "strongest_sensitivity_driver_opportunity": strongest_opportunity.to_dict(),
    }
    (OUT_DIR / "sensitivity_meta.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    print(f"[save] {OUT_DIR / 'sensitivity_meta.json'}")


if __name__ == "__main__":
    main()
