"""Phase 5: exploratory spatial diagnostics (Moran's I) — diagnostic only,
never used to fit or select a predictive model.

Queen contiguity is used for the spatial weights matrix (a standard,
defensible choice for a regular grid — two cells are neighbors if they
share an edge or a corner).
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
from esda.moran import Moran
from libpysal.weights import Queen


def build_queen_weights(grid: gpd.GeoDataFrame):
    w = Queen.from_dataframe(grid, use_index=False)
    w.transform = "r"
    return w


def morans_i(values: np.ndarray, w) -> dict:
    mi = Moran(values, w, permutations=999)
    return {
        "morans_i": round(float(mi.I), 4),
        "expected_i_under_null": round(float(mi.EI), 4),
        "z_score": round(float(mi.z_sim), 3),
        "p_value_pseudo": round(float(mi.p_sim), 4),
        "n_permutations": 999,
        "interpretation": (
            "significant positive spatial autocorrelation" if mi.p_sim < 0.05 and mi.I > mi.EI
            else "significant negative spatial autocorrelation" if mi.p_sim < 0.05 and mi.I < mi.EI
            else "no significant spatial autocorrelation detected"
        ),
    }


def binary_cluster_morans_i(cluster_labels: np.ndarray, w) -> dict:
    """Moran's I on a 0/1 'belongs to this cluster' indicator, per cluster —
    a defensible way to test spatial clustering tendency of a categorical
    typology without assuming cluster IDs are ordinal."""
    results = {}
    for label in sorted(set(cluster_labels)):
        indicator = (cluster_labels == label).astype(float)
        results[f"cluster_{label}"] = morans_i(indicator, w)
    return results
