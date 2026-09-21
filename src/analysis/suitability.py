"""Phase 5B: suitability computation — normalization, dimension aggregation,
scenario weighting, latent-opportunity gap, and Monte Carlo sensitivity.

All of this is a SUITABILITY framework (potential/appropriateness), never a
demand prediction — this distinction is stated in every output column name
and every map title.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.analysis import suitability_config as scfg


def percentile_rank_normalize(series: pd.Series, higher_is_better: bool) -> pd.Series:
    rank = series.rank(pct=True, method="average")
    return rank if higher_is_better else 1 - rank


def ebike_slope_suitability(slope_deg: pd.Series, floor: float) -> pd.Series:
    comfortable, steep = scfg.EBIKE_SLOPE_COMFORTABLE_DEG, scfg.EBIKE_SLOPE_STEEP_DEG
    out = pd.Series(1.0, index=slope_deg.index)
    ramp = (slope_deg - comfortable) / (steep - comfortable)
    ramp = ramp.clip(lower=0, upper=1)
    out = 1.0 - ramp * (1.0 - floor)
    out[slope_deg <= comfortable] = 1.0
    out[slope_deg >= steep] = floor
    return out


def compute_dimension_scores(df: pd.DataFrame, slope_floor: float = scfg.EBIKE_SLOPE_FLOOR) -> pd.DataFrame:
    scores = pd.DataFrame(index=df.index)
    for dim_name, dim_cfg in scfg.DIMENSIONS.items():
        indicator_scores = []
        for feature, higher_is_better in dim_cfg["indicators"]:
            if dim_name == "terrain_ebike_relevance" and feature == "mean_slope_deg":
                indicator_scores.append(ebike_slope_suitability(df[feature], slope_floor))
            else:
                indicator_scores.append(percentile_rank_normalize(df[feature], higher_is_better))
        scores[dim_name] = pd.concat(indicator_scores, axis=1).mean(axis=1)
    return scores


def compute_scenario_scores(dimension_scores: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=dimension_scores.index)
    for scenario_name, scenario_cfg in scfg.SCENARIOS.items():
        weights = scenario_cfg["weights"]
        out[scenario_name] = sum(dimension_scores[dim] * w for dim, w in weights.items())
    return out


def compute_latent_opportunity(dimension_scores: pd.DataFrame) -> pd.Series:
    """non-infrastructure composite (equal-weight mean of the other 5
    dimensions) MINUS the cycling-infrastructure dimension score. Positive
    values = favorable conditions on every other axis but weak existing
    infrastructure — the literal "latent opportunity" the phase asks for."""
    other_dims = [d for d in scfg.DIMENSIONS if d != "cycling_accessibility_infrastructure"]
    non_infra_composite = dimension_scores[other_dims].mean(axis=1)
    return non_infra_composite - dimension_scores["cycling_accessibility_infrastructure"]


def monte_carlo_sensitivity(dimension_scores: pd.DataFrame) -> dict:
    rng = np.random.default_rng(scfg.MONTE_CARLO_RANDOM_STATE)
    dims = list(scfg.DIMENSIONS.keys())
    n_cells = len(dimension_scores)
    weight_draws = rng.dirichlet(np.ones(len(dims)), size=scfg.N_MONTE_CARLO_DRAWS)

    scores_matrix = np.zeros((scfg.N_MONTE_CARLO_DRAWS, n_cells))
    dim_matrix = dimension_scores[dims].to_numpy()
    for i, w in enumerate(weight_draws):
        scores_matrix[i] = dim_matrix @ w

    mean_score = scores_matrix.mean(axis=0)
    std_score = scores_matrix.std(axis=0)
    cv_score = np.where(mean_score > 0, std_score / mean_score, np.nan)

    top_decile_threshold_per_draw = np.quantile(scores_matrix, scfg.TOP_DECILE_THRESHOLD, axis=1, keepdims=True)
    in_top_decile = scores_matrix >= top_decile_threshold_per_draw
    pct_draws_in_top_decile = in_top_decile.mean(axis=0) * 100

    return {
        "mean_score": pd.Series(mean_score, index=dimension_scores.index),
        "std_score": pd.Series(std_score, index=dimension_scores.index),
        "coefficient_of_variation": pd.Series(cv_score, index=dimension_scores.index),
        "pct_draws_in_top_decile": pd.Series(pct_draws_in_top_decile, index=dimension_scores.index),
        "n_draws": scfg.N_MONTE_CARLO_DRAWS,
    }
