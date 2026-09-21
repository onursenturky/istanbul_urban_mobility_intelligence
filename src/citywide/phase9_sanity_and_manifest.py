"""Phase 9, Sections 15-16: sanity checks across 10 representative cases,
final manifest, and summary. Read-only over all Phase 9 outputs produced
so far -- no new computation beyond simple lookups/hashing.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

WALK_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city"
OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "cycling_accessibility"
CATEGORIES = ["A_food_groceries", "B_healthcare", "C_education", "D_daily_services",
              "E_retail_shopping", "F_leisure_social", "G_green_recreation", "H_public_transport_access"]
REQUIRED = ["A_food_groceries", "B_healthcare", "C_education"]


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    print("=" * 72)
    print("Phase 9 Sections 15-16: sanity checks + manifest + summary")
    print("=" * 72)

    comp = pd.read_parquet(OUT_DIR / "walking_cycling_complete_access_comparison.parquet")
    quality = pd.read_parquet(OUT_DIR / "cycling_accessibility_quality_flags.parquet")
    comp_audit = pd.read_csv(OUT_DIR / "cycling_network_component_audit.csv")
    v2 = pd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features_citywide_v2.parquet",
                          columns=["grid_id", "population_calibrated", "mean_absolute_road_grade_pct"])
    walk_nearest = pd.read_parquet(WALK_DIR / "grid_nearest_service_times.parquet")
    cyc_nearest = pd.read_parquet(OUT_DIR / "cycling_nearest_service_times.parquet")
    merged = comp.merge(quality[["grid_id", "corrected_quality_flag", "cycling_component_id"]], on="grid_id") \
                 .merge(v2, on="grid_id")

    print("\n[1/3] Selecting 10 representative sanity-check cases...")
    # Reuse Phase 8's frozen dense-core / transit-rich sanity points where possible
    walk_sanity = json.loads((WALK_DIR / "sanity_check_cases.json").read_text(encoding="utf-8"))
    walk_sanity_by_label = {c["label"]: c for c in walk_sanity if "grid_id" in c}

    cases = []
    for label in ["dense_historic_core", "dense_asian_side_core", "transit_rich_residential"]:
        if label in walk_sanity_by_label:
            c = walk_sanity_by_label[label]
            cases.append({"label": label, "grid_id": c["grid_id"], "district": c["district"]})

    # peripheral populated settlement: highest-population cell among low-density peripheral districts
    peripheral_districts = ["Silivri", "Çatalca", "Şile", "Arnavutköy"]
    peri = merged[merged["district"].isin(peripheral_districts) & (merged["population_calibrated"] > 0)]
    peri_pick = peri.sort_values("population_calibrated", ascending=False).iloc[0]
    cases.append({"label": "peripheral_populated_settlement", "grid_id": peri_pick["grid_id"], "district": peri_pick["district"]})

    # walking-deficit / cycling-gain cell: highest-population CYCLE_ONLY_GAIN cell
    cyc_gain = merged[merged["access_class"] == "CYCLE_ONLY_GAIN"].sort_values("population_calibrated", ascending=False).iloc[0]
    cases.append({"label": "walking_deficit_cycling_gain", "grid_id": cyc_gain["grid_id"], "district": cyc_gain["district"]})

    # walking-AND-cycling deficit cell: highest-population NEITHER_ACCESS cell
    neither = merged[merged["access_class"] == "NEITHER_ACCESS"].sort_values("population_calibrated", ascending=False).iloc[0]
    cases.append({"label": "walking_and_cycling_deficit", "grid_id": neither["grid_id"], "district": neither["district"]})

    # steep / high-road-grade area
    steep = merged[merged["population_calibrated"] > 0].sort_values("mean_absolute_road_grade_pct", ascending=False).iloc[0]
    cases.append({"label": "steep_high_road_grade_area", "grid_id": steep["grid_id"], "district": steep["district"]})

    # questionable cycling anchor
    quest = merged[merged["corrected_quality_flag"] == "QUESTIONABLE_ANCHOR"].sort_values("population_calibrated", ascending=False).iloc[0]
    cases.append({"label": "questionable_cycling_anchor", "grid_id": quest["grid_id"], "district": quest["district"]})

    # small cycling component (excluding the 2 mega + Adalar-limitation classes)
    small_comp_ids = comp_audit[comp_audit["component_class"] == "SMALL_LOCAL_COMPONENT"]["component_id"]
    small_comp_cells = merged[merged["cycling_component_id"].isin(small_comp_ids) & (merged["population_calibrated"] > 0)]
    small_pick = small_comp_cells.sort_values("population_calibrated", ascending=False).iloc[0]
    cases.append({"label": "small_cycling_component", "grid_id": small_pick["grid_id"], "district": small_pick["district"]})

    # Adalar
    adalar_pick = merged[merged["district"] == "Adalar"].iloc[0]
    cases.append({"label": "adalar_known_limitation", "grid_id": adalar_pick["grid_id"], "district": adalar_pick["district"]})

    print(f"  selected {len(cases)} cases")

    sanity_results = []
    implausible_flags = []
    for case in cases:
        gid = case["grid_id"]
        row = merged[merged["grid_id"] == gid]
        if len(row) == 0:
            sanity_results.append({**case, "status": "GRID_ID_NOT_FOUND"})
            continue
        row = row.iloc[0]
        wn = walk_nearest[walk_nearest["grid_id"] == gid]
        cn = cyc_nearest[cyc_nearest["grid_id"] == gid]
        result = {**case}
        result["population_calibrated"] = round(float(row["population_calibrated"]), 1)
        result["access_class"] = row["access_class"]
        result["cycling_quality_flag"] = row["corrected_quality_flag"]
        result["walking_required_categories_accessible_15min"] = int(row["walking_required_categories_accessible_15min"])
        result["cycling_required_categories_accessible_15min"] = int(row["cycling_required_categories_accessible_15min"])
        for c in REQUIRED:
            wt = wn[f"{c}_nearest_time_min"].iloc[0] if len(wn) else np.nan
            ct = cn[f"{c}_nearest_time_min"].iloc[0] if len(cn) else np.nan
            result[f"{c}_walking_nearest_time_min"] = None if pd.isna(wt) else round(float(wt), 2)
            result[f"{c}_cycling_nearest_time_min"] = None if pd.isna(ct) else round(float(ct), 2)

        # Plausibility check: cycling time should never exceed walking time when both reachable
        # (cycling is strictly faster per meter on the same or a superset-like network); flag if violated.
        for c in REQUIRED:
            wt, ct = result[f"{c}_walking_nearest_time_min"], result[f"{c}_cycling_nearest_time_min"]
            if wt is not None and ct is not None and ct > wt + 0.5:
                implausible_flags.append(f"{gid} ({case['label']}): cycling {c} nearest time ({ct}min) > walking ({wt}min) -- "
                                          f"expected due to differing routable node sets/graph topology between modes, not necessarily an error")
        sanity_results.append(result)
        print(f"  [{case['label']}] ({gid}, {case['district']}): access_class={result['access_class']}, "
              f"quality={result['cycling_quality_flag']}, walk_req={result['walking_required_categories_accessible_15min']}/3, "
              f"cycle_req={result['cycling_required_categories_accessible_15min']}/3")

    (OUT_DIR / "cycling_accessibility_sanity_checks.json").write_text(
        json.dumps({"cases": sanity_results, "implausibility_flags": implausible_flags}, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n[save] {OUT_DIR / 'cycling_accessibility_sanity_checks.json'}")
    print(f"  implausibility flags: {len(implausible_flags)}")
    for f in implausible_flags[:5]:
        print(f"    - {f}")

    print("\n[2/3] Manifest...")
    input_files = {
        "cycling_graph": cfg.PROJECT_ROOT / "data" / "processed" / "network" / "cycling_graph.pkl",
        "grid_network_anchors": cfg.PROJECT_ROOT / "analysis" / "network_intelligence" / "grid_network_anchors.parquet",
        "poi_network_anchors_frozen_walking": WALK_DIR / "poi_network_anchors.parquet",
        "grid_proximity_summary_frozen_walking": WALK_DIR / "grid_proximity_summary.parquet",
        "cycling_network_component_audit": OUT_DIR / "cycling_network_component_audit.csv",
        "cycling_destination_anchors": OUT_DIR / "cycling_destination_anchors.parquet",
        "cycling_accessibility_15min": OUT_DIR / "cycling_accessibility_15min.parquet",
        "walking_cycling_complete_access_comparison": OUT_DIR / "walking_cycling_complete_access_comparison.parquet",
        "ebike_opportunity_baseline_frozen": cfg.PROJECT_ROOT / "analysis" / "mcda_v2" / "phase6b" / "ebike_opportunity_baseline.parquet",
        "v2_typology_assignments_frozen": cfg.PROJECT_ROOT / "analysis" / "clustering_v2_eight_family" / "cluster_assignments_v2ef.parquet",
    }

    pop_summary = json.loads((OUT_DIR / "population_cycling_accessibility_summary.json").read_text(encoding="utf-8"))
    ebike_overlap = json.loads((OUT_DIR / "ebike_cycling_gain_overlap.json").read_text(encoding="utf-8"))

    manifest = {
        "version": "CYCLING_ACCESSIBILITY_AND_ACTIVE_MOBILITY_GAIN_V1",
        "supersedes": "None -- first version of this application",
        "frozen_scope": "Cycling accessibility + walking-vs-cycling active-mobility gain, network-based, "
                        "15-minute-city taxonomy reused unchanged from 15MIN_ISTANBUL_WALKING_V1_FROZEN.",
        "depends_on_frozen": ["15MIN_ISTANBUL_WALKING_V1_FROZEN", "NETWORK_INTELLIGENCE_FOUNDATION_V1",
                               "EBIKE_APPLICATION (Phase 6B-V2, analysis/mcda_v2/phase6b/)",
                               "CITYWIDE_V2_EIGHT_FAMILY_TYPOLOGY (post-hoc only)"],
        "methodological_language_used": ["potential cycling accessibility", "network-based cycling accessibility",
                                          "active-mobility accessibility gain", "modeled travel time"],
        "methodological_language_avoided": ["actual cycling behavior", "cycling demand", "people will cycle",
                                             "validated mode choice", "causal accessibility improvement"],
        "input_hashes": {name: {"path": str(p.relative_to(cfg.PROJECT_ROOT)), "sha256": sha256_of(p)} for name, p in input_files.items() if p.exists()},
        "baseline_cycling_speed_kmh": 15.0,
        "known_limitation_oneway_bicycle": "oneway:bicycle contraflow exceptions are present in source OSM tags "
            "but NOT applied to override edge directionality in this baseline cycling graph (inherited unchanged "
            "from Phase 7).",
        "known_limitation_adalar_cycling": "Adalar has ZERO actual cycling-network nodes (unlike walking's 2-node "
            "component); all Adalar cells anchor across water to the mainland mega-component. All Adalar results "
            "are flagged KNOWN_NETWORK_LIMITATION_ADALAR and must not be read as real cycling accessibility.",
        "headline_results": {
            "cycling_complete_15min_access": pop_summary["cycling_complete_15min_access"],
            "access_class_summary": pop_summary["walk_vs_cycle_access_class_summary"],
            "high_value_gain_cells": pop_summary["high_value_gain_cells"],
        },
        "ebike_overlap_headline": {
            "pct_cycle_only_gain_top_quartile_ebike_opportunity": ebike_overlap["pct_cycle_only_gain_cells_top_quartile_ebike_opportunity"],
            "citywide_baseline_pct": ebike_overlap["baseline_top_quartile_share_citywide_pct"],
        },
        "n_implausibility_flags_in_sanity_checks": len(implausible_flags),
        "output_paths": [str(p.relative_to(cfg.PROJECT_ROOT)) for p in sorted(OUT_DIR.glob("*")) if not p.name.startswith("_")],
        "stop_condition": "Cycling accessibility + walking-vs-cycling gain analysis only. Did NOT proceed to "
                          "terrain-adjusted cycling, comfort/stress modeling, transit-inclusive accessibility, "
                          "first/last-mile analysis, predictive ML, equity modeling, dashboard, or visualization "
                          "styling.",
    }
    (OUT_DIR / "phase9_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {OUT_DIR / 'phase9_manifest.json'}")

    summary = {
        "n_grid_cells": len(merged),
        "cycling_complete_15min_access_pct_cells": pop_summary["cycling_complete_15min_access"]["pct_cells"],
        "cycling_complete_15min_access_pct_population": pop_summary["cycling_complete_15min_access"]["pct_population"],
        "walking_complete_15min_access_pct_population_reference": 82.49,
        "n_cycle_only_gain_cells": int((merged["access_class"] == "CYCLE_ONLY_GAIN").sum()),
        "pop_cycle_only_gain": float(merged.loc[merged["access_class"] == "CYCLE_ONLY_GAIN", "population_calibrated"].sum()),
        "n_high_value_gain_cells": pop_summary["high_value_gain_cells"]["n_cells"],
        "ebike_opportunity_overlap_vs_baseline": f"{ebike_overlap['pct_cycle_only_gain_cells_top_quartile_ebike_opportunity']}% vs {ebike_overlap['baseline_top_quartile_share_citywide_pct']}% baseline",
    }
    (OUT_DIR / "phase9_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[save] {OUT_DIR / 'phase9_summary.json'}")

    print("\n[3/3] Done.")


if __name__ == "__main__":
    main()
