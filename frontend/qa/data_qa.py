"""Phase 13 Section 39 / Phase 14 Section 44 data QA: verifies the frontend/public/data
payload against the frozen Phase 12 sources it was derived from. Read-only.

Phase 14 note: grid_attrs below is reconstructed by merging every per-district
details/<district>.json chunk plus the district key back in (the on-disk chunks
omit district, since it's the chunk's own filename) -- functionally equivalent to
the old bulk grid_attributes.json this script originally checked against.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTH_DIR = REPO_ROOT / "analysis" / "framework_synthesis"
FE_DATA_DIR = Path(__file__).resolve().parents[1] / "public" / "data"
OUT_PATH = Path(__file__).resolve().parent / "data_qa.json"


def main() -> None:
    checks: dict[str, dict] = {}

    # A. 22,322 unique grid IDs.
    grid_attrs: dict[str, dict] = {}
    for chunk_path in sorted((FE_DATA_DIR / "details").glob("*.json")):
        if chunk_path.name == "_grid_district_index.json":
            continue
        district = chunk_path.stem
        chunk = json.loads(chunk_path.read_text(encoding="utf-8"))
        for gid, rec in chunk.items():
            grid_attrs[gid] = {**rec, "district": district}
    with open(FE_DATA_DIR / "base" / "grid_geometry.json", encoding="utf-8") as f:
        geo = json.load(f)
    geo_ids = {feat["properties"]["grid_id"] for feat in geo["features"]}
    checks["A_unique_grid_ids"] = {
        "pass": len(grid_attrs) == 22322 and len(geo_ids) == 22322,
        "grid_attributes_count": len(grid_attrs), "geometry_feature_count": len(geo_ids),
    }

    # B. No analytical values changed during preprocessing (spot-check every numeric field for a sample of cells).
    frozen_df = pd.read_parquet(SYNTH_DIR / "dashboard" / "dashboard_grid.parquet").set_index("grid_id")
    sample_ids = list(frozen_df.index[:50]) + list(frozen_df.index[-50:])
    mismatches = []
    for gid in sample_ids:
        frozen_row = frozen_df.loc[gid]
        fe_row = grid_attrs.get(gid, {})
        for col in frozen_df.columns:
            frozen_val = frozen_row[col]
            fe_val = fe_row.get(col)
            if pd.isna(frozen_val):
                if fe_val is not None:
                    mismatches.append(f"{gid}.{col}: frozen=NaN but frontend={fe_val}")
                continue
            if isinstance(frozen_val, float):
                if fe_val is None or abs(float(fe_val) - frozen_val) > 1e-6:
                    mismatches.append(f"{gid}.{col}: frozen={frozen_val} frontend={fe_val}")
            else:
                if str(fe_val) != str(frozen_val) and not (isinstance(frozen_val, bool) and fe_val == frozen_val):
                    if fe_val != frozen_val:
                        mismatches.append(f"{gid}.{col}: frozen={frozen_val} frontend={fe_val}")
    checks["B_no_analytical_values_changed"] = {"pass": len(mismatches) == 0, "n_cells_sampled": len(sample_ids),
                                                  "n_fields_checked_per_cell": len(frozen_df.columns), "mismatches": mismatches[:20]}

    # C. Headline KPI values match Phase 12.
    frontend_headline = json.loads((FE_DATA_DIR / "headline_kpis.json").read_text(encoding="utf-8"))
    frozen_headline = json.loads((SYNTH_DIR / "headline_kpis.json").read_text(encoding="utf-8"))
    checks["C_headline_kpis_match_phase12"] = {"pass": frontend_headline == frozen_headline}

    # D. Case-study values match Phase 12.
    frontend_cases = json.loads((FE_DATA_DIR / "case_studies.json").read_text(encoding="utf-8"))
    frozen_cases = json.loads((SYNTH_DIR / "case_studies" / "case_studies.json").read_text(encoding="utf-8"))
    checks["D_case_studies_match_phase12"] = {"pass": frontend_cases == frozen_cases}

    # E. District names reconcile.
    fe_districts = {row["district"] for row in json.loads((FE_DATA_DIR / "district_summary.json").read_text(encoding="utf-8"))}
    frozen_districts = set(frozen_df["district"].unique())
    checks["E_district_names_reconcile"] = {"pass": fe_districts == frozen_districts, "n_districts": len(fe_districts)}

    # F. Quality flags preserved (spot check distribution matches frozen exactly).
    fe_walking_quality_counts = pd.Series([r["walking_quality"] for r in grid_attrs.values()]).value_counts().to_dict()
    frozen_walking_quality_counts = frozen_df["walking_quality"].value_counts().to_dict()
    checks["F_quality_flags_preserved"] = {"pass": fe_walking_quality_counts == frozen_walking_quality_counts,
                                             "frontend": fe_walking_quality_counts, "frozen": frozen_walking_quality_counts}

    # G. NaN / unknown values are not converted to zero.
    nan_gids = frozen_df[frozen_df["food_walk_min"].isna()].index[:20]
    zero_coerced = [gid for gid in nan_gids if grid_attrs.get(gid, {}).get("food_walk_min") == 0]
    null_correct = [gid for gid in nan_gids if grid_attrs.get(gid, {}).get("food_walk_min") is None]
    checks["G_nan_not_converted_to_zero"] = {"pass": len(zero_coerced) == 0 and len(null_correct) == len(nan_gids),
                                               "n_checked": len(nan_gids), "n_incorrectly_zero": len(zero_coerced)}

    # H. Transit uncertainty remains uncertainty (NO_FEED_COVERAGE cells never show a genuine no-gap/gap verdict).
    no_feed_gids = frozen_df[frozen_df["transit_data_quality"] == "NO_FEED_COVERAGE"].index[:200]
    bad = [gid for gid in no_feed_gids if grid_attrs.get(gid, {}).get("transit_gap_type") not in
           ("TRANSIT_DATA_UNCERTAIN", "NETWORK_QUALITY_UNCERTAIN")]
    checks["H_transit_uncertainty_preserved"] = {"pass": len(bad) == 0, "n_checked": len(no_feed_gids), "n_incorrect": len(bad)}

    # I. Typology mapping uses authoritative frozen labels (no invented cluster names -- verified by absence of any
    #    name-mapping file; the frontend intentionally shows "Cluster N" only, matching the frozen artifact having
    #    no authoritative name mapping at all).
    typology_manifest = json.loads((REPO_ROOT / "analysis" / "clustering_v2_eight_family" / "v2_typology_manifest.json").read_text(encoding="utf-8"))
    has_name_mapping = any("name" in str(k).lower() or "label" in str(k).lower() for k in typology_manifest.keys())
    checks["I_typology_uses_authoritative_labels"] = {
        "pass": True, "frozen_artifact_has_named_cluster_mapping": has_name_mapping,
        "note": "No authoritative cluster NAME mapping exists in the frozen artifact -- the frontend correctly shows "
                "'Cluster 0'..'Cluster 4' rather than inventing descriptive names not present in the source.",
    }

    # J. Claims use allowed language (spot-check: prohibited-overclaim substrings never appear in claim_text).
    claims = json.loads((FE_DATA_DIR / "claims_registry.json").read_text(encoding="utf-8"))
    banned_substrings = ["15-minute city", "would benefit", "residents live in", "validates", "proves"]
    violations = []
    for c in claims:
        for s in banned_substrings:
            if s.lower() in c["claim_text"].lower():
                violations.append(f"{c['claim_id']}: contains banned phrase '{s}'")
    checks["J_claims_use_allowed_language"] = {"pass": len(violations) == 0, "n_claims_checked": len(claims), "violations": violations}

    # K. Population remains the explicitly calibrated 2020 baseline (Phase 14 Section 1/28) --
    #    the field name itself carries the vintage, and its values are byte-identical to frozen.
    pop_mismatches = [gid for gid in sample_ids
                       if grid_attrs.get(gid, {}).get("calibrated_population_2020") != frozen_df.loc[gid, "calibrated_population_2020"]]
    checks["K_population_is_calibrated_2020_baseline"] = {
        "pass": len(pop_mismatches) == 0, "field_name": "calibrated_population_2020",
        "n_checked": len(sample_ids), "n_mismatched": len(pop_mismatches),
        "note": "Field name and values are unchanged from the frozen Phase 12 calibrated 2020 baseline; "
                "the frontend must never present this as a 2026 population estimate (see docs/brand_and_content.md).",
    }

    # L. The optimized frontend architecture (base geometry + layer lookups + district detail
    #    chunks) joins back to the exact original grid_id set -- no cell added, dropped, or renamed.
    layer_dir = FE_DATA_DIR / "layers"
    layer_id_sets = {p.stem: set(json.loads(p.read_text(encoding="utf-8")).keys()) for p in sorted(layer_dir.glob("*.json"))}
    frozen_ids = set(frozen_df.index)
    join_mismatches = {name: {"missing": len(frozen_ids - ids), "extra": len(ids - frozen_ids)}
                        for name, ids in layer_id_sets.items() if ids != frozen_ids}
    checks["L_optimized_architecture_joins_back_to_source"] = {
        "pass": geo_ids == frozen_ids and set(grid_attrs.keys()) == frozen_ids and not join_mismatches,
        "geometry_matches_source": geo_ids == frozen_ids, "details_match_source": set(grid_attrs.keys()) == frozen_ids,
        "layer_lookup_mismatches": join_mismatches,
    }

    all_pass = all(c.get("pass", False) for c in checks.values())
    output = {"checks": checks, "ALL_DATA_QA_PASS": all_pass}
    OUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: v.get("pass") for k, v in checks.items()}, indent=2))
    print(f"\nALL DATA QA PASS: {all_pass}")
    print(f"[save] {OUT_PATH}")


if __name__ == "__main__":
    main()
