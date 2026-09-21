import { semanticColors } from "./theme";

export const UNCERTAIN_FALLBACK = semanticColors.uncertain;

/** value -> color maps for every categorical field the map can render. */
export const fieldColorMaps: Record<string, Record<string, string>> = {
  typology_cluster: {
    "0": "#8C9A91",
    "1": "#B2F093",
    "2": "#6BAF82",
    "3": "#E0C168",
    "4": "#7D8BB0",
  },
  active_mobility_intervention: {
    WALKING_SUFFICIENT: semanticColors.positive,
    CYCLING_CLOSES_EVERYDAY_GAP: semanticColors.gain,
    CYCLING_CLOSES_TRANSIT_GAP: semanticColors.gain,
    CYCLING_CLOSES_BOTH: semanticColors.gain,
    CYCLING_PARTIAL_GAIN: semanticColors.partial,
    CYCLING_DOES_NOT_CLOSE_GAP: semanticColors.gap,
    QUALITY_UNCERTAIN: semanticColors.uncertain,
  },
  cycling_gap_closure: {
    NOT_APPLICABLE_NO_GAP: semanticColors.positive,
    FULLY_CLOSED_BY_CYCLING: semanticColors.gain,
    PARTIALLY_CLOSED_BY_CYCLING: semanticColors.partial,
    UNCHANGED_BY_CYCLING: semanticColors.gap,
    CYCLING_RESULT_UNCERTAIN: semanticColors.uncertain,
  },
  everyday_gap_type: {
    NO_REQUIRED_GAP: semanticColors.positive,
    FOOD_GAP: "#E0785A",
    HEALTHCARE_GAP: "#D9A441",
    EDUCATION_GAP: "#C77DBA",
    FOOD_HEALTHCARE_GAP: "#C65A3D",
    FOOD_EDUCATION_GAP: "#B85A9B",
    HEALTHCARE_EDUCATION_GAP: "#B98A2E",
    ALL_REQUIRED_GAP: "#9A3B2A",
    UNKNOWN_OR_QUALITY_LIMITED: semanticColors.uncertain,
  },
  transit_gap_type: {
    NO_TRANSIT_ACCESS_GAP: semanticColors.positive,
    GENERAL_ACCESS_GAP: "#D9A441",
    FIXED_GUIDEWAY_ACCESS_GAP: "#E0785A",
    BOTH_TRANSIT_ACCESS_GAPS: "#9A3B2A",
    TRANSIT_DATA_UNCERTAIN: semanticColors.transitLimit,
    NETWORK_QUALITY_UNCERTAIN: semanticColors.uncertain,
  },
  multi_domain_pattern: {
    A_BROAD_ACCESS: semanticColors.positive,
    B_EVERYDAY_NEEDS_GAP_ONLY: "#D9A441",
    C_TRANSIT_ACCESS_GAP_ONLY: semanticColors.transitLimit,
    D_BOTH_ACCESS_GAPS: semanticColors.gap,
    E_DATA_OR_NETWORK_UNCERTAIN: semanticColors.uncertain,
  },
  ebike_readiness_robustness: {
    ROBUST_HIGH: semanticColors.gain,
    FREQUENT_HIGH: semanticColors.positive,
    CONDITIONAL_HIGH: semanticColors.partial,
    RARE_HIGH: semanticColors.transitLimit,
    NEVER_HIGH: semanticColors.uncertain,
  },
  data_confidence: {
    RELIABLE: semanticColors.positive,
    NETWORK_LIMITATION: semanticColors.uncertain,
    TRANSIT_DATA_LIMITATION: semanticColors.transitLimit,
    MULTIPLE_LIMITATIONS: "#6B5F6E",
    KNOWN_SPECIAL_CASE: semanticColors.knownLimit,
  },
  cross_app_convergence: {
    BOTH_SIGNALS: semanticColors.gain,
    ACCESSIBILITY_GAIN_ONLY: semanticColors.positive,
    HIGH_EBIKE_READINESS_ONLY: semanticColors.transitLimit,
    NEITHER: semanticColors.uncertain,
  },
  ebike_opportunity_robustness: {
    ROBUST_HIGH: semanticColors.gain,
    FREQUENT_HIGH: semanticColors.positive,
    CONDITIONAL_HIGH: semanticColors.partial,
    RARE_HIGH: semanticColors.transitLimit,
    NEVER_HIGH: semanticColors.uncertain,
  },
};

export const fieldLabelMaps: Record<string, Record<string, string>> = {
  typology_cluster: { "0": "Cluster 0", "1": "Cluster 1", "2": "Cluster 2", "3": "Cluster 3", "4": "Cluster 4" },
};

/** Builds a MapLibre `match` expression for a categorical OR small-integer
 * ordinal field. Numeric-looking keys (e.g. "0".."3" for a 0-3 required-
 * categories count) are coerced to JS numbers so they compare correctly
 * against a numeric GeoJSON property -- MapLibre's `match` does strict
 * type comparison, so a string "0" would never match a number 0. */
export function buildMatchExpression(field: string, valueToColor: Record<string, string>, fallback = UNCERTAIN_FALLBACK): unknown[] {
  const expr: unknown[] = ["match", ["get", field]];
  for (const [value, color] of Object.entries(valueToColor)) {
    const isNumeric = value.trim() !== "" && !Number.isNaN(Number(value));
    const isBoolean = value === "true" || value === "false";
    const casted = isBoolean ? value === "true" : isNumeric ? Number(value) : value;
    expr.push(casted, color);
  }
  expr.push(fallback);
  return expr;
}
