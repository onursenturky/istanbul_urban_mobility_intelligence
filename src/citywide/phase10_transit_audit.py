"""Phase 10, Sections 1-3: transit source audit, district/stop-type quality
classification, the two destination systems (A general / B fixed-guideway),
and stop deduplication documentation.

Reuses the ALREADY-FETCHED, cached GTFS feeds (data/raw/transit/main_gtfs,
data/raw/transit/iett_gtfs -- no network access) and the ALREADY-EXISTING
mode-classification + spatial dedup logic in
src/features/transit_infrastructure.py (load_all_transit_stops, which
itself calls dedup_stops with a 20m same-mode buffer -- the SAME
deduplicated stop set that already feeds Phase 8's H_public_transport_access
category, 5,501 stops). No new data acquisition, no re-fetch.

Dedup-logic audit finding (verified directly against the raw CSVs before
writing this script): main_gtfs's stops.csv has parent_station EMPTY for
all 7,073 rows and location_type == '0' for all of them (no station/
platform hierarchy encoded at all); iett_gtfs's stops.csv has no
parent_station column at all. Neither feed provides usable parent/child
station structure, so the existing 20m same-mode spatial buffer is the
only defensible deduplication available from this data -- not a
simplification chosen over a better option that was skipped.
"""

from __future__ import annotations

import json

import geopandas as gpd
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.data.fetch_transit_data import fetch_iett_gtfs, fetch_main_gtfs
from src.features import transit_tag_config as tcfg
from src.features.transit_infrastructure import load_all_transit_stops
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "first_last_mile_transit"

# System B: fixed-guideway / high-capacity modes. Ferry is deliberately
# excluded (contextual/separate, per instruction -- not silently merged
# with rail-based modes despite superficially similar "you board a vehicle
# at a fixed stop" semantics; ferry lacks a fixed physical guideway and its
# network topology/frequency behaves very differently).
SYSTEM_B_MODES = ["metro", "tram", "rail", "metrobus"]
SYSTEM_A_MODES = tcfg.ALL_MODES  # bus, metrobus, metro, tram, rail, ferry -- all six


