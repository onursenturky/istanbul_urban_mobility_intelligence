export interface GridAttributes {
  grid_id: string;
  district: string;
  calibrated_population_2020: number;
  typology_cluster: number;
  population_density_per_km2: number;
  intersection_density_km2: number;
  cycle_infrastructure_density_km_per_km2: number;
  food_walk_min: number | null;
  healthcare_walk_min: number | null;
  education_walk_min: number | null;
  required_categories_walk_15: number;
  complete_walk_15: boolean;
  food_cycle_min: number | null;
  healthcare_cycle_min: number | null;
  education_cycle_min: number | null;
  required_categories_cycle_15: number;
  complete_cycle_15: boolean;
  cycle_only_everyday_gain: boolean;
  general_transit_walk_min: number | null;
  general_transit_cycle_min: number | null;
  fixed_transit_walk_min: number | null;
  fixed_transit_cycle_min: number | null;
  cycle_only_transit_gain: boolean;
  everyday_gap_type: string;
  cycling_gap_closure: string;
  transit_gap_type: string;
  multi_domain_pattern: string;
  active_mobility_intervention: string;
  ebike_readiness: number;
  ebike_opportunity: number;
  ebike_readiness_robustness: string;
  ebike_opportunity_robustness: string;
  walking_quality: string;
  cycling_quality: string;
  transit_data_quality: string;
  synthesis_reliable: boolean;
}

export type GridAttributesLookup = Record<string, GridAttributes>;

export interface DistrictSummaryRow {
  district: string;
  n_cells: number;
  population_total: number;
  [key: string]: unknown;
}

export interface DistrictProfile {
  district: string;
  n_cells: number;
  population_total: number;
  typology_composition_pct_population: Record<string, number>;
  population_complete_walk_15: number;
  common_everyday_gap_types: Record<string, number>;
  population_cycling_closes_everyday_gap: number;
  common_cycling_closure_types: Record<string, number>;
  transit_data_quality_class: string | null;
  population_in_good_transit_coverage_cells: number;
  ebike_readiness_mean: number;
  ebike_opportunity_mean: number;
  pct_cells_walking_quality_reliable: number;
  pct_cells_cycling_quality_reliable: number;
}

export interface ClaimRecord {
  claim_id: string;
  claim_text: string;
  exact_value: number;
  unit: string;
  denominator: string;
  analysis_universe: string;
  source_file: string;
  source_field_or_method: string;
  quality_status: string;
  allowed_language: string;
  prohibited_overclaim: string;
}

export interface CaseStudy {
  case_label: string;
  grid_id: string;
  district: string;
  population: number | null;
  typology_cluster: number | null;
  walking_accessibility: Record<string, unknown>;
  cycling_accessibility: Record<string, unknown>;
  transit_accessibility: Record<string, unknown>;
  gap_class: Record<string, unknown>;
  ebike_context: Record<string, unknown>;
  quality_status: Record<string, unknown>;
  why_this_case_matters: string;
}

export interface KpiRegistryRow {
  kpi_id: string;
  display_name: string;
  short_name: string;
  description: string;
  unit: string;
  source_application: string;
  headline_eligible: boolean;
  interpretation_warning: string;
  [key: string]: unknown;
}

export interface ContentHook {
  hook_id: string;
  title_tr: string;
  title_en: string;
  question: string;
  related_dashboard_page: string;
  related_map: string;
  claim_id: string;
  suggested_format: string;
  interpretation_note: string;
}
