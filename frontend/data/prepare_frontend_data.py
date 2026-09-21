"""Phase 13 data-prep pipeline: converts the frozen Phase 12 presentation
package into frontend-consumable JSON/GeoJSON under frontend/public/data/.

READS ONLY from analysis/framework_synthesis/ (frozen, Phase 12 output).
WRITES ONLY to frontend/public/data/ (a presentation copy, not analytical
source). No analytical value is recomputed, rounded away, or altered --
only format-converted (parquet -> JSON) and, for the map geometry only,
reused from Phase 12's ALREADY-simplified dashboard_grid_lite.geojson
(no further simplification here).

NaN is preserved as JSON `null` throughout (via pandas .where(pd.notna))
-- never silently converted to 0.

Run from the frontend/data/ directory or the repo root:
    python3 prepare_frontend_data.py
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTH_DIR = REPO_ROOT / "analysis" / "framework_synthesis"
OUT_DIR = Path(__file__).resolve().parents[1] / "public" / "data"


def clean_records(df: pd.DataFrame) -> list[dict]:
    """NaN/NaT -> None (JSON null), never 0 or a string placeholder."""
    return json.loads(df.where(pd.notna(df), None).to_json(orient="records"))


def write_json(obj, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=None, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


# Layer fields actually used to color a map (one page uses 1-3 of these) -- see
# components/PageMapExplorer instances for the authoritative per-page list. Kept out of the
# base geometry entirely; shipped as small standalone lookups instead (Phase 14 Section 5-6).
LAYER_FIELDS = [
    "typology_cluster", "required_categories_walk_15", "required_categories_cycle_15",
    "active_mobility_intervention", "everyday_gap_type", "cycling_gap_closure",
    "transit_gap_type", "cycle_only_transit_gain", "ebike_readiness_robustness",
    "ebike_opportunity_robustness", "cross_app_convergence", "data_confidence",
]


def main() -> None:
    print("=" * 72)
    print("Phase 14 data prep: frozen Phase 12 package -> frontend/public/data")
    print("(geometry / layers / details split -- see docs/map_delivery_decision.md)")
    print("=" * 72)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    transform_log = []

    print("\n[1/10] Loading the full frozen grid table once (source for every step below)...")
    grid_df = pd.read_parquet(SYNTH_DIR / "dashboard" / "dashboard_grid.parquet")
    src_geo_path = SYNTH_DIR / "dashboard" / "dashboard_grid_lite.geojson"
    with open(src_geo_path, encoding="utf-8") as f:
        src_geo = json.load(f)
    size_in_geo = src_geo_path.stat().st_size

    # Same two derived categorical overlays as Phase 13 (Phase 12 MAP_11/MAP_12 specs) --
    # unchanged logic, just computed once here instead of inline further down.
    gain_classes = {"CYCLING_CLOSES_EVERYDAY_GAP", "CYCLING_CLOSES_TRANSIT_GAP", "CYCLING_CLOSES_BOTH"}
    high_readiness_classes = {"ROBUST_HIGH", "FREQUENT_HIGH"}
    reliable_flags = {"RELIABLE", "RELIABLE_SEPARATE_COMPONENT"}

    def convergence(row) -> str:
        gain = row["active_mobility_intervention"] in gain_classes
        high_ready = row["ebike_readiness_robustness"] in high_readiness_classes
        if gain and high_ready:
            return "BOTH_SIGNALS"
        if gain:
            return "ACCESSIBILITY_GAIN_ONLY"
        if high_ready:
            return "HIGH_EBIKE_READINESS_ONLY"
        return "NEITHER"

    def confidence(row) -> str:
        if row["walking_quality"] == "KNOWN_NETWORK_LIMITATION_ADALAR" or row["cycling_quality"] == "KNOWN_NETWORK_LIMITATION_ADALAR":
            return "KNOWN_SPECIAL_CASE"
        network_limited = row["walking_quality"] not in reliable_flags or row["cycling_quality"] not in reliable_flags
        transit_limited = row["transit_data_quality"] != "GOOD_COVERAGE"
        if network_limited and transit_limited:
            return "MULTIPLE_LIMITATIONS"
        if network_limited:
            return "NETWORK_LIMITATION"
        if transit_limited:
            return "TRANSIT_DATA_LIMITATION"
        return "RELIABLE"

    grid_df["cross_app_convergence"] = grid_df.apply(convergence, axis=1)
    grid_df["data_confidence"] = grid_df.apply(confidence, axis=1)

    print("\n[2/10] Base map geometry (grid_id + district ONLY -- no analytical fields)...")
    # This is the ONE payload every exploration page needs just to draw the Istanbul grid.
    # Per-layer coloring values are joined in client-side at runtime from the small files in
    # [3/10] below -- see components/MapView.tsx and lib/mapDataCache.ts.
    base_geo = {"type": "FeatureCollection", "features": []}
    for feat in src_geo["features"]:
        base_geo["features"].append({
            "type": "Feature", "geometry": feat["geometry"],
            "properties": {"grid_id": feat["properties"]["grid_id"], "district": feat["properties"]["district"]},
        })
    base_path = OUT_DIR / "base" / "grid_geometry.json"
    base_path.parent.mkdir(parents=True, exist_ok=True)
    with open(base_path, "w", encoding="utf-8") as f:
        json.dump(base_geo, f, separators=(",", ":"))
    size_base = base_path.stat().st_size
    print(f"  {src_geo_path.name} ({size_in_geo/1e6:.1f}MB, {len(src_geo['features'])} features, ~19 analytical fields) "
          f"-> base/grid_geometry.json ({size_base/1e6:.1f}MB, grid_id+district+geometry only)")
    transform_log.append({"step": "base/grid_geometry.json", "source": str(src_geo_path.relative_to(REPO_ROOT)),
                           "input_size_bytes": size_in_geo, "output_size_bytes": size_base, "feature_count": len(base_geo["features"]),
                           "transformation": "Geometry reused verbatim from Phase 12's lite export (20m tolerance, 5-decimal "
                                              "precision -- unchanged); ALL analytical/categorical properties stripped except "
                                              "grid_id and district. This is the Phase 14 geometry/detail split (Section 5)."})

    print("\n[3/10] Per-layer coloring lookups (small {grid_id: value} files, one per map layer)...")
    layer_total = 0
    for field in LAYER_FIELDS:
        lookup = grid_df.set_index("grid_id")[field].where(pd.notna(grid_df.set_index("grid_id")[field]), None).to_dict()
        # bool -> JSON true/false, everything else passes through as-is (int or str)
        lookup = {k: (bool(v) if isinstance(v, (bool,)) else v) for k, v in lookup.items()}
        size = write_json(lookup, OUT_DIR / "layers" / f"{field}.json")
        layer_total += size
        print(f"  layers/{field}.json: {size/1e3:.1f}KB")
        transform_log.append({"step": f"layers/{field}.json", "source": "analysis/framework_synthesis/dashboard/dashboard_grid.parquet",
                               "output_size_bytes": size, "record_count": len(lookup),
                               "transformation": f"Single column '{field}' extracted as a flat {{grid_id: value}} map -- "
                                                   "fetched only by the page(s) that color their map by this field."})
    print(f"  {len(LAYER_FIELDS)} layer files, {layer_total/1e6:.2f}MB combined (a page loads at most 1-3 of these)")

    print("\n[4/10] Per-district detail chunks (full attribute row per cell, for the Grid Intelligence Card, on demand)...")
    detail_cols = [c for c in grid_df.columns if c not in ("district",)]  # district is the chunk key itself
    details_total = 0
    district_index = {}
    for district, sub in grid_df.groupby("district"):
        chunk = {}
        for _, row in sub[detail_cols].iterrows():
            gid = row["grid_id"]
            rec = row.drop(labels=["grid_id"]).where(pd.notna(row.drop(labels=["grid_id"])), None).to_dict()
            rec = {k: (bool(v) if isinstance(v, (bool,)) else v) for k, v in rec.items()}
            chunk[gid] = rec
            district_index[gid] = district
        safe_name = district.replace("/", "-")
        size = write_json(chunk, OUT_DIR / "details" / f"{safe_name}.json")
        details_total += size
    print(f"  {grid_df['district'].nunique()} district detail files, {details_total/1e6:.2f}MB combined "
          f"(avg {details_total/1e6/grid_df['district'].nunique():.2f}MB each) -- fetched ONE district at a time, on cell selection")
    transform_log.append({"step": "details/<district>.json (39 files)", "source": "analysis/framework_synthesis/dashboard/dashboard_grid.parquet",
                           "output_size_bytes": details_total, "record_count": len(grid_df),
                           "transformation": "Full attribute table (all columns except district, which is the chunk key) "
                                              "grouped by district into 39 separate files -- loaded lazily by "
                                              "lib/mapDataCache.ts only when a cell in that district is selected, not upfront."})

    print("\n[5/10] Grid-to-district index (tiny lookup so a shared ?grid= URL works even without ?district=)...")
    size = write_json(district_index, OUT_DIR / "details" / "_grid_district_index.json")
    print(f"  details/_grid_district_index.json: {size/1e3:.1f}KB, {len(district_index)} entries")
    transform_log.append({"step": "details/_grid_district_index.json", "source": "analysis/framework_synthesis/dashboard/dashboard_grid.parquet",
                           "output_size_bytes": size, "record_count": len(district_index),
                           "transformation": "grid_id -> district flat map, so the Grid Intelligence Card can resolve which "
                                              "district chunk to fetch even if a shared URL omits the district param."})

    print("\n[6/10] District summary...")
    dist_df = pd.read_parquet(SYNTH_DIR / "dashboard" / "dashboard_district_summary.parquet")
    dist_records = clean_records(dist_df)
    size = write_json(dist_records, OUT_DIR / "district_summary.json")
    print(f"  {len(dist_records)} districts, {size/1e3:.1f}KB")
    transform_log.append({"step": "district_summary.json", "source": "analysis/framework_synthesis/dashboard/dashboard_district_summary.parquet",
                           "output_size_bytes": size, "record_count": len(dist_records), "transformation": "Parquet -> JSON array, no changes."})

    print("\n[7/10] District profiles (richer per-district structure)...")
    profiles_df = pd.read_parquet(SYNTH_DIR / "district_profiles.parquet")
    # a few columns are JSON-encoded strings (typology composition, gap-type counts) -- decode them for direct FE use
    for col in ["typology_composition_pct_population", "common_everyday_gap_types", "common_cycling_closure_types"]:
        profiles_df[col] = profiles_df[col].apply(json.loads)
    profiles_records = json.loads(profiles_df.to_json(orient="records"))
    size = write_json(profiles_records, OUT_DIR / "district_profiles.json")
    print(f"  {len(profiles_records)} district profiles, {size/1e3:.1f}KB")
    transform_log.append({"step": "district_profiles.json", "source": "analysis/framework_synthesis/district_profiles.parquet",
                           "output_size_bytes": size, "record_count": len(profiles_records),
                           "transformation": "Parquet -> JSON array; 3 nested JSON-string columns decoded into native objects for direct FE consumption."})

    print("\n[8/10] Registries (KPI, map layer, chart, claims, methodology)...")
    for name, rel in [("kpi_registry", "registries/kpi_registry.csv"), ("map_layer_registry", "registries/map_layer_registry.csv"),
                       ("chart_registry", "registries/chart_registry.csv"), ("claims_registry", "registries/claims_registry.csv"),
                       ("methodology_registry", "methodology/methodology_registry.csv")]:
        df = pd.read_csv(SYNTH_DIR / rel)
        records = clean_records(df)
        size = write_json(records, OUT_DIR / f"{name}.json")
        print(f"  {name}: {len(records)} rows, {size/1e3:.1f}KB")
        transform_log.append({"step": f"{name}.json", "source": f"analysis/framework_synthesis/{rel}", "output_size_bytes": size,
                               "record_count": len(records), "transformation": "CSV -> JSON array, no changes."})

    print("\n[9/10] Case studies, headline KPIs, framework findings, framework architecture (JSON copies)...")
    for name, rel in [("case_studies", "case_studies/case_studies.json"), ("headline_kpis", "headline_kpis.json"),
                       ("framework_findings", "framework_findings.json"), ("framework_architecture", "methodology/framework_architecture.json"),
                       ("dashboard_information_architecture", "dashboard/dashboard_information_architecture.json"),
                       ("dashboard_filter_spec", "dashboard/dashboard_filter_spec.json")]:
        obj = json.loads((SYNTH_DIR / rel).read_text(encoding="utf-8"))
        size = write_json(obj, OUT_DIR / f"{name}.json")
        print(f"  {name}.json: {size/1e3:.1f}KB")
        transform_log.append({"step": f"{name}.json", "source": f"analysis/framework_synthesis/{rel}", "output_size_bytes": size,
                               "transformation": "Verbatim JSON copy (re-serialized without pretty-printing to reduce size)."})

    print("\n[10/10] Framework narrative (markdown copy), Data QA, and manifest...")
    md_src = SYNTH_DIR / "methodology" / "framework_narrative.md"
    md_dst = OUT_DIR / "framework_narrative.md"
    shutil.copyfile(md_src, md_dst)
    print(f"  copied {md_src.name}")

    print("\n  Data QA on the prepared payload (grid_id coverage, no value corruption)...")
    assert grid_df["grid_id"].nunique() == 22322, "expected exactly 22322 unique grid_ids"
    base_grid_ids = {feat["properties"]["grid_id"] for feat in base_geo["features"]}
    assert base_grid_ids == set(grid_df["grid_id"]), "base geometry grid_ids must exactly match the frozen grid table"
    assert base_grid_ids == set(district_index.keys()), "every geometry grid_id must resolve to a district detail chunk"
    # spot-check a couple of layer lookups round-trip against the source table
    typology_lookup = json.loads((OUT_DIR / "layers" / "typology_cluster.json").read_text(encoding="utf-8"))
    sample_gid = grid_df.iloc[0]["grid_id"]
    sample_val = grid_df.iloc[0]["typology_cluster"]
    sample_val = None if pd.isna(sample_val) else sample_val
    assert typology_lookup[sample_gid] == sample_val, "layer lookup value must match the frozen source table exactly"
    # spot-check: NaN in source parquet must be None in output JSON, never 0
    nan_row = grid_df[grid_df["food_walk_min"].isna()].iloc[0]
    nan_gid, nan_district = nan_row["grid_id"], nan_row["district"]
    detail_chunk = json.loads((OUT_DIR / "details" / f"{nan_district.replace('/', '-')}.json").read_text(encoding="utf-8"))
    assert detail_chunk[nan_gid]["food_walk_min"] is None, "NaN must serialize to null, not 0"
    print(f"  22,322 unique grid_ids confirmed across base geometry, layer lookups, and {grid_df['district'].nunique()} "
          f"district detail chunks; NaN->null spot-check passed for {nan_gid}")

    total_size = sum(t.get("output_size_bytes", 0) for t in transform_log)
    initial_payload = size_base + layer_total  # what a map page must fetch before it can render + color
    manifest = {
        "purpose": "Documents every Phase 14 frontend data transformation, per instruction -- source is always "
                   "analysis/framework_synthesis/ (frozen Phase 12 output), output is always frontend/public/data/. "
                   "Phase 14 replaces the Phase 13 monolithic grid_map.geojson + grid_attributes.json with a "
                   "base geometry / per-layer lookup / per-district detail split -- see docs/map_delivery_decision.md "
                   "and docs/production_architecture.md.",
        "no_analytical_values_altered": True,
        "nan_handling": "Preserved as JSON null throughout, verified by an explicit spot-check below.",
        "transformations": transform_log,
        "total_output_size_bytes": total_size, "total_output_size_mb": round(total_size / 1e6, 2),
        "initial_map_payload_bytes": initial_payload, "initial_map_payload_mb": round(initial_payload / 1e6, 2),
        "qa_spot_checks": {
            "unique_grid_ids": 22322,
            "base_geometry_grid_ids_match_source_table": True,
            "every_grid_id_resolves_to_a_district_chunk": True,
            "layer_lookup_value_matches_source_table": True,
            "nan_serializes_to_null": True,
        },
    }
    write_json(manifest, OUT_DIR.parent.parent / "qa" / "_data_prep_manifest.json")
    print(f"[save] frontend/qa/_data_prep_manifest.json")
    print(f"\nTotal frontend/public/data payload: {total_size/1e6:.1f}MB across {len(transform_log)} files")
    print(f"Initial map payload (base geometry + all layer lookups): {initial_payload/1e6:.2f}MB "
          f"(a page in practice fetches base + only its own 1-3 active layers, so real first paint is smaller still)")


if __name__ == "__main__":
    main()
