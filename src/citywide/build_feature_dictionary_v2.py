"""Phase 7B: V2 feature dictionary.

Extends the frozen V1 feature dictionary (73 rows carried over unchanged,
after dropping the 2 PENDING_DEPENDENCY sentinel rows) with entries for the
21 new/resolved Phase 7A predictors. Every new predictor is classified
independently as READY / READY_WITH_LIMITATION / EXCLUDE_FROM_MODEL based on
the redundancy, structural-zero, coverage, and scaling-risk findings from
phase7b_impact_audit.py -- QA passing is necessary, not sufficient, for
READY.

New columns beyond the V1 schema:
  conceptual_relevance   -- which MCDA-relevant dimension(s) this predictor
                            could plausibly contribute to (classification
                            only, no weights/value functions assigned)
  redundancy_note        -- Spearman findings from the Phase 7B audit
  scaling_risk_note      -- Phase 5C-style zero-inflation/RobustScaler risk
  v1_v2_provenance        -- lineage note (new in V2 / resolved from V1 pending)

Output: data/processed/citywide/metadata/feature_dictionary_citywide_v2.csv
"""

from __future__ import annotations

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

V1_DICT_PATH = cfg.DATA_PROCESSED / "metadata" / "feature_dictionary_citywide.csv"
OUT_PATH = cfg.DATA_PROCESSED / "metadata" / "feature_dictionary_citywide_v2.csv"

PBF_SOURCE = "OpenStreetMap contributors, via Geofabrik Turkey PBF extract (snapshot 2026-09-18T20:21:10Z)"

