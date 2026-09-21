"""Phase 5A: clustering algorithm comparison and quantitative k selection.

Three defensible algorithms are compared across k=2..10:
  - KMeans (hard partitional, assumes roughly spherical clusters)
  - Agglomerative (Ward linkage; captures nested/hierarchical structure)
  - Gaussian Mixture (soft/probabilistic; allows elliptical clusters)

Selection is quantitative, not visual: for each (algorithm, k) we compute
silhouette score (higher better, primary criterion — comparable across all
three algorithms), Davies-Bouldin index (lower better), and Calinski-Harabasz
index (higher better). GMM additionally reports BIC (lower better) since
that is its native model-selection criterion. The winning (algorithm, k) is
the one maximizing silhouette score; the other indices are reported as
corroborating evidence, not overridden by visual "elbow" inspection.

We also compare clustering on the full screened/scaled feature space vs. on
the top-N PCA components (N = enough for 85% cumulative explained variance),
and report which representation gives the better silhouette score.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.mixture import GaussianMixture

K_RANGE = range(2, 11)
PCA_VARIANCE_TARGET = 0.85
RANDOM_STATE = 42


def pca_diagnostics(X: pd.DataFrame) -> dict:
    pca = PCA(random_state=RANDOM_STATE)
    pca.fit(X)
    cum_var = np.cumsum(pca.explained_variance_ratio_)
    n_components_85 = int(np.searchsorted(cum_var, PCA_VARIANCE_TARGET) + 1)
    return {
        "n_original_features": X.shape[1],
        "explained_variance_ratio_first_10": [round(float(v), 4) for v in pca.explained_variance_ratio_[:10]],
        "cumulative_variance_first_10": [round(float(v), 4) for v in cum_var[:10]],
        "n_components_for_85pct_variance": n_components_85,
    }, pca, n_components_85


def _evaluate(X: np.ndarray, labels: np.ndarray) -> dict:
    if len(set(labels)) < 2:
        return {"silhouette": float("nan"), "davies_bouldin": float("nan"), "calinski_harabasz": float("nan")}
    return {
        "silhouette": round(float(silhouette_score(X, labels)), 4),
        "davies_bouldin": round(float(davies_bouldin_score(X, labels)), 4),
        "calinski_harabasz": round(float(calinski_harabasz_score(X, labels)), 1),
    }


def compare_algorithms(X: pd.DataFrame, representation_label: str) -> pd.DataFrame:
    Xv = X.values
    rows = []
    for k in K_RANGE:
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10).fit(Xv)
        rows.append({"representation": representation_label, "algorithm": "kmeans", "k": k, **_evaluate(Xv, km.labels_)})

        agg = AgglomerativeClustering(n_clusters=k, linkage="ward").fit(Xv)
        rows.append({"representation": representation_label, "algorithm": "agglomerative_ward", "k": k, **_evaluate(Xv, agg.labels_)})

        gmm = GaussianMixture(n_components=k, random_state=RANDOM_STATE, n_init=5).fit(Xv)
        gmm_labels = gmm.predict(Xv)
        row = {"representation": representation_label, "algorithm": "gaussian_mixture", "k": k, **_evaluate(Xv, gmm_labels)}
        row["bic"] = round(float(gmm.bic(Xv)), 1)
        rows.append(row)
    return pd.DataFrame(rows)


DEGENERACY_MAX_CLUSTER_SHARE = 0.80  # if the largest cluster exceeds this share of all cells, treat as degenerate
SILHOUETTE_TIEBREAK_TOLERANCE = 0.15  # secondary pick must stay within this much silhouette of the global max


def select_best(comparison_df: pd.DataFrame, cluster_size_lookup=None) -> dict:
    """Primary rule: global maximum silhouette. Pre-declared secondary rule,
    applied ONLY if the primary pick is degenerate (one cluster holding over
    DEGENERACY_MAX_CLUSTER_SHARE of all cells — not useful as a 'typology'):
    among ALL tested (representation, algorithm) combinations at k >= 3,
    take the one maximizing Calinski-Harabasz, provided its silhouette is
    within SILHOUETTE_TIEBREAK_TOLERANCE of the global max. This is a
    quantitative tie-break fixed before inspecting cluster interpretations,
    not a visual/preference-based override; it is deliberately not
    restricted to the primary pick's own algorithm, since the point of the
    tie-break is to find the best-corroborated richer segmentation
    wherever it occurs."""
    valid = comparison_df.dropna(subset=["silhouette"])
    primary = valid.loc[valid["silhouette"].idxmax()]
    result = {
        "primary_pick": {
            "representation": primary["representation"], "algorithm": primary["algorithm"], "k": int(primary["k"]),
            "silhouette": float(primary["silhouette"]), "davies_bouldin": float(primary["davies_bouldin"]),
            "calinski_harabasz": float(primary["calinski_harabasz"]),
        },
        "selection_rule": (
            "Primary: global maximum silhouette. Secondary (pre-declared, applied only if primary is "
            f"degenerate, i.e. largest cluster > {DEGENERACY_MAX_CLUSTER_SHARE:.0%} of cells): across ALL "
            "tested (representation, algorithm) combinations, take the k >= 3 maximizing Calinski-Harabasz, "
            f"provided its silhouette is within {SILHOUETTE_TIEBREAK_TOLERANCE} of the global maximum."
        ),
    }

    is_degenerate = None
    if cluster_size_lookup is not None:
        sizes = cluster_size_lookup(primary["representation"], primary["algorithm"], int(primary["k"]))
        largest_share = max(sizes) / sum(sizes)
        is_degenerate = largest_share > DEGENERACY_MAX_CLUSTER_SHARE
        result["primary_pick"]["largest_cluster_share"] = round(float(largest_share), 3)
        result["primary_pick_is_degenerate"] = is_degenerate

    if is_degenerate:
        candidates = valid[
            (valid["k"] >= 3)
            & (valid["silhouette"] >= primary["silhouette"] - SILHOUETTE_TIEBREAK_TOLERANCE)
        ]
        if len(candidates):
            secondary = candidates.loc[candidates["calinski_harabasz"].idxmax()]
            result["final"] = {
                "representation": secondary["representation"], "algorithm": secondary["algorithm"], "k": int(secondary["k"]),
                "silhouette": float(secondary["silhouette"]), "davies_bouldin": float(secondary["davies_bouldin"]),
                "calinski_harabasz": float(secondary["calinski_harabasz"]),
                "chosen_via": "secondary_calinski_harabasz_tiebreak",
            }
            return {**result, **result["final"]}

    result["final"] = {**result["primary_pick"], "chosen_via": "primary_global_silhouette_max"}
    return {**result, **result["final"]}


def fit_final_clustering(X: pd.DataFrame, algorithm: str, k: int) -> np.ndarray:
    Xv = X.values
    if algorithm == "kmeans":
        model = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10).fit(Xv)
        return model.labels_
    if algorithm == "agglomerative_ward":
        model = AgglomerativeClustering(n_clusters=k, linkage="ward").fit(Xv)
        return model.labels_
    if algorithm == "gaussian_mixture":
        model = GaussianMixture(n_components=k, random_state=RANDOM_STATE, n_init=5).fit(Xv)
        return model.predict(Xv)
    raise ValueError(f"unknown algorithm: {algorithm}")
