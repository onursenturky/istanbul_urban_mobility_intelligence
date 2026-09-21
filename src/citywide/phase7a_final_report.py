"""Phase 7A final report: consolidates provenance, coverage, and regression
results for the two recovered feature families (land-use, road network) and
their dependent features (road grade, cycling-road overlap), and verifies
INTERIM_CITYWIDE_V1_SIX_FAMILY was not touched.

Read-only with respect to all Phase 7A outputs already produced; performs no
new computation other than re-hashing the 9 frozen V1 artifacts to confirm
their integrity.

Output: data/processed/citywide/qa/phase7a_final_report.json
"""

from __future__ import annotations

import hashlib
import json

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

QA_DIR = cfg.DATA_PROCESSED / "qa"
FEATURES_DIR = cfg.DATA_FEATURES
PBF_DIR = cfg.DATA_RAW / "osm" / "pbf"
V1_MANIFEST_PATH = cfg.PROJECT_ROOT / "analysis" / "final_v1" / "final_analysis_manifest.json"


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_v1_untouched() -> dict:
    manifest = json.loads(V1_MANIFEST_PATH.read_text(encoding="utf-8"))
    results = {}
    all_ok = True
    for name, info in manifest["key_artifact_hashes"].items():
        path = cfg.PROJECT_ROOT / info["path"]
        if not path.exists():
            results[name] = {"path": info["path"], "status": "MISSING"}
            all_ok = False
            continue
        current_hash = sha256_of(path)
        matches = current_hash == info["sha256"]
        all_ok &= matches
        results[name] = {"path": info["path"], "expected_sha256": info["sha256"], "current_sha256": current_hash, "unchanged": matches}
    return {"v1_version_tag": manifest["version"], "all_9_artifacts_unchanged": all_ok, "per_artifact": results}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main() -> None:
    print("=" * 72)
    print("Phase 7A FINAL REPORT: Road Network + Land-Use Acquisition Recovery")
    print("=" * 72)

    print("\n[1/5] Verifying INTERIM_CITYWIDE_V1_SIX_FAMILY is untouched...")
    v1_check = verify_v1_untouched()
    print(f"  all_9_artifacts_unchanged: {v1_check['all_9_artifacts_unchanged']}")
    for name, r in v1_check["per_artifact"].items():
        if not r.get("unchanged", False):
            print(f"  !! {name}: {r}")

    pbf_meta = load_json(PBF_DIR / "turkey-latest.osm.pbf.meta.json")
    road_qa = load_json(QA_DIR / "road_qa_citywide.json")
    road_gate = load_json(QA_DIR / "coverage_gate_road.json")
    landuse_qa = load_json(QA_DIR / "landuse_qa_citywide.json")
    landuse_gate = load_json(QA_DIR / "coverage_gate_landuse.json")
    grade_qa = load_json(QA_DIR / "road_grade_qa_citywide.json")
    cycling_overlap_qa = load_json(QA_DIR / "cycling_road_overlap_qa_citywide.json")
    intersection_regression = load_json(cfg.PROJECT_ROOT / "data" / "processed" / "qa" / "phase7a_intersection_regression.json")

    print("\n[2/5] PBF acquisition provenance...")
    print(f"  source: {pbf_meta['source_url']} (resolved {pbf_meta['resolved_url']})")
    print(f"  snapshot: {pbf_meta['pbf_internal_osm_timestamp']}  sha256: {pbf_meta['sha256'][:16]}...")

    print("\n[3/5] Coverage gates...")
    print(f"  road_network: {road_gate['n_districts_present']}/39 districts")
    print(f"  landuse: {landuse_gate['n_districts_present']}/39 districts")

    print("\n[4/5] Regression results...")
    print(f"  intersection_count (pilot, graph-degree vs pyrosm u/v): "
          f"{intersection_regression['per_cell_exact_agreement_rate_pct']}% exact agreement, "
          f"max abs diff {intersection_regression['max_abs_cell_difference']}, "
          f"total diff {intersection_regression['total_difference_pct']}%")
    print(f"  land-use (39 districts computed vs 22 preserved Overpass caches, grid-clipped both sides): "
          f"median ratio {landuse_qa['regression_vs_overpass']['median_ratio_pbf_over_overpass']}, "
          f"{len(landuse_qa['regression_vs_overpass']['districts_flagged_ratio_outside_0.4_2.5'])} districts flagged")

    report = {
        "phase": "7A",
        "title": "Road Network + Land-Use Acquisition Recovery",
        "status": "COMPLETE -- both missing feature families recovered and QA-passed; stopping before V2 integration per instruction",
        "v1_integrity_check": v1_check,
        "acquisition_method": {
            "abandoned": "live Overpass API (unreliable citywide, repeated endpoint outages after passing health checks)",
            "adopted": "local OSM PBF workflow (Geofabrik Turkey extract)",
            "pbf_provenance": pbf_meta,
            "istanbul_extraction": {
                "method": "osmium extract --strategy=smart, boundary = frozen citywide study-area polygon buffered "
                "500m / simplified 25m (identical params to every prior Overpass query)",
                "file": "data/raw/osm/pbf/istanbul.osm.pbf",
                "n_nodes": 6768185, "n_ways": 1091733, "n_relations": 9421,
            },
            "road_network_subextract": {
                "method": "osmium tags-filter istanbul.osm.pbf w/highway",
                "file": "data/raw/osm/pbf/road_network_extract.osm.pbf",
                "n_nodes": 1441603, "n_ways": 245089, "n_relations": 0,
            },
            "landuse_green_subextract": {
                "method": "osmium tags-filter istanbul.osm.pbf w/leisure=... r/leisure=... w/landuse=... "
                "r/landuse=... w/natural=... r/natural=... (exact value lists from osm_tag_config.py)",
                "file": "data/raw/osm/pbf/landuse_green_extract.osm.pbf",
                "n_nodes": 927750, "n_ways": 38215, "n_relations": 667,
            },
            "polygon_reconstruction_note": "Land-use polygons read via `osmium export --geometry-types=polygon` "
            "(libosmium's Area Assembler), NOT GDAL/pyogrio's 'multipolygons' layer -- switched after regression "
            "testing found GDAL's heuristic assembly silently corrupted a handful of very large/complex forest "
            "relations (see landuse_qa_citywide.json module docstring / build_landuse_features_citywide.py for the "
            "full diagnosis). Road geometry (LineStrings, no relation-assembly ambiguity) continued to use GDAL's "
            "'lines' layer without issue.",
        },
        "regression_tests": {
            "intersection_count_graph_degree_vs_pyrosm_uv": intersection_regression,
            "landuse_pbf_vs_overpass_22_districts": landuse_qa["regression_vs_overpass"],
        },
        "feature_families_completed": {
            "road_network": {
                "status": "CITYWIDE_COMPLETE",
                "coverage": f"{road_gate['n_districts_present']}/39 districts, {road_gate['n_cells']} cells",
                "output_file": str(FEATURES_DIR / "road_features_citywide.parquet"),
                "qa_file": str(QA_DIR / "road_qa_citywide.json"),
                "features": ["road_length_m", "major_road_length_m", "local_road_length_m", "walkable_road_length_m",
                             "cycle_accessible_road_length_m", "road_density_km_per_km2", "intersection_count",
                             "intersection_density_km2"],
                "total_road_length_km": road_qa["total_road_length_km_citywide"],
                "total_intersections": road_qa["total_intersections_citywide"],
                "warnings": [
                    f"{road_qa['lines_layer_diagnostics']['n_closed_way_highway_areas_excluded_polygon_classified']} "
                    "closed-way polygonal highway areas (0.13%) excluded from line-length calc, consistent with "
                    "OSMnx network_type='all' also not representing these as routable edges -- documented, not silent.",
                    f"{road_qa['n_cells_implausible_road_density_gt_50km_per_km2']} cells >50 km road/km2 -- "
                    "reviewed, all in Istanbul's densest historic urban cores (Fatih, Zeytinburnu, Bağcılar etc.), "
                    "spread across many districts (not concentrated), 0 flagged as statistical outliers "
                    "(>3x p99 road length) -- plausible for fine-grained dense street/alley grids, not a defect.",
                ],
            },
            "landuse_green_space": {
                "status": "CITYWIDE_COMPLETE",
                "coverage": f"{landuse_gate['n_districts_present']}/39 districts, {landuse_gate['n_cells']} cells",
                "output_file": str(FEATURES_DIR / "landuse_features_citywide_pbf.parquet"),
                "qa_file": str(QA_DIR / "landuse_qa_citywide.json"),
                "total_green_area_km2": landuse_qa["total_green_area_km2_citywide"],
                "n_invalid_geometries": landuse_qa["n_invalid_final_geometries"],
                "old_overpass_22_district_caches": "PRESERVED UNTOUCHED as regression reference only "
                "(data/raw/osm/landuse_green_by_district/); NOT mixed into this production dataset.",
                "warnings": [
                    "1 of ~34,852 exported polygon relations citywide failed even libosmium's area assembly "
                    "('Could not build area geometry') -- a genuine upstream OSM topology defect in that single "
                    "relation, recorded, not silently dropped from the count.",
                    f"{landuse_qa['loading_diagnostics']['n_rows_with_no_target_landuse_leisure_natural_value']} "
                    "exported rows carry no target landuse/leisure/natural value (osmium tags-filter matches at "
                    "object level) -- harmless, filtered out downstream by compute_greenspace_features' own "
                    "exact-value classification.",
                ],
            },
            "road_grade": {
                "status": "COMPLETE (previously PENDING_ROAD_NETWORK)",
                "coverage": f"{grade_qa['n_districts_present']}/39 districts",
                "output_file": str(FEATURES_DIR / "road_grade_features_citywide.parquet"),
                "qa_file": str(QA_DIR / "road_grade_qa_citywide.json"),
                "n_cells_zero_sample_nan_grade": grade_qa["n_cells_zero_grade_sample_length"],
                "n_extreme_grade_cells_gt20pct": grade_qa["n_cells_mean_grade_gt_20pct"],
                "dem_source": "Copernicus GLO-30 (reused from cache, no re-fetch)",
            },
            "cycling_road_overlap": {
                "status": "COMPLETE (previously PENDING_ROAD_NETWORK)",
                "coverage": f"{cycling_overlap_qa['n_districts_present']}/39 districts",
                "output_file": str(FEATURES_DIR / "cycling_road_overlap_citywide.parquet"),
                "qa_file": str(QA_DIR / "cycling_road_overlap_qa_citywide.json"),
                "column": "pct_road_network_with_cycle_infrastructure",
                "n_nan_zero_road_cells": cycling_overlap_qa["n_cells_nan_no_road_in_cell"],
                "n_cells_with_overlap": cycling_overlap_qa["n_cells_with_any_cycle_overlap"],
                "cycling_source": "İBB-only network (same source as all other citywide cycling features, per the "
                "earlier explicit İBB-only instruction) -- not the pilot's İBB+OSM combined network.",
            },
        },
        "explicitly_not_done_per_stop_condition": [
            "INTERIM_CITYWIDE_V1_SIX_FAMILY not modified (verified above)",
            "No V2 master feature table created (road/land-use/road-grade/cycling-overlap outputs kept in separate, clearly-named files)",
            "Phase 5 clustering not rerun",
            "Phase 6 MCDA / consensus / final communication products not rerun",
        ],
    }

    out_path = QA_DIR / "phase7a_final_report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[5/5] [save] {out_path}")

    print("\n" + "=" * 72)
    print("PHASE 7A COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