NEW_ROWS = [
    # (feature_name, feature_family, definition, unit, zero_is_meaningful, completeness_status,
    #  known_limitation, classification, conceptual_relevance, redundancy_note, scaling_risk_note, provenance)
    dict(feature_name="road_length_m", feature_family="road_network",
         definition="Total OSM highway-network length (network_type='all' equivalent: all highway=* classes) clipped to this cell.",
         unit="m", zero_is_meaningful=True, completeness_status="COMPLETE",
         known_limitation="OSM road-mapping completeness varies by area, as with all OSM-derived features in this project.",
         classification="READY",
         conceptual_relevance="Mobility/Connectivity; Urban Form",
         redundancy_note="rho=0.99 vs road_grade_sample_length_m (diagnostic, excluded); rho=0.98 vs walkable_road_length_m/cycle_accessible_road_length_m (near-total subsets); rho=0.99 vs road_density_km_per_km2 (denominator-derived).",
         scaling_risk_note="No zero-mass or magnitude flags.",
         v1_v2_provenance="NEW in V2 (Phase 7A road-network family)."),
    dict(feature_name="major_road_length_m", feature_family="road_network",
         definition="Length of motorway/trunk/primary/secondary (+ _link) classes clipped to this cell.",
         unit="m", zero_is_meaningful=True, completeness_status="COMPLETE",
         known_limitation="73.6% of cells have zero major-road length (most cells contain only local streets) -- a genuine structural zero, not missing data.",
         classification="READY_WITH_LIMITATION",
         conceptual_relevance="Mobility/Connectivity; contextual (major roads are typically a cycling-safety barrier, not an enabler)",
         redundancy_note="No |rho|>=0.90 pairs.",
         scaling_risk_note="LARGE_EXACT_ZERO_MASS (73.6%), EXTREME_ROBUSTSCALER_MAGNITUDE (105.8), HIGH_SKEW (3.78) -- log1p or two-part (presence + conditional intensity) recommended before any scaling step.",
         v1_v2_provenance="NEW in V2 (Phase 7A road-network family)."),
    dict(feature_name="local_road_length_m", feature_family="road_network",
         definition="Length of tertiary/residential/living_street/unclassified/service/road (+ _link) classes clipped to this cell.",
         unit="m", zero_is_meaningful=True, completeness_status="COMPLETE",
         known_limitation="40.8% zero cells (undeveloped/rural/major-road-only cells).",
         classification="READY_WITH_LIMITATION",
         conceptual_relevance="Mobility/Connectivity; Urban Form",
         redundancy_note="No |rho|>=0.90 pairs.",
         scaling_risk_note="LARGE_EXACT_ZERO_MASS (40.8%); moderate skew (1.91), max scaled magnitude 7.9 -- log1p recommended.",
         v1_v2_provenance="NEW in V2 (Phase 7A road-network family)."),
    dict(feature_name="walkable_road_length_m", feature_family="road_network",
         definition="road_length_m minus motorway/motorway_link/trunk/trunk_link classes (roads legally open to pedestrians).",
         unit="m", zero_is_meaningful=True, completeness_status="COMPLETE",
         known_limitation="Perfectly rank-correlated with cycle_accessible_road_length_m citywide (differ only by the rare 'steps' class) -- carries no independent ranking information from it.",
         classification="READY_WITH_LIMITATION",
         conceptual_relevance="Mobility/Connectivity",
         redundancy_note="rho=1.00 vs cycle_accessible_road_length_m (near-identical exclusion sets) -- retain only ONE of the two in any composite index; both kept here as independently defined, methodologically distinct features.",
         scaling_risk_note="No zero-mass or magnitude flags.",
         v1_v2_provenance="NEW in V2 (Phase 7A road-network family)."),
    dict(feature_name="cycle_accessible_road_length_m", feature_family="road_network",
         definition="road_length_m minus motorway/motorway_link/trunk/trunk_link/steps classes (roads legally open to cyclists).",
         unit="m", zero_is_meaningful=True, completeness_status="COMPLETE",
         known_limitation="Perfectly rank-correlated with walkable_road_length_m citywide -- see that feature's note.",
         classification="READY_WITH_LIMITATION",
         conceptual_relevance="Cycling Readiness; Mobility/Connectivity",
         redundancy_note="rho=1.00 vs walkable_road_length_m; rho=0.98 vs road_length_m (near-total subset).",
         scaling_risk_note="No zero-mass or magnitude flags.",
         v1_v2_provenance="NEW in V2 (Phase 7A road-network family)."),
    dict(feature_name="road_density_km_per_km2", feature_family="road_network",
         definition="road_length_m normalized by cell land area (km road per km^2 land).",
         unit="km/km^2", zero_is_meaningful=True, completeness_status="COMPLETE",
         known_limitation="Denominator-derived from road_length_m; the two are rho=0.99 correlated by construction.",
         classification="READY",
         conceptual_relevance="Mobility/Connectivity; Urban Form",
         redundancy_note="rho=0.99 vs road_length_m (denominator-derived) -- prefer this normalized form over the raw length for cross-cell comparison in any future composite index.",
         scaling_risk_note="No zero-mass or magnitude flags.",
         v1_v2_provenance="NEW in V2 (Phase 7A road-network family)."),
    dict(feature_name="intersection_count", feature_family="road_network",
         definition="Count of nodes with street degree >=3 in the undirected road network within this cell (genuine shared-node junctions).",
         unit="count", zero_is_meaningful=True, completeness_status="COMPLETE",
         known_limitation="Computed via a validated lightweight method (pyrosm u/v node-degree), not a full OSMnx graph -- regression-tested against the frozen graph-degree method on the pilot districts: 98.6% exact per-cell agreement, max abs diff 2, total diff 0.032%.",
         classification="READY_WITH_LIMITATION",
         conceptual_relevance="Mobility/Connectivity; Cycling Readiness (network permeability)",
         redundancy_note="rho=0.998 vs intersection_density_km2 (denominator-derived); rho=0.90-0.91 vs several road-length features (general urbanization/network-extent signal).",
         scaling_risk_note="LARGE_EXACT_ZERO_MASS (40.5%), EXTREME_ROBUSTSCALER_MAGNITUDE (38.1) -- log1p recommended.",
         v1_v2_provenance="NEW in V2 (Phase 7A road-network family)."),
    dict(feature_name="intersection_density_km2", feature_family="road_network",
         definition="intersection_count normalized by cell land area (intersections per km^2).",
         unit="count/km^2", zero_is_meaningful=True, completeness_status="COMPLETE",
         known_limitation="Denominator-derived from intersection_count; see that feature's methodology note.",
         classification="READY",
         conceptual_relevance="Mobility/Connectivity; Cycling Readiness",
         redundancy_note="rho=0.998 vs intersection_count (denominator-derived) -- prefer this normalized form for cross-cell comparison.",
         scaling_risk_note="LARGE_EXACT_ZERO_MASS (40.5%), EXTREME_ROBUSTSCALER_MAGNITUDE (38.2) -- log1p recommended.",
         v1_v2_provenance="NEW in V2 (Phase 7A road-network family)."),
    dict(feature_name="green_area_m2", feature_family="landuse_greenspace",
         definition="Total area of OSM leisure/landuse/natural polygons matching the frozen GREEN_* value sets (dissolved, de-duplicated), clipped to this cell.",
         unit="m^2", zero_is_meaningful=True, completeness_status="COMPLETE",
         known_limitation="Subject to the same citywide OSM land-use tagging sparsity as all *_area_ratio features (see landuse_data_coverage_pct) -- 0 may reflect absence of tagging rather than absence of green space, though green/leisure features tend to be more consistently tagged than administrative land-use polygons where present.",
         classification="READY_WITH_LIMITATION",
         conceptual_relevance="Environmental/Land-use Context; Cycling Readiness (greenway appeal, contextual)",
         redundancy_note="rho=0.99 vs green_area_ratio (denominator-derived).",
         scaling_risk_note="No zero-mass/magnitude flags (green_area_m2 itself); see green_area_ratio.",
         v1_v2_provenance="NEW in V2 (Phase 7A land-use family)."),
    dict(feature_name="green_area_ratio", feature_family="landuse_greenspace",
         definition="green_area_m2 / cell land area.",
         unit="ratio", zero_is_meaningful=True, completeness_status="COMPLETE",
         known_limitation="Same OSM land-use tagging sparsity caveat as green_area_m2.",
         classification="READY_WITH_LIMITATION",
         conceptual_relevance="Environmental/Land-use Context",
         redundancy_note="rho=0.99 vs green_area_m2 (denominator-derived) -- prefer this normalized form.",
         scaling_risk_note="No risk flags (25.6% zero, skew 0.14, max RobustScaler magnitude 0.63) -- well-behaved, bounded [0,1].",
         v1_v2_provenance="NEW in V2 (Phase 7A land-use family)."),
    dict(feature_name="residential_area_ratio", feature_family="landuse_greenspace",
         definition="Area of OSM landuse=residential polygons / cell land area.",
         unit="ratio", zero_is_meaningful=False, completeness_status="PARTIAL_TAGGING_COVERAGE",
         known_limitation="Mean citywide landuse_data_coverage_pct is only 9.2% -- a cell's true residential land use is very frequently simply UNTAGGED in OSM, not genuinely absent. Confirmed empirically: rho=0.91 vs landuse_data_coverage_pct itself, meaning this feature substantially tracks 'was this cell's land use tagged at all' rather than a clean residential-density signal. 79.1% of cells read exactly zero.",
         classification="READY_WITH_LIMITATION",
         conceptual_relevance="Urban Form; Demand/Activity (contextual)",
         redundancy_note="rho=0.91 vs landuse_data_coverage_pct (severe coverage confound, see limitation).",
         scaling_risk_note="LARGE_EXACT_ZERO_MASS (79.1%), ZERO_IQR_UNDEFINED_ROBUSTSCALER, HIGH_SKEW (3.07) -- undefined-vs-zero confound means log1p alone will not fix this; a coverage-conditional or two-part treatment (informed by landuse_data_coverage_pct) should be evaluated before use, or exclusion considered.",
         v1_v2_provenance="NEW in V2 (Phase 7A land-use family)."),
    dict(feature_name="commercial_area_ratio", feature_family="landuse_greenspace",
         definition="Area of OSM landuse=commercial polygons / cell land area.",
         unit="ratio", zero_is_meaningful=False, completeness_status="PARTIAL_TAGGING_COVERAGE",
         known_limitation="Same severe OSM land-use tagging sparsity as residential_area_ratio; commercial land use is tagged even less consistently (96.25% of cells read exactly zero) -- cannot distinguish 'no commercial land use' from 'not tagged' at the cell level.",
         classification="READY_WITH_LIMITATION",
         conceptual_relevance="Demand/Activity (contextual)",
         redundancy_note="No |rho|>=0.90 pairs found, but see coverage caveat above.",
         scaling_risk_note="LARGE_EXACT_ZERO_MASS (96.25%), ZERO_IQR_UNDEFINED_ROBUSTSCALER, extreme skew (16.1) -- among the most zero-inflated features in V2; two-part representation or exclusion should be strongly considered.",
         v1_v2_provenance="NEW in V2 (Phase 7A land-use family)."),
    dict(feature_name="retail_area_ratio", feature_family="landuse_greenspace",
         definition="Area of OSM landuse=retail polygons / cell land area.",
         unit="ratio", zero_is_meaningful=False, completeness_status="PARTIAL_TAGGING_COVERAGE",
         known_limitation="Same OSM land-use tagging sparsity issue, most severe of the four composition ratios: 99.59% of cells read exactly zero. Note retail_count (POI family) already captures retail activity far more completely via point data -- this polygon-based ratio adds little on top of that and is overwhelmingly a coverage artifact.",
         classification="EXCLUDE_FROM_MODEL",
         conceptual_relevance="contextual-only",
         redundancy_note="No |rho|>=0.90 pairs found (too sparse to correlate meaningfully with anything).",
         scaling_risk_note="LARGE_EXACT_ZERO_MASS (99.59%), ZERO_IQR_UNDEFINED_ROBUSTSCALER, extreme skew (45.3) -- effectively unusable as a continuous predictor at this coverage level.",
         v1_v2_provenance="NEW in V2 (Phase 7A land-use family)."),
    dict(feature_name="industrial_area_ratio", feature_family="landuse_greenspace",
         definition="Area of OSM landuse=industrial polygons / cell land area.",
         unit="ratio", zero_is_meaningful=False, completeness_status="PARTIAL_TAGGING_COVERAGE",
         known_limitation="Same OSM land-use tagging sparsity issue (93.1% zero cells); where present, industrial land use IS meaningfully large-parcel and less prone to under-tagging than commercial/retail, but the confound with landuse_data_coverage_pct still applies.",
         classification="READY_WITH_LIMITATION",
         conceptual_relevance="contextual-only (industrial land use is not itself an e-bike demand or readiness signal, but may act as a negative modifier)",
         redundancy_note="No |rho|>=0.90 pairs found.",
         scaling_risk_note="LARGE_EXACT_ZERO_MASS (93.1%), ZERO_IQR_UNDEFINED_ROBUSTSCALER, high skew (8.0) -- two-part representation recommended if retained.",
         v1_v2_provenance="NEW in V2 (Phase 7A land-use family)."),
    dict(feature_name="landuse_data_coverage_pct", feature_family="landuse_greenspace",
         definition="Share of this cell's land area covered by ANY classified OSM land-use polygon (diagnostic denominator for the *_area_ratio columns' interpretability, not itself a suitability signal).",
         unit="pct", zero_is_meaningful=True, completeness_status="COMPLETE",
         known_limitation="Mean citywide value is only 9.2% -- reflects OSM community land-use tagging sparsity, not a Phase 7A acquisition defect (would be identical under the abandoned live-Overpass method, same underlying OSM data).",
         classification="EXCLUDE_FROM_MODEL",
         conceptual_relevance="contextual-only (coverage diagnostic)",
         redundancy_note="rho=0.91 vs residential_area_ratio -- the exact confound this diagnostic exists to explain.",
         scaling_risk_note="Not applicable (diagnostic, not a model predictor).",
         v1_v2_provenance="NEW in V2 (Phase 7A land-use family)."),
    dict(feature_name="mean_absolute_road_grade_pct", feature_family="road_grade",
         definition="Length-weighted mean |grade| across road segments in this cell (grade_pct = |elevation_change| / horizontal_length * 100, sampled bilinearly from Copernicus GLO-30 at each segment's endpoints).",
         unit="pct", zero_is_meaningful=True, completeness_status="COMPLETE_WHERE_ROAD_PRESENT",
         known_limitation="NaN (not 0) for the 12.6% of cells with no road segment surviving the 30m minimum-length / valid-DEM-coverage filter -- a genuine missing-data case, never silently zeroed.",
         classification="READY",
         conceptual_relevance="Terrain/Physical Feasibility; Cycling Readiness (grade is a core e-bike/cycling barrier-or-enabler measure)",
         redundancy_note="No |rho|>=0.90 pairs.",
         scaling_risk_note="No zero-mass/magnitude flags among cells with data.",
         v1_v2_provenance="RESOLVED in V2 from V1's road_grade_status='PENDING_ROAD_NETWORK' sentinel (Phase 7A road-grade family)."),
    dict(feature_name="median_absolute_road_grade_pct", feature_family="road_grade",
         definition="Length-weighted median |grade| across road segments in this cell.",
         unit="pct", zero_is_meaningful=True, completeness_status="COMPLETE_WHERE_ROAD_PRESENT",
         known_limitation="Same NaN-for-missing convention as mean_absolute_road_grade_pct.",
         classification="READY",
         conceptual_relevance="Terrain/Physical Feasibility; Cycling Readiness",
         redundancy_note="No |rho|>=0.90 pairs.",
         scaling_risk_note="No zero-mass/magnitude flags among cells with data.",
         v1_v2_provenance="RESOLVED in V2 from V1's road_grade_status='PENDING_ROAD_NETWORK' sentinel (Phase 7A road-grade family)."),
    dict(feature_name="pct_road_length_grade_gt_5pct", feature_family="road_grade",
         definition="Share of this cell's grade-sampled road length with grade > 5%.",
         unit="pct", zero_is_meaningful=True, completeness_status="COMPLETE_WHERE_ROAD_PRESENT",
         known_limitation="Same NaN-for-missing convention as mean_absolute_road_grade_pct.",
         classification="READY_WITH_LIMITATION",
         conceptual_relevance="Terrain/Physical Feasibility; Cycling Readiness",
         redundancy_note="No |rho|>=0.90 pairs.",
         scaling_risk_note="LARGE_EXACT_ZERO_MASS (41.4%, flat-terrain cells) -- moderate skew (1.48), not extreme; log1p optional.",
         v1_v2_provenance="RESOLVED in V2 from V1's road_grade_status='PENDING_ROAD_NETWORK' sentinel (Phase 7A road-grade family)."),
    dict(feature_name="pct_road_length_grade_gt_8pct", feature_family="road_grade",
         definition="Share of this cell's grade-sampled road length with grade > 8%.",
         unit="pct", zero_is_meaningful=True, completeness_status="COMPLETE_WHERE_ROAD_PRESENT",
         known_limitation="Same NaN-for-missing convention as mean_absolute_road_grade_pct.",
         classification="READY_WITH_LIMITATION",
         conceptual_relevance="Terrain/Physical Feasibility; Cycling Readiness",
         redundancy_note="No |rho|>=0.90 pairs.",
         scaling_risk_note="LARGE_EXACT_ZERO_MASS (59.8%), HIGH_SKEW (3.04) -- log1p recommended.",
         v1_v2_provenance="RESOLVED in V2 from V1's road_grade_status='PENDING_ROAD_NETWORK' sentinel (Phase 7A road-grade family)."),
    dict(feature_name="road_grade_sample_length_m", feature_family="road_grade",
         definition="Total road length (m) that survived the grade-computation filters (>=30m segment, valid DEM at both endpoints) in this cell -- a coverage diagnostic for the other road-grade columns.",
         unit="m", zero_is_meaningful=True, completeness_status="COMPLETE",
         known_limitation="Diagnostic column analogous to V1's n_valid_dem_pixels -- not intended as a model predictor.",
         classification="EXCLUDE_FROM_MODEL",
         conceptual_relevance="contextual-only (coverage diagnostic)",
         redundancy_note="rho=0.999 vs road_length_m, rho=0.988 vs road_density_km_per_km2 -- essentially a filtered restatement of total road length.",
         scaling_risk_note="Not applicable (diagnostic, not a model predictor).",
         v1_v2_provenance="RESOLVED in V2 from V1's road_grade_status='PENDING_ROAD_NETWORK' sentinel (Phase 7A road-grade family)."),
    dict(feature_name="pct_road_network_with_cycle_infrastructure", feature_family="cycling",
         definition="Share of this cell's (Phase 7A PBF-derived) road network length lying within CYCLING_DEDUP_BUFFER_M (15m) of any İBB cycling-infrastructure geometry.",
         unit="pct", zero_is_meaningful=True, completeness_status="COMPLETE_WHERE_ROAD_PRESENT",
         known_limitation="NaN (not 0) for the 12.6% of cells with zero road length -- distinguishes 'no road to measure' from 'road present, no nearby cycling infra' (which correctly reads 0). Cycling infrastructure is genuinely rare citywide (95.3% of valid cells read exactly 0).",
         classification="READY_WITH_LIMITATION",
         conceptual_relevance="Cycling Readiness (direct)",
         redundancy_note="rho=0.99 vs cycle_infrastructure_density_km_per_km2_ibb_only and cycle_infrastructure_length_km_ibb_only (existing V1 cycling features) -- expected, since more cycling infrastructure mechanically raises both metrics, but the two use different normalizations (share of road network vs. absolute density per land area) and are not strictly interchangeable; a later MCDA step should choose one preferred representation rather than double-counting both.",
         scaling_risk_note="LARGE_EXACT_ZERO_MASS (95.3%), ZERO_IQR_UNDEFINED_ROBUSTSCALER, HIGH_SKEW (8.0) -- textbook two-part (presence + conditional intensity) candidate, matching the Candidate D pattern already used for building_coverage_ratio in Phase 5C.",
         v1_v2_provenance="RESOLVED in V2 from V1's pct_road_network_with_cycle_infrastructure_status='PENDING_ROAD_NETWORK' sentinel (Phase 7A cycling-road-overlap)."),
]


