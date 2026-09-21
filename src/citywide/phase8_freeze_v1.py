"""Freezes 15-Minute Istanbul (walking) as v1, consolidating Phase 8 +
Phase 8.1 validation into one immutable version record. Read-only over
existing outputs; performs no new computation other than hashing.
"""

from __future__ import annotations

import hashlib
import json

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

APP_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city"
VAL_DIR = APP_DIR / "validation"
VERSION_TAG = "15MIN_ISTANBUL_WALKING_V1_FROZEN"


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    manifest8 = json.loads((APP_DIR / "15min_city_manifest.json").read_text(encoding="utf-8"))
    summary8 = json.loads((APP_DIR / "15min_city_summary.json").read_text(encoding="utf-8"))
    val_manifest = json.loads((VAL_DIR / "phase8_1_validation_manifest.json").read_text(encoding="utf-8"))
    val_summary = json.loads((VAL_DIR / "phase8_1_validation_summary.json").read_text(encoding="utf-8"))
    pop_val = json.loads((VAL_DIR / "population_accessibility_validation.json").read_text(encoding="utf-8"))

    key_artifacts = {
        "poi_everyday_needs_taxonomy": APP_DIR / "poi_everyday_needs_taxonomy.csv",
        "poi_network_anchors": APP_DIR / "poi_network_anchors.parquet",
        "grid_proximity_summary": APP_DIR / "grid_proximity_summary.parquet",
        "grid_nearest_service_times": APP_DIR / "grid_nearest_service_times.parquet",
        "accessibility_deficit_classes": APP_DIR / "accessibility_deficit_classes.parquet",
        "corrected_accessibility_quality_flags": VAL_DIR / "corrected_accessibility_quality_flags.parquet",
        "network_component_audit": VAL_DIR / "network_component_audit.csv",
    }

    freeze_record = {
        "version": VERSION_TAG,
        "generated_at_utc": "2026-09-20T09:00:00Z",
        "supersedes": "None -- first frozen version of this application",
        "frozen_scope": "15-Minute Istanbul, WALKING mode only. Cycling accessibility is a SEPARATE, subsequent "
                        "application (not part of this freeze).",
        "phase8_summary": summary8,
        "phase8_1_validation_summary": val_summary,
        "freeze_decision": val_manifest["freeze_decision"],
        "freeze_decision_rationale": val_manifest["freeze_decision_rationale"],
        "headline_result": {
            "pct_cells_complete_15min_access": summary8["pct_cells_complete_15min_access"],
            "pct_population_complete_15min_access_denominator_A_raw": pop_val["denominator_A_all_populated_cells"]["pct_with_complete_access"],
            "pct_population_complete_15min_access_denominator_B_quality_reliable": pop_val["denominator_B_quality_reliable_cells"]["pct_with_complete_access"],
            "pct_population_complete_15min_access_denominator_C_strict_high_confidence": pop_val["denominator_C_strict_high_confidence_cells"]["pct_with_complete_access"],
        },
        "everyday_needs_taxonomy": manifest8["everyday_needs_taxonomy"],
        "key_artifact_hashes": {name: {"path": str(p.relative_to(cfg.PROJECT_ROOT)), "sha256": sha256_of(p)} for name, p in key_artifacts.items() if p.exists()},
        "known_limitations": manifest8["known_quality_limitations"] | {
            "component_quality_correction": "Original Phase 8 ISOLATED_NETWORK_COMPONENT flag was corrected in "
                "Phase 8.1 to distinguish genuine geographic separation (Asian side, RELIABLE_SEPARATE_COMPONENT) "
                "from real network-quality caution (SMALL_COMPONENT_CAUTION, 27 cells only). Use "
                "corrected_accessibility_quality_flags.parquet, not the original accessibility_quality_flags.parquet, "
                "for any downstream quality interpretation.",
        },
        "immutability_notice": "All files under analysis/applications/15min_city/ and "
                               "analysis/applications/15min_city/validation/ are now FROZEN. Any subsequent "
                               "application (e.g. cycling accessibility) must write to a NEW, separate output "
                               "directory and must not modify these files.",
    }

    out_path = APP_DIR / "15MIN_ISTANBUL_WALKING_V1_FROZEN_manifest.json"
    out_path.write_text(json.dumps(freeze_record, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {out_path}")
    print(f"\nVersion: {VERSION_TAG}")
    print(f"Freeze decision: {val_manifest['freeze_decision']}")


if __name__ == "__main__":
    main()
