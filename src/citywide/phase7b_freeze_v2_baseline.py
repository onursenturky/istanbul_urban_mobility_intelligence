"""Phase 7B: freeze the V2 feature baseline manifest --
CITYWIDE_V2_EIGHT_FAMILY_FEATURE_BASELINE.

This freezes the FEATURE TABLE + DICTIONARY only (schema/QA/audit state at
this point in time) -- it is explicitly NOT an analytical model: no EDA
transforms, clustering, MCDA scoring, consensus, or communication products
are computed or referenced here, per the Phase 7B stop condition.

Output: data/processed/citywide/qa/v2_feature_baseline_manifest.json
"""

from __future__ import annotations

import hashlib
import json

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

FEATURES_DIR = cfg.DATA_FEATURES
META_DIR = cfg.DATA_PROCESSED / "metadata"
QA_DIR = cfg.DATA_PROCESSED / "qa"
PBF_DIR = cfg.DATA_RAW / "osm" / "pbf"

VERSION_TAG = "CITYWIDE_V2_EIGHT_FAMILY_FEATURE_BASELINE"


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    pbf_meta = json.loads((PBF_DIR / "turkey-latest.osm.pbf.meta.json").read_text(encoding="utf-8"))
    impact_audit = json.loads((QA_DIR / "phase7b_impact_audit.json").read_text(encoding="utf-8"))

    key_artifacts = {
        "v2_master_feature_table": FEATURES_DIR / "urban_mobility_features_citywide_v2.parquet",
        "v2_feature_dictionary": META_DIR / "feature_dictionary_citywide_v2.csv",
        "road_features_citywide": FEATURES_DIR / "road_features_citywide.parquet",
        "landuse_features_citywide_pbf": FEATURES_DIR / "landuse_features_citywide_pbf.parquet",
        "road_grade_features_citywide": FEATURES_DIR / "road_grade_features_citywide.parquet",
        "cycling_road_overlap_citywide": FEATURES_DIR / "cycling_road_overlap_citywide.parquet",
    }
    key_artifact_hashes = {name: {"path": str(p.relative_to(cfg.PROJECT_ROOT)), "sha256": sha256_of(p)} for name, p in key_artifacts.items()}

    v1_manifest = json.loads((cfg.PROJECT_ROOT / "analysis" / "final_v1" / "final_analysis_manifest.json").read_text(encoding="utf-8"))

    manifest = {
        "version": VERSION_TAG,
        "generated_at_utc": "2026-09-19T19:30:00Z",
        "scope": "Citywide (39 districts, 22,322-cell grid), eight feature families: buildings, POI, population, "
                 "terrain elevation/slope, transit, cycling (İBB-only + resolved road overlap), road network "
                 "(NEW), land-use/green-space (NEW). Road-grade resolved as a ninth dependent sub-family.",
        "explicitly_not_frozen": "No analytical model: no EDA transforms, clustering, MCDA scoring, consensus "
                                  "classes, or final communication products are included in or implied by this baseline.",
        "v1_lineage": {
            "v1_version_tag": v1_manifest["version"],
            "v1_status": "PERMANENTLY UNTOUCHED -- verified via re-hash of all 9 V1 key artifacts immediately "
                         "before V2 construction (see phase7b_impact_audit.json / build_master_features_citywide_v2 run log)",
            "v1_master_table_path": "data/processed/citywide/features/urban_mobility_features_citywide.parquet",
        },
        "phase_7a_acquisition_provenance": {
            "pbf_source": pbf_meta["source_url"],
            "pbf_resolved_url": pbf_meta["resolved_url"],
            "pbf_snapshot_osm_timestamp": pbf_meta["pbf_internal_osm_timestamp"],
            "pbf_sha256": pbf_meta["sha256"],
            "pbf_license": pbf_meta["license"],
            "landuse_polygon_reconstruction_method": "osmium export --geometry-types=polygon (libosmium Area "
            "Assembler) -- NOT GDAL/pyogrio's 'multipolygons' layer, switched after regression testing found the "
            "GDAL heuristic silently corrupted several large forest relations (see "
            "data/processed/citywide/qa/landuse_qa_citywide.json and build_landuse_features_citywide.py docstring "
            "for the full diagnosis and fix).",
            "old_overpass_landuse_caches": "data/raw/osm/landuse_green_by_district/ (22 districts) -- PRESERVED "
            "UNTOUCHED, regression reference only, NOT mixed into any V2 production feature.",
            "intersection_count_method": "pyrosm get_network u/v node-degree (validated against frozen OSMnx "
            "graph-degree on pilot districts: 98.638% exact per-cell agreement, max abs diff 2, total diff 0.032%).",
        },
        "key_artifact_hashes": key_artifact_hashes,
        "feature_inventory": {
            "n_v2_predictors": impact_audit["schema_impact"]["n_v2_predictors"],
            "n_v1_predictors_incl_pending": impact_audit["schema_impact"]["n_v1_predictors"],
            "n_added": impact_audit["schema_impact"]["n_added"],
            "n_resolved_from_pending": impact_audit["schema_impact"]["n_resolved_from_pending"],
            "added_columns": impact_audit["schema_impact"]["added_columns"],
            "feature_dictionary_path": "data/processed/citywide/metadata/feature_dictionary_citywide_v2.csv",
        },
        "classification_summary": "50 READY / 39 READY_WITH_LIMITATION / 5 EXCLUDE_FROM_MODEL (of 94 total V2 "
                                   "predictors) -- see feature_dictionary_citywide_v2.csv for per-feature detail.",
        "existing_feature_integrity": impact_audit["existing_feature_integrity"]["status"],
        "known_limitations_carried_from_v1": v1_manifest["known_limitations"],
        "known_limitations_new_in_v2": [
            "Citywide OSM land-use tagging coverage is very sparse (mean landuse_data_coverage_pct = 9.2%): "
            "residential/commercial/retail/industrial_area_ratio all substantially confound 'no such land use' "
            "with 'not tagged' -- residential_area_ratio correlates rho=0.91 with the coverage diagnostic itself. "
            "retail_area_ratio (99.6% zero) is EXCLUDE_FROM_MODEL; the other three are READY_WITH_LIMITATION.",
            "12 of 21 new/resolved predictors carry a Phase-5C-style scaling risk flag (large exact-zero mass, "
            "extreme RobustScaler magnitude, or high skew) -- none have been transformed; see "
            "phase7b_impact_audit.json 'scaling_risk_audit' for the full per-feature breakdown.",
            "walkable_road_length_m and cycle_accessible_road_length_m are rank-identical (rho=1.00) citywide; "
            "only one should enter any future composite index.",
            "pct_road_network_with_cycle_infrastructure and the existing V1 cycle_infrastructure_density/length_"
            "km_ibb_only features are rho~0.99 correlated but use different normalizations -- a later step should "
            "choose one preferred representation, not carry both into scoring.",
        ],
        "qa_and_audit_references": [
            "data/processed/citywide/qa/phase7a_final_report.json",
            "data/processed/citywide/qa/road_qa_citywide.json",
            "data/processed/citywide/qa/landuse_qa_citywide.json",
            "data/processed/citywide/qa/road_grade_qa_citywide.json",
            "data/processed/citywide/qa/cycling_road_overlap_qa_citywide.json",
            "data/processed/citywide/qa/master_feature_v2_qa.json",
            "data/processed/citywide/qa/phase7b_impact_audit.json",
        ],
        "stop_condition": "Feature baseline only. No Phase 5A screening transforms, clustering, MCDA, "
                          "readiness/opportunity scoring, scenario sensitivity, consensus classes, or final "
                          "communication layer have been (re)run under this version.",
    }

    out_path = QA_DIR / "v2_feature_baseline_manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {out_path}")
    print(f"\nVersion: {VERSION_TAG}")
    print(f"V2 predictors: {manifest['feature_inventory']['n_v2_predictors']}")


if __name__ == "__main__":
    main()
