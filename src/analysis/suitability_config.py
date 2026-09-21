"""Phase 5B: E-bike deployment SUITABILITY framework — explicit configuration.

This is NOT a demand prediction. Every normalization, direction of
preference, and weight is declared here, in the open, specifically so noQ
hidden judgment call can silently drive the result.

Normalization: PERCENTILE RANK (0-1) per indicator across the 514 cells,
not min-max. Chosen because several indicators are heavy-tailed (e.g. one
cell has 33x more cycling-infrastructure density than the median) — min-max
would let that single cell compress the entire rest of the distribution
toward 0. Percentile rank is monotonic-preserving and outlier-robust.

Direction of preference is stated per indicator (higher_is_better). For
"lower is better" indicators (distances), the percentile rank is inverted
(1 - rank).

Terrain/e-bike relevance uses a DOCUMENTED, DELIBERATELY GENTLER penalty
than conventional (non-assisted) cycling-suitability literature would use,
reflecting motor assistance reducing the effort cost of grade. This is an
ASSUMPTION, not an empirically fitted e-bike tolerance curve (no such
Istanbul-specific literature was located) — it is sensitivity-tested
explicitly against a conventional (harsher) penalty curve.
"""

from __future__ import annotations

# --- Dimension -> indicator list. Each indicator: (feature_name, higher_is_better) ---
DIMENSIONS = {
    "activity_demand_environment": {
        "description": "Potential pedestrian/commercial activity environment — NOT observed demand.",
        "indicators": [
            ("poi_density_km2", True),
            ("poi_entropy", True),
            ("retail_area_ratio", True),
        ],
    },
    "population_exposure": {
        "description": "Residential population exposure (Phase 4: calibrated variant used as primary).",
        "indicators": [
            ("population_density_calibrated_km2", True),
        ],
    },
    "transit_accessibility_complementarity": {
        "description": "Proximity to and richness of public transit — e-bike share framed as a first/last-mile complement, not a competitor.",
        "indicators": [
            ("number_of_transit_modes_accessible", True),
            ("transit_stops_within_500m", True),
            ("distance_to_nearest_transit_m", False),
        ],
    },
    "cycling_accessibility_infrastructure": {
        "description": "Existing cycling-specific infrastructure — deliberately kept as only ONE of six dimensions so it cannot automatically dominate the result.",
        "indicators": [
            ("cycle_infrastructure_density_km_per_km2", True),
            ("pct_road_network_with_cycle_infrastructure", True),
            ("distance_to_nearest_cycle_infrastructure_m", False),
        ],
    },
    "urban_form_land_use_intensity": {
        "description": "Built-environment intensity and street connectivity.",
        "indicators": [
            ("building_coverage_ratio", True),
            ("intersection_density_km2", True),
            ("road_density_km_per_km2", True),
        ],
    },
    "terrain_ebike_relevance": {
        "description": "Terrain, with an e-bike-adjusted (gentler-than-conventional) slope penalty — see EBIKE_SLOPE_PENALTY.",
        "indicators": [
            ("mean_slope_deg", False),  # direction handled via the dedicated penalty function, not raw percentile-rank inversion
        ],
    },
}

# E-bike-adjusted slope suitability: 1.0 up to a comfortable threshold, then
# a linear decline to a FLOOR (never fully zeroed), reflecting that motor
# assistance still leaves *some* residual preference for flatter terrain
# (safety, range/battery anxiety) without penalizing hills as harshly as
# conventional unassisted-cycling suitability indices do.
EBIKE_SLOPE_COMFORTABLE_DEG = 3.0
EBIKE_SLOPE_STEEP_DEG = 10.0
EBIKE_SLOPE_FLOOR = 0.5

# For the sensitivity comparison: a CONVENTIONAL (non-assisted) cycling
# penalty — linear decline to 0 (fully unsuitable) by the same steep
# threshold, matching how much harsher standard cycling-suitability
# literature treats grade.
CONVENTIONAL_SLOPE_FLOOR = 0.0

# --- Scenario weights (sum to 1 across the six dimensions) ---
SCENARIOS = {
    "A_equal_weight_baseline": {
        "description": "No prior assumption — every dimension weighted equally. The transparent default.",
        "weights": {
            "activity_demand_environment": 1 / 6, "population_exposure": 1 / 6,
            "transit_accessibility_complementarity": 1 / 6, "cycling_accessibility_infrastructure": 1 / 6,
            "urban_form_land_use_intensity": 1 / 6, "terrain_ebike_relevance": 1 / 6,
        },
    },
    "B_transit_complementary": {
        "description": "E-bike share positioned as a first/last-mile transit extension: upweights transit access and population exposure.",
        "weights": {
            "activity_demand_environment": 0.20, "population_exposure": 0.20,
            "transit_accessibility_complementarity": 0.30, "cycling_accessibility_infrastructure": 0.10,
            "urban_form_land_use_intensity": 0.10, "terrain_ebike_relevance": 0.10,
        },
    },
    "C_latent_opportunity": {
        "description": "Deliberately EXCLUDES current cycling infrastructure (weight=0, redistributed equally to the other five) to surface areas favorable on every OTHER dimension regardless of whether infrastructure has caught up.",
        "weights": {
            "activity_demand_environment": 0.2, "population_exposure": 0.2,
            "transit_accessibility_complementarity": 0.2, "cycling_accessibility_infrastructure": 0.0,
            "urban_form_land_use_intensity": 0.2, "terrain_ebike_relevance": 0.2,
        },
    },
}

# Monte Carlo sensitivity: number of random weight draws (Dirichlet over the
# 6 dimensions, alpha=1 i.e. uniform over the simplex) used to test how much
# the ranking depends on the specific scenario weights chosen above.
N_MONTE_CARLO_DRAWS = 1000
MONTE_CARLO_RANDOM_STATE = 42
TOP_DECILE_THRESHOLD = 0.90