def main() -> None:
    print("=" * 72)
    print("Phase 10 Sections 1-3: transit source audit + destination systems + dedup")
    print("=" * 72)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/5] Re-auditing raw parent/child-station structure (data-driven, not assumed)...")
    main_dir = fetch_main_gtfs()
    iett_dir = fetch_iett_gtfs()
    main_stops_raw = pd.read_csv(main_dir / "stops.csv", encoding=tcfg.MAIN_GTFS["encoding"], dtype=str)
    iett_stops_raw = pd.read_csv(iett_dir / "stops.csv", encoding=tcfg.IETT_GTFS["encoding"],
                                  sep=tcfg.IETT_GTFS["delimiter"], dtype=str)
    parent_station_audit = {
        "main_gtfs_n_raw_stops": len(main_stops_raw),
        "main_gtfs_n_with_parent_station": int(main_stops_raw["parent_station"].notna().sum()) if "parent_station" in main_stops_raw.columns else 0,
        "main_gtfs_location_type_counts": main_stops_raw["location_type"].value_counts(dropna=False).to_dict(),
        "iett_gtfs_n_raw_stops": len(iett_stops_raw),
        "iett_gtfs_has_parent_station_column": "parent_station" in iett_stops_raw.columns,
        "finding": "Neither feed provides usable parent/child station hierarchy -- main_gtfs's parent_station "
                   "column is empty for all rows and location_type is uniformly '0' (no stations/platforms "
                   "distinguished); iett_gtfs has no parent_station column at all. The existing 20m same-mode "
                   "spatial-buffer dedup (src/features/transit_infrastructure.dedup_stops, STOP_DEDUP_DISTANCE_M="
                   f"{tcfg.STOP_DEDUP_DISTANCE_M}m) is therefore the only defensible deduplication available from "
                   "this data, not a simplification chosen over a better option.",
    }
    print(f"  {parent_station_audit['finding']}")

    print("\n[2/5] Loading deduplicated transit stops (reusing existing frozen logic, no new fetch)...")
    stops, load_diag = load_all_transit_stops(main_dir, iett_dir)
    print(f"  {len(stops)} deduplicated physical access points across {stops['mode'].nunique()} modes")
    print(stops["mode"].value_counts().to_string())

    n_raw_total = load_diag["main_gtfs"]["n_stops_raw"] + load_diag["iett_gtfs"]["n_stops_raw"]
    n_mode_rows_before_dedup = load_diag["main_gtfs"]["n_stop_mode_rows"] + load_diag["iett_gtfs"]["n_stop_mode_rows"]
    dedup_doc = {
        "raw_stop_records_both_feeds": n_raw_total,
        "stop_mode_rows_before_spatial_dedup": n_mode_rows_before_dedup,
        "note_on_stop_mode_rows": "A stop serving >1 in-scope mode (rare) is counted once per mode before dedup; "
                                   "this is intentional multi-mode representation, not a duplication bug.",
        "n_duplicate_stops_removed_by_20m_same_mode_buffer": load_diag["n_duplicate_stops_removed"],
        "n_deduplicated_physical_access_points": len(stops),
        "dedup_logic": f"Two stops of the SAME mode within {tcfg.STOP_DEDUP_DISTANCE_M}m are treated as one "
                       "physical access point (e.g. duplicate platform records, opposite-direction stops mapped "
                       "as separate points close together); stops of DIFFERENT modes at the same physical "
                       "location (e.g. a bus stop next to a metro entrance) are intentionally NOT merged, since "
                       "they represent genuinely different access opportunities.",
        "parent_child_station_logic_used": "None available in either feed (see parent_station_audit) -- dedup is "
                                            "spatial-only, per mode.",
        "counts_by_mode_after_dedup": stops["mode"].value_counts().to_dict(),
        "counts_by_source_feed_after_dedup": stops["source_feed"].value_counts().to_dict(),
        "raw_stop_id_mapping_preserved": "Every deduplicated record retains its own raw_stop_id and stop_id "
                                          "(prefixed main_/iett_); the identity of stops REMOVED as duplicates is "
                                          "not separately itemized here (not retained by the existing dedup_stops "
                                          "function) but the counts above are exact and reproducible from source.",
        "stop_id_not_globally_unique_finding": "534 stop_id values are shared by exactly 2 rows each -- a single "
            "physical stop served by both a regular bus route AND a metrobus route (mode classification is "
            "per-route, and dedup_stops groups by mode, so this multi-mode stop is correctly represented as 2 "
            "distinct rows, not a bug). access_point_id (stop_id + '__' + mode) is the globally-unique key used "
            "for all Phase 10 anchoring/routing.",
    }

    print("\n[3/5] District-level stop counts (re-auditing known limitations from earlier phases)...")
    districts = gpd.read_file(cfg.DATA_PROCESSED / "districts_metric.gpkg")[["district", "geometry"]]
    stops_m = stops.to_crs(cfg.METRIC_CRS) if stops.crs.to_string() != cfg.METRIC_CRS else stops
    joined = gpd.sjoin(stops_m, districts, predicate="within", how="left")
    n_unmatched = int(joined["district"].isna().sum())
    if n_unmatched:
        # nearest-district fallback for stops falling just outside a polygon boundary (coastline slivers)
        unmatched = joined[joined["district"].isna()].drop(columns=["district", "index_right"])
        nearest = gpd.sjoin_nearest(unmatched, districts, how="left")
        joined.loc[joined["district"].isna(), "district"] = nearest["district"].to_numpy()
    print(f"  {n_unmatched} stops needed nearest-district fallback (coastline/boundary slivers)")

    by_district_mode = joined.groupby(["district", "mode"]).size().unstack(fill_value=0)
    for m in tcfg.ALL_MODES:
        if m not in by_district_mode.columns:
            by_district_mode[m] = 0
    by_district_mode["total_stops"] = by_district_mode[tcfg.ALL_MODES].sum(axis=1)
    by_district_mode = by_district_mode.reset_index()
    # Districts with ZERO matched stops (e.g. Silivri, Catalca) never appear in
    # `joined` at all, so they would silently DROP OUT of this table instead of
    # being classified NO_FEED_COVERAGE -- reindex against the full district
    # list and fill true zeros, so the exact districts this phase is meant to
    # flag are not the ones that go missing.
    by_district_mode = districts[["district"]].merge(by_district_mode, on="district", how="left")
    for m in tcfg.ALL_MODES + ["total_stops"]:
        by_district_mode[m] = by_district_mode[m].fillna(0).astype(int)

    known_facts_check = {
        "catalca_total_stops": int(by_district_mode.loc[by_district_mode["district"] == "Çatalca", "total_stops"].sum()),
        "silivri_total_stops": int(by_district_mode.loc[by_district_mode["district"] == "Silivri", "total_stops"].sum()),
        "bahcelievler_total_stops": int(by_district_mode.loc[by_district_mode["district"] == "Bahçelievler", "total_stops"].sum()),
        "gaziosmanpasa_total_stops": int(by_district_mode.loc[by_district_mode["district"] == "Gaziosmanpaşa", "total_stops"].sum()),
        "kagithane_total_stops": int(by_district_mode.loc[by_district_mode["district"] == "Kâğıthane", "total_stops"].sum()),
        "sultangazi_total_stops": int(by_district_mode.loc[by_district_mode["district"] == "Sultangazi", "total_stops"].sum()),
    }
    print(f"  re-audit: {known_facts_check}")

    # Area-normalized density for a fair small-vs-large-district comparison.
    by_district_mode = by_district_mode.merge(
        districts.assign(area_km2=districts.geometry.area / 1e6)[["district", "area_km2"]], on="district", how="left"
    )
    by_district_mode["stops_per_km2"] = (by_district_mode["total_stops"] / by_district_mode["area_km2"]).round(3)
    median_density = float(by_district_mode.loc[by_district_mode["total_stops"] > 0, "stops_per_km2"].median())
    print(f"  citywide median stops_per_km2 (districts with >=1 stop): {median_density:.3f}")

    def classify_district(row):
        if row["total_stops"] == 0:
            return "NO_FEED_COVERAGE"
        if row["district"] in ("Bahçelievler", "Gaziosmanpaşa", "Kâğıthane", "Sultangazi"):
            # Confirmed unusually sparse in earlier phases; keep as a documented judgment call,
            # not a mechanical density cutoff, since these districts are NOT zero-stop.
            return "SUSPECT_FEED_COVERAGE"
        if row["stops_per_km2"] < median_density * 0.25:
            return "SUSPECT_FEED_COVERAGE"
        if row["stops_per_km2"] < median_density * 0.75:
            return "USABLE_WITH_LIMITATION"
        return "GOOD_COVERAGE"

    by_district_mode["transit_data_quality_class"] = by_district_mode.apply(classify_district, axis=1)
    print("\n  district quality classification counts:")
    print(by_district_mode["transit_data_quality_class"].value_counts().to_string())
    print("\n  flagged districts (not GOOD_COVERAGE):")
    print(by_district_mode.loc[by_district_mode["transit_data_quality_class"] != "GOOD_COVERAGE",
                                ["district", "total_stops", "stops_per_km2", "transit_data_quality_class"]]
          .sort_values("total_stops").to_string(index=False))

    by_district_mode.to_csv(OUT_DIR / "transit_district_quality.csv", index=False)
    print(f"\n[save] {OUT_DIR / 'transit_district_quality.csv'}")

    print("\n[4/5] Defining System A (general transit) and System B (fixed-guideway)...")
    stops_out = joined.drop(columns=["index_right"], errors="ignore").copy()
    # stop_id is NOT globally unique: a physical stop serving >1 in-scope mode
    # (e.g. a metrobus corridor stop also served by regular bus routes) gets
    # one row per mode with the SAME stop_id (534 such rows found on audit).
    # access_point_id (stop_id + mode) is the unique key used for all routing/
    # anchoring from here on; stop_id is kept only to identify the underlying
    # physical location.
    stops_out["access_point_id"] = stops_out["stop_id"] + "__" + stops_out["mode"]
    assert stops_out["access_point_id"].is_unique, "access_point_id must be unique"
    stops_out["in_system_a"] = stops_out["mode"].isin(SYSTEM_A_MODES)
    stops_out["in_system_b"] = stops_out["mode"].isin(SYSTEM_B_MODES)
    print(f"  System A (general transit, modes={SYSTEM_A_MODES}): {int(stops_out['in_system_a'].sum())} access points")
    print(f"  System B (fixed-guideway, modes={SYSTEM_B_MODES}): {int(stops_out['in_system_b'].sum())} access points")
    print(f"  Ferry ({int((stops_out['mode']=='ferry').sum())} access points) is IN System A, EXCLUDED from System B.")

    keep_cols = ["access_point_id", "stop_id", "raw_stop_id", "stop_name", "mode", "source_feed", "district",
                 "in_system_a", "in_system_b", "geometry"]
    stops_out[keep_cols].to_parquet(OUT_DIR / "transit_access_point_dedup.csv".replace(".csv", ".parquet"))
    # also write the requested CSV name (non-geometry columns) for easy inspection
    stops_out[[c for c in keep_cols if c != "geometry"]].to_csv(OUT_DIR / "transit_access_point_dedup.csv", index=False)
    print(f"[save] {OUT_DIR / 'transit_access_point_dedup.csv'} (+ .parquet with geometry)")

    summary_by_mode = stops_out.groupby("mode").agg(
        n_access_points=("stop_id", "size"), n_districts=("district", "nunique"),
        in_system_a=("in_system_a", "first"), in_system_b=("in_system_b", "first"),
    ).reset_index()
    summary_by_mode.to_csv(OUT_DIR / "transit_access_point_summary.csv", index=False)
    print(f"[save] {OUT_DIR / 'transit_access_point_summary.csv'}")

    print("\n[5/5] Writing transit_source_audit.json...")
    audit = {
        "main_gtfs_reliability_note": tcfg.MAIN_GTFS["reliability_note"],
        "iett_gtfs_reliability_note": tcfg.IETT_GTFS["reliability_note"],
        "parent_station_audit": parent_station_audit,
        "stop_load_diagnostics": load_diag,
        "dedup_documentation": dedup_doc,
        "known_facts_reaudit": known_facts_check,
        "district_quality_classification_method": "NOT mechanical: NO_FEED_COVERAGE = zero mapped stops; "
            "SUSPECT_FEED_COVERAGE = below 25% of citywide median stop density among served districts, OR one of "
            "the 4 districts already flagged as unusually sparse in earlier phases (Bahçelievler, Gaziosmanpaşa, "
            "Kâğıthane, Sultangazi) despite non-zero counts; USABLE_WITH_LIMITATION = below 75% of median density; "
            "GOOD_COVERAGE = otherwise.",
        "system_definitions": {
            "system_a_general_transit": {"modes": SYSTEM_A_MODES, "question": "Can the resident reach some mapped public transport access point?"},
            "system_b_fixed_guideway": {"modes": SYSTEM_B_MODES, "question": "Can the resident reach a major fixed-guideway/high-capacity transit access point?",
                                          "ferry_treatment": "EXCLUDED from System B -- ferry lacks a fixed physical guideway and behaves differently "
                                                              "operationally from rail-based modes; reported only within System A and descriptively on its own."},
        },
        "n_deduplicated_access_points_total": len(stops_out),
    }
    (OUT_DIR / "transit_source_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {OUT_DIR / 'transit_source_audit.json'}")


if __name__ == "__main__":
    main()
