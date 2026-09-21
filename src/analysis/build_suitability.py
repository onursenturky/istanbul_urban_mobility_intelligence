"""Phase 5B orchestrator: E-bike deployment SUITABILITY framework.

This is a transparent multi-criteria SUITABILITY score, never a demand
prediction. Run from the project root:
    .venv/bin/python -m src.analysis.build_suitability
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.analysis import suitability_config as scfg
from src.analysis.spatial_diagnostics import build_queen_weights, morans_i
from src.analysis.suitability import (
    compute_dimension_scores,
    compute_latent_opportunity,
    compute_scenario_scores,
    ebike_slope_suitability,
    monte_carlo_sensitivity,
)
from src.utils import config as cfg

SUITABILITY_DIR = cfg.PROJECT_ROOT / "data" / "processed" / "suitability"


def load_features() -> gpd.GeoDataFrame:
    gdf = gpd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features.parquet")
    assert len(gdf) == 514 and gdf["grid_id"].is_unique
    return gdf


def _map_extent(districts_gdf: gpd.GeoDataFrame):
    minx, miny, maxx, maxy = districts_gdf.total_bounds
    pad_x, pad_y = (maxx - minx) * 0.03, (maxy - miny) * 0.03
    return (minx - pad_x, maxx + pad_x, miny - pad_y, maxy + pad_y)


def make_dimension_panel(grid: gpd.GeoDataFrame, dimension_scores: pd.DataFrame, districts_gdf, extent) -> str:
    dims = list(scfg.DIMENSIONS.keys())
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    for ax, dim in zip(axes.flat, dims):
        plot_gdf = grid.assign(_v=dimension_scores[dim].values)
        plot_gdf.plot(column="_v", cmap="viridis", vmin=0, vmax=1, ax=ax, legend=True, edgecolor="#666666", linewidth=0.05)
        districts_gdf.boundary.plot(ax=ax, linewidth=1.0, color="black", zorder=3)
        ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
        ax.set_title(dim.replace("_", " "), fontsize=11)
        ax.set_axis_off()
    fig.suptitle("Suitability dimension scores (0-1, percentile-based)", fontsize=14)
    out = cfg.OUTPUTS_MAPS / "suitability_dimensions.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def make_single_map(grid: gpd.GeoDataFrame, values: pd.Series, title: str, filename: str, districts_gdf, extent, cmap="viridis", **kwargs) -> str:
    fig, ax = plt.subplots(figsize=(10, 10))
    plot_gdf = grid.assign(_v=values.values)
    plot_gdf.plot(column="_v", cmap=cmap, ax=ax, legend=True, edgecolor="#666666", linewidth=0.1, **kwargs)
    districts_gdf.boundary.plot(ax=ax, linewidth=1.4, color="black", zorder=3)
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_title(title)
    ax.set_axis_off()
    out = cfg.OUTPUTS_MAPS / filename
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def main() -> None:
    print("=" * 72)
    print("Phase 5B — E-bike Deployment SUITABILITY Framework (not demand)")
    print("=" * 72)
    SUITABILITY_DIR.mkdir(parents=True, exist_ok=True)

    features_df = load_features()
    dimension_scores = compute_dimension_scores(features_df)
    scenario_scores = compute_scenario_scores(dimension_scores)
    latent_opportunity = compute_latent_opportunity(dimension_scores)

    # --- Sensitivity 1: e-bike-adjusted vs conventional slope penalty ---
    conventional_terrain = ebike_slope_suitability(features_df["mean_slope_deg"], scfg.CONVENTIONAL_SLOPE_FLOOR)
    dims_conventional = dimension_scores.copy()
    dims_conventional["terrain_ebike_relevance"] = conventional_terrain
    scenario_scores_conventional = compute_scenario_scores(dims_conventional)
    slope_sensitivity = {}
    for scenario in scfg.SCENARIOS:
        rho, _ = spearmanr(scenario_scores[scenario], scenario_scores_conventional[scenario])
        slope_sensitivity[scenario] = {
            "spearman_rho_ebike_vs_conventional_slope_penalty": round(float(rho), 4),
        }

    # --- Sensitivity 2: Monte Carlo weight perturbation ---
    mc = monte_carlo_sensitivity(dimension_scores)

    # --- Cross-scenario rank stability ---
    scenario_rank_corr = scenario_scores.corr(method="spearman")

    # --- Spatial autocorrelation ---
    w = build_queen_weights(features_df[["grid_id", "geometry"]])
    spatial_results = {}
    for scenario in scfg.SCENARIOS:
        spatial_results[scenario] = morans_i(scenario_scores[scenario].to_numpy(), w)
    spatial_results["latent_opportunity"] = morans_i(latent_opportunity.to_numpy(), w)
    for dim in scfg.DIMENSIONS:
        spatial_results[f"dimension__{dim}"] = morans_i(dimension_scores[dim].to_numpy(), w)

    # --- Save data outputs ---
    out_gdf = features_df[["grid_id", "district", "geometry"]].copy()
    for dim in scfg.DIMENSIONS:
        out_gdf[f"dim_{dim}"] = dimension_scores[dim].values
    for scenario in scfg.SCENARIOS:
        out_gdf[f"suitability_{scenario}"] = scenario_scores[scenario].values
    out_gdf["latent_opportunity_score"] = latent_opportunity.values
    out_gdf["mc_mean_score"] = mc["mean_score"].values
    out_gdf["mc_coefficient_of_variation"] = mc["coefficient_of_variation"].values
    out_gdf["mc_pct_draws_in_top_decile"] = mc["pct_draws_in_top_decile"].values
    out_gdf.to_parquet(SUITABILITY_DIR / "suitability_scores.parquet")

    with open(SUITABILITY_DIR / "suitability_config_used.json", "w", encoding="utf-8") as f:
        json.dump({
            "dimensions": {k: {"description": v["description"], "indicators": v["indicators"]} for k, v in scfg.DIMENSIONS.items()},
            "ebike_slope_penalty": {
                "comfortable_deg": scfg.EBIKE_SLOPE_COMFORTABLE_DEG, "steep_deg": scfg.EBIKE_SLOPE_STEEP_DEG,
                "floor": scfg.EBIKE_SLOPE_FLOOR, "conventional_comparison_floor": scfg.CONVENTIONAL_SLOPE_FLOOR,
            },
            "scenarios": scfg.SCENARIOS,
            "normalization": "percentile_rank (0-1), direction per indicator as declared above",
        }, f, indent=2, ensure_ascii=False)

    sensitivity_report = {
        "slope_penalty_sensitivity_ebike_vs_conventional": slope_sensitivity,
        "monte_carlo": {
            "n_draws": mc["n_draws"],
            "mean_coefficient_of_variation_across_cells": round(float(mc["coefficient_of_variation"].mean()), 4),
            "max_coefficient_of_variation": round(float(mc["coefficient_of_variation"].max()), 4),
            "interpretation": "Coefficient of variation of a cell's overall score across 1000 random weight draws — "
                               "higher values mean that cell's ranking is more sensitive to which weights are chosen.",
        },
        "cross_scenario_rank_correlation_spearman": scenario_rank_corr.round(4).to_dict(),
        "spatial_autocorrelation": spatial_results,
    }
    with open(SUITABILITY_DIR / "sensitivity_report.json", "w", encoding="utf-8") as f:
        json.dump(sensitivity_report, f, indent=2, default=str)

    # --- Maps ---
    districts_gdf = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")
    extent = _map_extent(districts_gdf)
    grid = features_df[["grid_id", "geometry"]]

    dim_map = make_dimension_panel(grid, dimension_scores, districts_gdf, extent)
    scenario_maps = {}
    for scenario, cfg_s in scfg.SCENARIOS.items():
        scenario_maps[scenario] = make_single_map(
            grid, scenario_scores[scenario], f"E-bike deployment SUITABILITY (not demand)\nScenario {scenario}: {cfg_s['description'][:60]}",
            f"suitability_scenario_{scenario}.png", districts_gdf, extent,
        )
    latent_map = make_single_map(
        grid, latent_opportunity, "Latent opportunity: favorable conditions, weak cycling infrastructure\n(positive = opportunity gap)",
        "suitability_latent_opportunity.png", districts_gdf, extent, cmap="RdYlGn", vmin=-float(latent_opportunity.abs().max()), vmax=float(latent_opportunity.abs().max()),
    )
    sensitivity_map = make_single_map(
        grid, mc["coefficient_of_variation"], "Weight-sensitivity: coefficient of variation across 1000 random weight draws\n(higher = ranking less robust to weight choice)",
        "suitability_sensitivity_stability.png", districts_gdf, extent, cmap="magma",
    )

    print("\n--- SLOPE PENALTY SENSITIVITY (e-bike vs conventional) ---")
    print(json.dumps(slope_sensitivity, indent=2))
    print("\n--- MONTE CARLO SENSITIVITY ---")
    print(json.dumps(sensitivity_report["monte_carlo"], indent=2))
    print("\n--- CROSS-SCENARIO RANK CORRELATION ---")
    print(scenario_rank_corr.round(3).to_string())
    print("\n--- SPATIAL AUTOCORRELATION ---")
    print(json.dumps(spatial_results, indent=2, default=str))

    print("\n--- OUTPUT FILES ---")
    print(f"  {SUITABILITY_DIR / 'suitability_scores.parquet'}")
    print(f"  {SUITABILITY_DIR / 'suitability_config_used.json'}")
    print(f"  {SUITABILITY_DIR / 'sensitivity_report.json'}")
    print(f"  {dim_map}")
    for s, p in scenario_maps.items():
        print(f"  {p}")
    print(f"  {latent_map}")
    print(f"  {sensitivity_map}")


if __name__ == "__main__":
    main()
