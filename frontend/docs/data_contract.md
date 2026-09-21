# Data Contract

The frontend's ONLY analytical inputs are the frozen files under
`analysis/framework_synthesis/` (Phase 12 output). This document lists every frontend data
file, its source, and any transformation applied. Full machine-readable detail after each
`prepare-data` run is in `qa/_data_prep_manifest.json`.

| Frontend file | Source (`analysis/framework_synthesis/...`) | Transformation |
|---|---|---|
| `public/data/base/grid_geometry.json` | `dashboard/dashboard_grid_lite.geojson` | Geometry reused verbatim from Phase 12's lite export (20m simplification, 5-decimal precision — Phase 12's own choice, not re-simplified here). Properties stripped to `grid_id` + `district` only — no analytical fields (Phase 14 geometry/layer split, see `docs/map_delivery_decision.md`). |
| `public/data/layers/<field>.json` (12 files: `typology_cluster`, `required_categories_walk_15`, `required_categories_cycle_15`, `active_mobility_intervention`, `everyday_gap_type`, `cycling_gap_closure`, `transit_gap_type`, `cycle_only_transit_gain`, `ebike_readiness_robustness`, `ebike_opportunity_robustness`, `cross_app_convergence`, `data_confidence`) | `dashboard/dashboard_grid.parquet` (single column each); `cross_app_convergence` and `data_confidence` are derived categorical overlays (see below) | One column extracted as a flat `{grid_id: value}` map. Merged client-side into the base geometry's properties by `lib/mapDataCache.ts` for whichever field(s) the current page colors by. |
| `public/data/details/<district>.json` (39 files) | `dashboard/dashboard_grid.parquet` | Full attribute row (all 36 columns except `district`, which is the chunk's filename) per cell, grouped by district. Fetched on demand by `lib/useGridAttributes.ts` only for the district containing a selected cell — never fetched in bulk. NaN → JSON `null` (never 0). |
| `public/data/details/_grid_district_index.json` | `dashboard/dashboard_grid.parquet` | Flat `grid_id -> district` map, so a shared `?grid=` URL can resolve which detail chunk to fetch even without a matching `?district=`. |
| `public/data/district_summary.json` | `dashboard/dashboard_district_summary.parquet` | Parquet → JSON array, unchanged. |
| `public/data/district_profiles.json` | `district_profiles.parquet` | Parquet → JSON array; 3 nested JSON-string columns decoded into native objects. |
| `public/data/kpi_registry.json`, `map_layer_registry.json`, `chart_registry.json`, `claims_registry.json` | `registries/*.csv` | CSV → JSON array, unchanged. |
| `public/data/methodology_registry.json` | `methodology/methodology_registry.csv` | CSV → JSON array, unchanged. |
| `public/data/case_studies.json`, `headline_kpis.json`, `framework_findings.json`, `framework_architecture.json`, `dashboard_information_architecture.json`, `dashboard_filter_spec.json` | corresponding `.json` files | Verbatim re-serialization (compact, no pretty-print). |
| `public/data/framework_narrative.md` | `methodology/framework_narrative.md` | Verbatim copy. |

## Derived presentation-only fields (not new analytical scores)

Both are 4-way categorical overlays of two *already-frozen* categorical fields, computed
once during data prep — not a new score, not a new measurement:

- **`cross_app_convergence`**: `BOTH_SIGNALS` / `ACCESSIBILITY_GAIN_ONLY` /
  `HIGH_EBIKE_READINESS_ONLY` / `NEITHER`, from `active_mobility_intervention` (gain if in
  `{CYCLING_CLOSES_EVERYDAY_GAP, CYCLING_CLOSES_TRANSIT_GAP, CYCLING_CLOSES_BOTH}`) crossed
  with `ebike_readiness_robustness` (high if `ROBUST_HIGH` or `FREQUENT_HIGH`). Mirrors
  Phase 12's own MAP_11 specification.
- **`data_confidence`**: `RELIABLE` / `NETWORK_LIMITATION` / `TRANSIT_DATA_LIMITATION` /
  `MULTIPLE_LIMITATIONS` / `KNOWN_SPECIAL_CASE`, from `walking_quality` + `cycling_quality` +
  `transit_data_quality`. Mirrors Phase 12's own MAP_12 specification. Adalar is always
  `KNOWN_SPECIAL_CASE`.

## Bug found and fixed upstream during Phase 13 (not a frontend-only patch)

`required_categories_cycle_15` was traced, during live QA, to an incorrect source column
two phases upstream: Phase 11's synthesis table never joined in
`cycling_required_categories_accessible_15min` (the 3-required-category count) from
`analysis/applications/cycling_accessibility/walking_cycling_complete_access_comparison.parquet`;
Phase 12 then substituted `cycling_categories_accessible_15min` (the all-8-category count)
under the wrong name. Fixed in `src/citywide/phase11_synthesis.py`, with the full Phase 11 →
Phase 12 → frontend-data-prep chain re-run and re-verified (all consistency/QA checks and
every population/cell figure identical — the bug only ever affected this one display field,
never any actual classification). See `qa/visual_qa.md` for the full account.

## Guarantees

- No file under `analysis/` is ever written to by anything in `frontend/`.
- Every value in `public/data/` traces to a named frozen source file and column (verified
  programmatically by `qa/data_qa.py`, check B).
- NaN/unreachable is always `null` in the JSON output, never `0` or a placeholder string
  (verified by `qa/data_qa.py`, check G).
