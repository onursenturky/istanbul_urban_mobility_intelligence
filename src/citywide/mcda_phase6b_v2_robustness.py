"""Phase 6B-V2: robustness / consensus classes over the 6 sensitivity
variants (BASELINE + 5 alternatives), for Readiness and Opportunity
separately. Mirrors V1's Phase 6C consensus-class taxonomy exactly
(pct_top_decile thresholds), applied to this phase's smaller, deliberately
non-combinatorial variant set. Agreement here means robustness to the
tested assumptions, NOT empirical validation.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "mcda_v2" / "phase6b"


def cell_stability(scores: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    vals = scores[cols].to_numpy()
    n_cells = vals.shape[0]
    ranks = np.apply_along_axis(lambda col: rankdata(col) / n_cells, 0, vals)
    thresholds = np.quantile(vals, 0.9, axis=0)
    top_decile = vals >= thresholds
    return pd.DataFrame({
        "grid_id": scores["grid_id"], "district": scores["district"],
        "mean_score": vals.mean(axis=1), "std_score": vals.std(axis=1),
        "min_score": vals.min(axis=1), "max_score": vals.max(axis=1),
        "mean_rank_pct": ranks.mean(axis=1), "std_rank_pct": ranks.std(axis=1),
        "n_top_decile": top_decile.sum(axis=1), "pct_top_decile": top_decile.mean(axis=1) * 100,
    })


def consensus_class(pct_top_decile: pd.Series) -> pd.Series:
    conditions = [
        pct_top_decile >= 100, (pct_top_decile >= 75) & (pct_top_decile < 100),
        (pct_top_decile >= 25) & (pct_top_decile < 75), (pct_top_decile > 0) & (pct_top_decile < 25),
        pct_top_decile == 0,
    ]
    choices = ["ROBUST_HIGH", "FREQUENT_HIGH", "CONDITIONAL_HIGH", "RARE_HIGH", "NEVER_HIGH"]
    return pd.Series(np.select(conditions, choices, default="NEVER_HIGH"), index=pct_top_decile.index)


def main() -> None:
    print("=" * 72)
    print("Phase 6B-V2: robustness / consensus classes")
    print("=" * 72)

    scores = pd.read_parquet(OUT_DIR / "sensitivity_variant_scores.parquet")
    readiness_cols = [c for c in scores.columns if c.startswith("readiness__")]
    opportunity_cols = [c for c in scores.columns if c.startswith("opportunity__")]
    print(f"Readiness variants: {readiness_cols}")
    print(f"Opportunity variants: {opportunity_cols}")

    print("\n[1/3] Readiness robustness...")
    readiness_stab = cell_stability(scores, readiness_cols)
    readiness_stab["consensus_class"] = consensus_class(readiness_stab["pct_top_decile"])
    readiness_stab.to_parquet(OUT_DIR / "readiness_robustness.parquet")
    print(readiness_stab["consensus_class"].value_counts().to_string())
    print(f"  saved {OUT_DIR / 'readiness_robustness.parquet'}")

    print("\n[2/3] Opportunity robustness...")
    opportunity_stab = cell_stability(scores, opportunity_cols)
    opportunity_stab["consensus_class"] = consensus_class(opportunity_stab["pct_top_decile"])
    opportunity_stab.to_parquet(OUT_DIR / "opportunity_robustness.parquet")
    print(opportunity_stab["consensus_class"].value_counts().to_string())
    print(f"  saved {OUT_DIR / 'opportunity_robustness.parquet'}")

    print("\n[3/3] Combined consensus_classes.parquet + spearman agreement summary...")
    consensus = scores[["grid_id", "district"]].copy()
    consensus["readiness_consensus_class"] = readiness_stab["consensus_class"].to_numpy()
    consensus["readiness_pct_top_decile"] = readiness_stab["pct_top_decile"].to_numpy()
    consensus["readiness_mean"] = readiness_stab["mean_score"].to_numpy()
    consensus["readiness_std"] = readiness_stab["std_score"].to_numpy()
    consensus["opportunity_consensus_class"] = opportunity_stab["consensus_class"].to_numpy()
    consensus["opportunity_pct_top_decile"] = opportunity_stab["pct_top_decile"].to_numpy()
    consensus["opportunity_mean"] = opportunity_stab["mean_score"].to_numpy()
    consensus["opportunity_std"] = opportunity_stab["std_score"].to_numpy()
    consensus.to_parquet(OUT_DIR / "consensus_classes.parquet")
    print(f"  saved {OUT_DIR / 'consensus_classes.parquet'}")

    readiness_corr = scores[readiness_cols].corr(method="spearman")
    opportunity_corr = scores[opportunity_cols].corr(method="spearman")

    def jaccard_matrix(cols):
        masks = {c: (scores[c] >= scores[c].quantile(0.9)) for c in cols}
        mat = pd.DataFrame(index=cols, columns=cols, dtype=float)
        for a in cols:
            for b in cols:
                inter = (masks[a] & masks[b]).sum()
                union = (masks[a] | masks[b]).sum()
                mat.loc[a, b] = inter / union if union else 0.0
        return mat

    readiness_jaccard = jaccard_matrix(readiness_cols)
    opportunity_jaccard = jaccard_matrix(opportunity_cols)

    n_robust_readiness = int((readiness_stab["consensus_class"] == "ROBUST_HIGH").sum())
    n_robust_opportunity = int((opportunity_stab["consensus_class"] == "ROBUST_HIGH").sum())
    n_conditional_readiness = int((readiness_stab["consensus_class"] == "CONDITIONAL_HIGH").sum())
    n_conditional_opportunity = int((opportunity_stab["consensus_class"] == "CONDITIONAL_HIGH").sum())

    print(f"\n  ROBUST_HIGH: readiness={n_robust_readiness} ({n_robust_readiness/len(scores)*100:.2f}%), "
          f"opportunity={n_robust_opportunity} ({n_robust_opportunity/len(scores)*100:.2f}%)")
    print(f"  CONDITIONAL_HIGH: readiness={n_conditional_readiness}, opportunity={n_conditional_opportunity}")

    summary = {
        "readiness_spearman_matrix": readiness_corr.round(4).to_dict(),
        "opportunity_spearman_matrix": opportunity_corr.round(4).to_dict(),
        "readiness_min_pairwise_spearman": round(float(readiness_corr.where(~np.eye(len(readiness_corr), dtype=bool)).min().min()), 4),
        "opportunity_min_pairwise_spearman": round(float(opportunity_corr.where(~np.eye(len(opportunity_corr), dtype=bool)).min().min()), 4),
        "readiness_jaccard_matrix": readiness_jaccard.round(4).to_dict(),
        "opportunity_jaccard_matrix": opportunity_jaccard.round(4).to_dict(),
        "readiness_consensus_class_counts": readiness_stab["consensus_class"].value_counts().to_dict(),
        "opportunity_consensus_class_counts": opportunity_stab["consensus_class"].value_counts().to_dict(),
        "note": "Agreement across the tested variants means robustness to THESE SPECIFIC assumptions -- it is not "
                "an empirical validation of readiness/opportunity against any ground truth.",
    }
    (OUT_DIR / "robustness_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[save] {OUT_DIR / 'robustness_summary.json'}")


if __name__ == "__main__":
    main()
