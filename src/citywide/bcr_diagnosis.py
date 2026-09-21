"""Phase 5C step 0: diagnose why building_coverage_ratio dominates cluster
separation under the Phase 5A log1p + RobustScaler treatment."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

CLUSTER_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering_v2"


def main() -> None:
    master = pd.read_parquet(cfg.DATA_PROCESSED / "features" / "urban_mobility_features_citywide.parquet")
    raw = master["building_coverage_ratio"]

    n = len(raw)
    zero_mask = raw == 0
    nonzero = raw[~zero_mask]

    percentiles = [50, 75, 90, 95, 97.5, 99, 99.5, 99.9, 100]
    raw_pcts = {f"p{p}": float(raw.quantile(p / 100)) for p in percentiles}
    nonzero_pcts = {f"p{p}": float(nonzero.quantile(p / 100)) for p in percentiles}

    log1p_vals = np.log1p(raw)
    log1p_pcts = {f"p{p}": float(np.quantile(log1p_vals, p / 100)) for p in percentiles}

    scaler = RobustScaler()
    scaled_vals = scaler.fit_transform(log1p_vals.to_numpy().reshape(-1, 1)).ravel()
    scaled_pcts = {f"p{p}": float(np.quantile(scaled_vals, p / 100)) for p in percentiles}

    diagnosis = {
        "n_cells": n,
        "zero_mass": {"n_zero": int(zero_mask.sum()), "pct_zero": round(float(zero_mask.mean() * 100), 2)},
        "raw_distribution": {
            "min": float(raw.min()), "max": float(raw.max()), "mean": float(raw.mean()), "std": float(raw.std()),
            "median": float(raw.median()), "iqr": float(raw.quantile(0.75) - raw.quantile(0.25)),
            "percentiles_all_cells": raw_pcts, "percentiles_nonzero_cells_only": nonzero_pcts,
        },
        "log1p_transformed": {
            "median": float(np.median(log1p_vals)), "iqr": float(np.quantile(log1p_vals, 0.75) - np.quantile(log1p_vals, 0.25)),
            "percentiles": log1p_pcts,
        },
        "log1p_plus_robustscaler_final": {
            "median": float(np.median(scaled_vals)), "iqr_used_by_scaler": float(scaler.scale_[0]),
            "center_used_by_scaler": float(scaler.center_[0]), "percentiles": scaled_pcts,
            "max_scaled_value": float(scaled_vals.max()),
        },
        "explanation": (
            f"65.2% of cells are exactly zero, so the log1p-transformed distribution's IQR is tiny "
            f"({float(np.quantile(log1p_vals, 0.75) - np.quantile(log1p_vals, 0.25)):.5f}) because both Q1 and "
            f"most of Q3 sit at or near zero. RobustScaler divides by this near-zero IQR "
            f"({float(scaler.scale_[0]):.5f}), so the minority of cells with real building coverage "
            f"(up to raw {float(raw.max()):.3f}, i.e. 67.5% coverage) get inflated into extreme scaled values "
            f"(max scaled = {float(scaled_vals.max()):.1f}). This is a mechanical consequence of applying a "
            "median/IQR-based robust scaler to a variable whose IQR is compressed by a large exact-zero mass, "
            "not a data error."
        ),
    }

    CLUSTER_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLUSTER_DIR / "bcr_diagnosis.json"
    out_path.write_text(json.dumps(diagnosis, indent=2, default=str), encoding="utf-8")
    print(json.dumps(diagnosis, indent=2, default=str))
    print(f"\n[save] {out_path}")


if __name__ == "__main__":
    main()