def main() -> None:
    v1 = pd.read_csv(V1_DICT_PATH)
    pending_names = {"road_grade_status", "pct_road_network_with_cycle_infrastructure_status"}
    v1_carried = v1[~v1["feature_name"].isin(pending_names)].copy()

    for col in ["conceptual_relevance", "redundancy_note", "scaling_risk_note", "v1_v2_provenance"]:
        v1_carried[col] = "" if col != "v1_v2_provenance" else "UNCHANGED from V1 (existing feature, integrity-verified identical in V2)."

    new_df = pd.DataFrame(NEW_ROWS)
    missing_cols = set(v1_carried.columns) - set(new_df.columns)
    for col in missing_cols:
        new_df[col] = new_df.get(col, "")

    v2_dict = pd.concat([v1_carried, new_df], ignore_index=True, sort=False)
    v2_dict = v2_dict[list(v1.columns) + ["conceptual_relevance", "redundancy_note", "scaling_risk_note", "v1_v2_provenance"]]

    assert v2_dict["feature_name"].is_unique, "duplicate feature_name in V2 dictionary"
    assert not (v2_dict["classification"] == "PENDING_DEPENDENCY").any(), "PENDING_DEPENDENCY should not remain in V2"

    print("V2 feature dictionary rows:", len(v2_dict))
    print(v2_dict["classification"].value_counts())

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v2_dict.to_csv(OUT_PATH, index=False)
    print(f"[save] {OUT_PATH}")


if __name__ == "__main__":
    main()
