"""Phase 12, Sections 15, 20-21: methodology/data-provenance registry,
claims registry, and the framework evidence narrative. Documentation
generation over already-frozen, already-documented sources -- no new
computation.
"""

from __future__ import annotations

import json

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

ROOT = cfg.PROJECT_ROOT
OUT_DIR = ROOT / "analysis" / "framework_synthesis"
REG_DIR = OUT_DIR / "registries"
METH_DIR = OUT_DIR / "methodology"


def main() -> None:
    print("=" * 72)
    print("Phase 12 Sections 15, 20-21: methodology registry, claims registry, framework narrative")
    print("=" * 72)

    print("\n[Section 20] Methodology / data-provenance registry...")
    methodology = [
        dict(layer="Population", data_source="WorldPop gridded population, calibrated to official TUIK 2020 district totals (Phase 3C calibration)",
             snapshot_year="2020", spatial_resolution="~100m native, aggregated to 500m study grid",
             processing_method="Dasymetric calibration of WorldPop raster to official 2020 district population counts.",
             known_limitations="2020 snapshot vs 2026 network/destination/GTFS data -- explicit temporal mismatch carried through every application.",
             appropriate_interpretation="Accessibility of the CALIBRATED 2020 population's spatial distribution to the CURRENT network/destination snapshot, never a 2026 population estimate."),
        dict(layer="Terrain", data_source="Copernicus DEM GLO-30", snapshot_year="~2019-2021 (Copernicus GLO-30 baseline)",
             spatial_resolution="30m", processing_method="Slope/elevation/road-grade features computed via Phase 4/7A road-grade sampling.",
             known_limitations="Vertical accuracy varies by terrain type; road-grade sampling only, not a full hydrological/geomorphological analysis.",
             appropriate_interpretation="Used for descriptive terrain/road-grade features only, never as a cycling-speed adjustment in the frozen baseline speed model."),
        dict(layer="Roads / Buildings / Land Use / POIs", data_source="OpenStreetMap via Geofabrik (turkey-latest.osm.pbf)",
             snapshot_year="Snapshot recorded 2026-09-18 (see network_intelligence_manifest.json pbf_snapshot)",
             spatial_resolution="Vector, native OSM digitization resolution",
             processing_method="osmium extraction (Phase 7A) + pyrosm/osmnx graph construction (Phase 7) + GDAL/pyogrio feature extraction (Phase 3-4).",
             known_limitations="Citizen-mapped data: completeness varies by district (documented per-feature in feature_dictionary_citywide_v2.csv); "
                                "a critical pyrosm to_graph() node-loss bug was found and fixed during Phase 7 (see network_intelligence_manifest.json).",
             appropriate_interpretation="Best-available open mapping data, not a surveyed inventory; treat sparse-district results as data-limited, not necessarily infrastructure-absent."),
        dict(layer="Cycling Infrastructure", data_source="İBB (Istanbul Metropolitan Municipality) official cycling-infrastructure datasets",
             snapshot_year="İBB open-data retrieval date (see feature_dictionary_citywide_v2.csv 'ibb_only' columns)",
             spatial_resolution="Vector", processing_method="Direct İBB dataset ingestion, kept SEPARATE from OSM-inferred cycling ways.",
             known_limitations="İBB-only source may undercount informally-used or newly-built cycling routes not yet in the official dataset.",
             appropriate_interpretation="Official infrastructure presence indicator, not a comfort/safety/usage measure."),
        dict(layer="Public Transit (Metro/Tram/Rail/Ferry)", data_source="main_gtfs, 'Toplu Ulaşım GTFS Verisi' (İBB Açık Veri Portalı)",
             snapshot_year="Resource files dated 2023-2024; feed explicitly states it will not be updated",
             spatial_resolution="Point (stops) + route topology", processing_method="GTFS parsing (src/features/transit_infrastructure.py); used for STATION LOCATIONS AND ROUTE TOPOLOGY ONLY.",
             known_limitations="Calendar/service dates have ALL expired as of the 2026 retrieval date -- NEVER used for departure frequency or timetable claims.",
             appropriate_interpretation="Infrastructure/topology source only; do not infer service frequency or current operational status from this feed."),
        dict(layer="Public Transit (Bus/Metrobüs)", data_source="iett_gtfs, 'İETT GTFS Verisi' (İBB Açık Veri Portalı)",
             snapshot_year="Resources dated 2026-03-17; calendar valid 2026-03-16 to 2026-12-31",
             spatial_resolution="Point (stops) + route topology + schedule", processing_method="GTFS parsing; used for both infrastructure AND departure-frequency features.",
             known_limitations="Zero mapped stops in Silivri and Çatalca (re-confirmed Phase 10); several districts show implausibly sparse coverage (Bahçelievler, Gaziosmanpaşa, Kâğıthane, Sultangazi).",
             appropriate_interpretation="Current and reliable where coverage exists; NO_FEED_COVERAGE areas require explicit DATA INSUFFICIENT treatment, never read as NO_TRANSIT_SERVICE."),
        dict(layer="Walking Network", data_source="Derived from the same OSM/Geofabrik PBF via pyrosm+osmnx (Phase 7)",
             snapshot_year="Same as OSM snapshot above", spatial_resolution="Vector graph, EPSG:32635",
             processing_method="Undirected graph, transparent tag-based inclusion/exclusion rules (network_rules.py), constant 5.0km/h baseline speed.",
             known_limitations="oneway:foot too sparse to support directed pedestrian routing (documented, not silently assumed handled).",
             appropriate_interpretation="Modeled network accessibility at a constant baseline speed, not observed walking behavior or real-time conditions."),
        dict(layer="Cycling Network", data_source="Derived from the same OSM/Geofabrik PBF via pyrosm+osmnx (Phase 7)",
             snapshot_year="Same as OSM snapshot above", spatial_resolution="Vector graph, EPSG:32635",
             processing_method="Directed graph respecting generic oneway tag, constant 15.0km/h baseline speed.",
             known_limitations="oneway:bicycle contraflow exceptions present in source data but NOT applied to override directionality (documented baseline limitation).",
             appropriate_interpretation="Modeled POTENTIAL cycling accessibility at a constant baseline speed -- no terrain adjustment, no comfort/stress modeling, not validated mode choice."),
        dict(layer="Everyday-Needs POI Taxonomy", data_source="OSM POI tags (raw amenity/shop/leisure values) + the two GTFS feeds for the transit category",
             snapshot_year="Same as OSM/GTFS snapshots above", spatial_resolution="Point",
             processing_method="8-category taxonomy (A-H) built from explicit, documented raw tag rules (Phase 8); Food/Healthcare/Education are the 3 REQUIRED categories.",
             known_limitations="Green/Recreation category is POI-only (excludes land-use polygons) and likely undercounts true green-space access; Daily Services is a new, moderate-reliability grouping.",
             appropriate_interpretation="REQUIRED categories (Food, Healthcare, Education) selected for BOTH conceptual necessity AND source reliability -- not forced to inflate any metric."),
        dict(layer="Urban Typology (V2 Eight-Family)", data_source="94-predictor V2 feature baseline (CITYWIDE_V2_EIGHT_FAMILY_FEATURE_BASELINE), clustered via KMeans k=5",
             snapshot_year="Composite of all above snapshots", spatial_resolution="500m grid cell",
             processing_method="Dimension-first aggregation + parsimonious criteria screening + KMeans k=5 (Phase 5A/5B-V2, evidence-based k selection).",
             known_limitations="Descriptive typology, not a causal urban-planning classification; cluster numbering (0-4) carries no inherent order.",
             appropriate_interpretation="Use only as a post-hoc descriptive lens -- typology never entered any routing or accessibility computation in any application."),
        dict(layer="E-bike Readiness & Opportunity", data_source="Frozen MCDA over the V2 feature baseline + frozen network intelligence",
             snapshot_year="Composite of all above snapshots", spatial_resolution="500m grid cell",
             processing_method="Dimension-first value-function aggregation (Readiness) and geometric demand^alpha*gap^(1-alpha) formula (Opportunity); 6-variant sensitivity, consensus classes.",
             known_limitations="MCDA value functions are analyst-defined (transparently documented), not empirically fit; robustness is to weighting choices only, not to underlying data quality.",
             appropriate_interpretation="Suitability/latent-opportunity indicator, not a deployment guarantee or observed/surveyed demand."),
    ]
    meth_df = pd.DataFrame(methodology)
    meth_df.to_csv(METH_DIR / "methodology_registry.csv", index=False)
    print(f"  {len(meth_df)} methodology/provenance rows written")
    print(f"[save] {METH_DIR / 'methodology_registry.csv'}")

    print("\n[Section 21] Claims registry (allowed vs prohibited language)...")
    claims = [
        dict(claim_id="C01", claim_text="Approximately 82.5% of the calibrated 2020 population distribution lies in cells with "
                                          "modeled 15-minute walking access to Food, Healthcare and Education.",
             exact_value=82.49, unit="pct of population", denominator="15,455,565.5 (all calibrated 2020 population)",
             analysis_universe="Phase 8.1 Denominator A (all populated cells, raw flag)",
             source_file="analysis/applications/15min_city/validation/population_accessibility_validation.json",
             source_field_or_method="denominator_A_all_populated_cells.pct_with_complete_access", quality_status="Official frozen headline figure",
             allowed_language="'modeled 15-minute walking access', 'calibrated 2020 population distribution'",
             prohibited_overclaim="'82.5% of Istanbul residents live in a 15-minute city' -- do not claim a lived experience or a validated urban-planning designation."),
        dict(claim_id="C02", claim_text="Cycling potentially closes the mapped everyday-needs walking gap for approximately 2.10 "
                                          "million people in the calibrated population surface.",
             exact_value=2095477.3, unit="people", denominator="19,073 cells with a walking everyday-needs gap",
             analysis_universe="Phase 9 CYCLE_ONLY_GAIN / Phase 11 FULLY_CLOSED_BY_CYCLING",
             source_file="analysis/applications/cycling_accessibility/population_cycling_accessibility_summary.json",
             source_field_or_method="high_value_gain_cells / access_class == CYCLE_ONLY_GAIN", quality_status="Consistent across Phase 9 and Phase 11 (>99% overlap, see consistency test B)",
             allowed_language="'potentially closes', 'modeled network accessibility', 'calibrated population surface'",
             prohibited_overclaim="'2.10 million Istanbul residents would benefit from cycling' -- no behavioral or causal claim, no implied policy outcome."),
        dict(claim_id="C03", claim_text="Approximately 95.6% of the calibrated 2020 population has complete 15-minute potential "
                                          "cycling access to the three required everyday needs.",
             exact_value=95.57, unit="pct of population", denominator="15,455,565.5",
             analysis_universe="Phase 9, RAW (all cells)", source_file="analysis/applications/cycling_accessibility/population_cycling_accessibility_summary.json",
             source_field_or_method="cycling_complete_15min_access.pct_population", quality_status="RAW figure; quality-aware re-check shows <0.1pp difference",
             allowed_language="'potential cycling access', 'modeled travel time'",
             prohibited_overclaim="Do not compare directly to C01 as a simple before/after -- different mode, same population, requires the cell-level join (see H02) to speak of a 'gain'."),
        dict(claim_id="C04", claim_text="Approximately 3.03 million people are associated with a modeled general-transit "
                                          "cycling-only access gain (RAW, 15-minute threshold).",
             exact_value=3025322.3, unit="people", denominator="15,455,565.5",
             analysis_universe="Phase 10, RAW (all cells, 15min, System A)", source_file="analysis/applications/first_last_mile_transit/transit_accessibility_gain_5_10_15.csv",
             source_field_or_method="access_class == CYCLE_ONLY_TRANSIT_GAIN, system=GENERAL, threshold_min=15",
             quality_status="RAW -- feed-gap sensitivity test showed a +30.83pp swing when non-GOOD_COVERAGE districts are excluded",
             allowed_language="'RAW, unfiltered by transit-feed quality'; always paired with the quality-aware caveat",
             prohibited_overclaim="Do not present this as a citywide fact without the feed-coverage caveat -- roughly a third of districts have inadequate transit-feed data."),
        dict(claim_id="C05", claim_text="Approximately 4.80 million people are associated with a modeled fixed-guideway "
                                          "cycling-only access gain (RAW, 15-minute threshold).",
             exact_value=4801394.5, unit="people", denominator="15,455,565.5",
             analysis_universe="Phase 10, RAW (all cells, 15min, System B)", source_file="analysis/applications/first_last_mile_transit/transit_accessibility_gain_5_10_15.csv",
             source_field_or_method="access_class == CYCLE_ONLY_TRANSIT_GAIN, system=FIXED, threshold_min=15",
             quality_status="RAW -- same feed-gap caveat as C04",
             allowed_language="Same as C04.", prohibited_overclaim="Same as C04."),
        dict(claim_id="C06", claim_text="352,939 people remain in cells where cycling does not close the mapped everyday-needs "
                                          "accessibility gap, most plausibly due to genuine destination sparsity.",
             exact_value=352939.0, unit="people", denominator="19,073 cells with a walking everyday-needs gap",
             analysis_universe="Phase 11 UNCHANGED_BY_CYCLING", source_file="analysis/applications/accessibility_gap_intelligence/framework_level_findings.json",
             source_field_or_method="q7_population_cycling_does_not_close_gap_destinations_sparse", quality_status="everyday_access_reliable == True required",
             allowed_language="'genuine destination sparsity', 'not a network/routing limitation'",
             prohibited_overclaim="Do not label these areas 'service deserts' or 'underserved communities'."),
        dict(claim_id="C07", claim_text="341,370 people (2.21% of population) are associated with a quality-aware cycling "
                                          "closure of a measured transit-access gap.",
             exact_value=341370.2, unit="people", denominator="15,455,565.5",
             analysis_universe="Phase 11, STRICT_SYNTHESIS_RELIABLE only", source_file="analysis/applications/accessibility_gap_intelligence/framework_level_findings.json",
             source_field_or_method="q4_population_cycling_closes_transit_gap", quality_status="Quality-aware (both network AND transit-feed quality adequate) -- the DEFENSIBLE figure",
             allowed_language="'quality-aware', 'reliable subset'",
             prohibited_overclaim="Do not conflate with C04/C05 (RAW) as if they measure the same thing -- this is deliberately smaller and more conservative."),
        dict(claim_id="C08", claim_text="74.67% of cells where cycling closes an everyday-needs gap fall in the top quartile "
                                          "of frozen e-bike Readiness, versus a 25% citywide baseline.",
             exact_value=74.67, unit="pct of cells", denominator="1,145 CYCLING_CLOSES_EVERYDAY_GAP cells",
             analysis_universe="Phase 11/12 cross-application overlay", source_file="analysis/applications/accessibility_gap_intelligence/ebike_gap_convergence.json",
             source_field_or_method="CYCLING_CLOSES_EVERYDAY_GAP.pct_top_quartile_ebike_readiness", quality_status="Descriptive overlap only",
             allowed_language="'cross-application convergence', 'descriptive co-location'",
             prohibited_overclaim="'This proves e-bikes work here' or 'this validates the e-bike model' -- convergence is not validation."),
    ]
    claims_df = pd.DataFrame(claims)
    claims_df.to_csv(REG_DIR / "claims_registry.csv", index=False)
    print(f"  {len(claims_df)} claims registered")
    print(f"[save] {REG_DIR / 'claims_registry.csv'}")

    print("\n[Section 15] Framework evidence narrative...")
    narrative_md = """# Istanbul Urban Mobility Intelligence -- Framework Evidence Narrative

## A. Istanbul is spatially heterogeneous
The V2 eight-family typology (k=5, evidence-based selection) shows Istanbul is not one
city but several recurring urban regimes -- dense transit-rich cores, dense peripheral
residential areas, and sparse/rural-edge districts -- each with a materially different
accessibility profile (see `typology_accessibility_gap_summary.csv`).

## B. Accessibility is concentrated
14.6% of grid cells hold 82.5% of the calibrated population's complete-walking-access
outcome (C01). This is not a modeling artifact: Phase 8.1's population-concentration
analysis confirmed the top 10% densest cells hold ~80% of population, and ~92% of that
population already has complete access. Land-area coverage and population coverage are
different lenses and must never be conflated.

## C. Cycling changes the accessibility geography
Cycling raises complete everyday-needs access from 82.5% to 95.6% of the population
(C01 vs C03), and 2.10 million people gain complete access specifically by switching the
modeled mode from walking to cycling (C02). This is Phase 9's central finding.

## D. Cycling also expands transit catchments
Cycling's largest quantified transit contribution is fixed-guideway access: RAW figures
suggest ~4.80 million people gain modeled 15-minute cycling access to metro/tram/rail/
metrobus that they lack by walking (C05) -- but this RAW figure swings by +30.83
percentage points when non-GOOD_COVERAGE districts are excluded (Phase 10 feed-gap
sensitivity test). The quality-aware, defensible figure for a *combined* everyday+transit
cycling closure is far smaller: 341,370 people (C07).

## E. Not all accessibility gaps are solved by cycling
352,939 people remain in cells where cycling's modeled network does not close any missing
required category (C06) -- these are areas of genuine destination sparsity, not network
or routing limitations. No active-mobility intervention can create a destination that does
not exist.

## F. Independent applications show cross-application convergence
Cells where cycling closes an everyday-needs gap are strongly over-represented in the
independently-derived e-bike Readiness top quartile (74.67% vs a 25% citywide baseline,
C08). The two applications were built from different frozen sources with no shared
computation -- this convergence is a meaningful cross-check, though explicitly not a
validation of either application.

## G. Uncertainty is part of the product
Only 27.29% of cells (73.84% of population) qualify as STRICT_SYNTHESIS_RELIABLE --
reliable enough for a joint everyday-needs-and-transit claim. Transit-feed coverage,
not network quality, is the dominant constraint: Silivri and Catalca have zero mapped
transit stops (NO_FEED_COVERAGE, re-confirmed by direct re-audit), and 16 further
districts show sparse or suspect coverage. Adalar carries a standing, explicitly flagged
network limitation across every phase (small isolated walking component; zero real
cycling nodes, with cycling figures reflecting cross-water snapping). None of this
uncertainty is hidden inside a combined score -- it is reported as its own dimension
throughout (`walking_quality`, `cycling_quality`, `transit_data_quality`,
`synthesis_reliable`).

*No causal claims are made anywhere in this framework. All figures describe modeled
network accessibility of a calibrated 2020 population surface against a 2026 network/
destination/transit-feed snapshot.*
"""
    (METH_DIR / "framework_narrative.md").write_text(narrative_md, encoding="utf-8")
    print(f"[save] {METH_DIR / 'framework_narrative.md'}")

    print("\n[Extra] framework_findings.json (top-level presentation synthesis of A-G)...")
    findings = {
        "A_spatially_heterogeneous": "5 urban regimes identified via the frozen V2 typology; see typology_accessibility_gap_summary.csv.",
        "B_accessibility_concentrated": "14.6% of cells hold 82.5% of the population's complete-walking-access outcome (C01); "
                                          "confirmed as a real population-distribution property, not a modeling artifact (Phase 8.1).",
        "C_cycling_changes_geography": "Complete everyday-needs access rises from 82.5% (walking, C01) to 95.6% (cycling, C03); "
                                         "2.10M people gain complete access via cycling (C02).",
        "D_cycling_expands_transit": "Up to 4.80M people (RAW) show cycling-only fixed-guideway transit gain (C05); quality-aware "
                                       "combined closure is 341,370 people (C07) -- a large RAW-to-quality-aware gap driven by "
                                       "transit-feed coverage, not network performance.",
        "E_not_all_gaps_solved": "352,939 people remain in cells cycling cannot help (C06) -- genuine destination sparsity.",
        "F_cross_application_convergence": "74.67% of CYCLING_CLOSES_EVERYDAY_GAP cells are top-quartile e-bike Readiness vs a 25% "
                                             "baseline (C08) -- descriptive convergence, not validation.",
        "G_uncertainty_is_part_of_product": "Only 27.29% of cells / 73.84% of population are STRICT_SYNTHESIS_RELIABLE; Silivri and "
                                              "Catalca have zero mapped transit stops; Adalar carries a standing network limitation.",
        "claims_registry_reference": "See registries/claims_registry.csv for the exact-value, denominator-traced version of every claim above.",
    }
    (OUT_DIR / "framework_findings.json").write_text(json.dumps(findings, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {OUT_DIR / 'framework_findings.json'}")


if __name__ == "__main__":
    main()
