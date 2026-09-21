"""Phase 4 orchestrator: target discovery, leakage audit, modeling feasibility.

Produces:
  - data/processed/target/target_data_inventory.csv
  - data/processed/target/target_feasibility_report.json
  - data/processed/target/predictor_leakage_audit.csv
  - data/processed/target/temporal_alignment_audit.csv

Does NOT produce candidate_target.parquet or spatial-dependence diagnostics:
per the evidence gathered here, no genuine usable target currently exists
(Outcome D — see the feasibility report for the full justification). Both
outputs are explicitly conditional on a viable target being found.

Run from the project root:
    .venv/bin/python -m src.analysis.build_phase4_target_audit
"""

from __future__ import annotations

import json

import geopandas as gpd
import pandas as pd

from src.analysis.bicification_analysis import load_all_bicification_trips, spatial_feasibility_analysis
from src.analysis.leakage_audit import build_leakage_audit
from src.analysis.target_source_inventory import TARGET_SOURCES
from src.analysis.temporal_alignment import build_temporal_alignment_table
from src.data.fetch_shared_mobility_data import fetch_bicification_full
from src.utils import config as cfg

TARGET_DIR = cfg.PROJECT_ROOT / "data" / "processed" / "target"


def load_grid_and_study_area():
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert len(grid) == 514 and grid["grid_id"].is_unique
    study_area = gpd.read_file(cfg.DATA_PROCESSED / "study_area_metric.gpkg").geometry.iloc[0]
    return grid, study_area


def sampling_bias_checks(trips: gpd.GeoDataFrame) -> dict:
    trips = trips.copy()
    trips["start_date"] = pd.to_datetime(trips["starttime"], errors="coerce", utc=True).dt.date
    by_date = trips.groupby("start_date").size().sort_values(ascending=False)
    n_distinct_dates = trips["start_date"].nunique()
    n_total = len(trips)
    top5_share_pct = round(float(by_date.head(5).sum()) / n_total * 100, 1) if n_total else 0.0
    return {
        "n_distinct_active_days_over_7_months": int(n_distinct_dates),
        "top_5_busiest_days_share_of_all_trips_pct": top5_share_pct,
        "busiest_single_day_trip_count": int(by_date.iloc[0]) if len(by_date) else 0,
        "interpretation": (
            "A reward-app pilot with a fixed, self-selected participant pool typically shows "
            "concentration on specific days (e.g. campaign pushes) rather than a smooth citywide "
            "usage pattern; the day-level concentration above should be read alongside the "
            "session-id-per-trip finding (no persistent user tracking possible) as evidence the "
            "sample reflects a small group's activity, not general population behavior."
        ),
    }


def build_feasibility_tests(bic_diag: dict, spatial_diag: dict) -> dict:
    origin = spatial_diag["origin_distribution"]
    dest = spatial_diag["destination_distribution"]
    return {
        "candidate_target_1_trip_origins": {
            "n_and_pct_zero_cells": {"n_zero": 514 - origin["n_nonzero_cells"], "pct_zero": round(100 - origin["pct_nonzero_cells"], 1)},
            "mean_per_nonzero_cell": origin["mean_per_nonzero_cell"],
            "median_per_nonzero_cell": origin["median_per_nonzero_cell"],
            "max_per_cell": origin["max_per_cell"],
            "total_observations": origin["total_observations"],
            "pct_of_514_cells_with_any_observation": origin["pct_nonzero_cells"],
        },
        "candidate_target_2_trip_destinations": {
            "n_and_pct_zero_cells": {"n_zero": 514 - dest["n_nonzero_cells"], "pct_zero": round(100 - dest["pct_nonzero_cells"], 1)},
            "mean_per_nonzero_cell": dest["mean_per_nonzero_cell"],
            "median_per_nonzero_cell": dest["median_per_nonzero_cell"],
            "max_per_cell": dest["max_per_cell"],
            "total_observations": dest["total_observations"],
            "pct_of_514_cells_with_any_observation": dest["pct_nonzero_cells"],
        },
        "candidate_target_3_station_based": {
            "status": "NOT APPLICABLE — no station-based observation data exists (İSBİKE API closed, no historical station-level counts obtained despite two direct İBB data requests)."
        },
        "candidate_target_4_deployment_reconstruction": {
            "status": "NOT APPLICABLE — no historical fleet/station deployment dataset was found; the current shared-bike system is itself mid-transition with no public station list."
        },
        "temporal_coverage": "7 months (2022-06 to 2022-12), single non-recurring pilot year — no repeated observations over time (e.g. multiple years) to assess trend or seasonal stability.",
        "repeated_observations_over_time": False,
        "sample_size_adequacy": (
            "Not remotely sufficient for spatial modeling at 500m resolution: 626 trips touching the "
            "study area over 7 months yield observations in only ~24-31% of 514 cells, with a median "
            "of 3 observations per non-zero cell. This is a sparse, zero-inflated count with too few "
            "non-zero observations to support a defensible spatial demand model, independent of the "
            "mode-labeling concern below."
        ),
    }


def main() -> None:
    print("=" * 72)
    print("Phase 4 — Target Discovery, Leakage Audit & Modeling Feasibility")
    print("=" * 72)
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    grid, study_area = load_grid_and_study_area()

    # --- 1. Target data inventory ---
    monthly_paths = fetch_bicification_full()
    trips, bic_load_diag = load_all_bicification_trips(monthly_paths)
    spatial_diag = spatial_feasibility_analysis(trips, study_area, grid)
    bias_diag = sampling_bias_checks(trips)

    inventory_rows = [dict(row) for row in TARGET_SOURCES]
    for row in inventory_rows:
        if row["source_name"].startswith("Bicification"):
            row["n_observations"] = bic_load_diag["n_usable_after_coordinate_fix"]
            row["geographic_coverage"] = (
                f"Citywide Istanbul; {spatial_diag['n_trips_with_start_or_end_in_study_area']} of "
                f"{bic_load_diag['n_usable_after_coordinate_fix']} usable trips touch the 3-district study area"
            )
    inventory_df = pd.DataFrame(inventory_rows)
    inventory_path = TARGET_DIR / "target_data_inventory.csv"
    inventory_df.to_csv(inventory_path, index=False)

    # --- 2. Leakage audit ---
    combined = gpd.read_parquet(cfg.DATA_FEATURES / "urban_mobility_features.parquet")
    feature_cols = [c for c in combined.columns if c not in ("grid_id", "district", "land_area_m2", "geometry")]
    leakage_df = build_leakage_audit(feature_cols)
    leakage_path = TARGET_DIR / "predictor_leakage_audit.csv"
    leakage_df.to_csv(leakage_path, index=False)

    # --- 3. Temporal alignment audit ---
    temporal_df = build_temporal_alignment_table()
    temporal_path = TARGET_DIR / "temporal_alignment_audit.csv"
    temporal_df.to_csv(temporal_path, index=False)

    # --- 4. Feasibility tests + final decision ---
    feasibility_tests = build_feasibility_tests(bic_load_diag, spatial_diag)

    decision = {
        "outcome": "D",
        "outcome_label": "No defensible supervised target currently exists for shared bicycle/e-bike demand or deployment",
        "justification": [
            "Priority 1 (trip demand) and priority 2 (origins/destinations): no shared-bike or "
            "e-bike trip dataset exists anywhere found in this search, official or academic. "
            "Bicification is the only real trip-level GPS data located, but its own documentation "
            "describes personal gamified-app bicycle trips, never shared-bike or e-bike usage — "
            "labeling it as such would not be supported by the source.",
            "Even setting the mode-identity concern aside and treating Bicification as a general "
            "active-cycling activity proxy, its scale is inadequate: 626 trips touching the study "
            "area over 7 months, covering only ~24-31% of the 514 grid cells, with no persistent "
            "user ID (every sessionid is unique to one trip) and visible day-level concentration "
            "consistent with a small self-selected participant pool rather than population behavior.",
            "Priority 3 (station-based demand): no station-level rental/return/occupancy dataset "
            "exists — İSBİKE's real-time API is confirmed closed, and two direct İBB open-data "
            "requests for exactly this kind of historical data were closed without a dataset "
            "delivered.",
            "Priority 4 (deployment reconstruction): the current shared-bike system is itself "
            "mid-transition (old system defunct since ~2024, new licensed operators not yet "
            "visible in open data as of the 2026 retrieval date) — there is no historical "
            "deployment record to reconstruct.",
        ],
        "recommendation": (
            "Stop supervised demand/deployment modeling rather than manufacturing a label from "
            "Bicification or any other proxy. The feature table built in Phases 3A-3E remains "
            "valid, real, and reusable. A defensible next step (NOT implemented in this phase) "
            "would be unsupervised spatial typology (e.g. clustering grid cells by their "
            "explanatory profile), scenario analysis, or a transparent, explicitly-labeled "
            "multi-criteria suitability index — none of which claim to predict observed behavior."
        ),
        "spatial_dependence_diagnostics": "SKIPPED — conditional on a viable target existing, per the phase instructions; none was found.",
        "candidate_target_parquet_created": False,
    }

    report = {
        "research_question_priority_evaluated": [
            "1. Shared bicycle/e-bike trip demand (spatial) — NOT FOUND",
            "2. Trip origins/destinations (spatial) — NOT FOUND for shared-bike/e-bike specifically; "
            "found only for general personal cycling (Bicification), see feasibility_tests",
            "3. Station/parking-area demand — NOT FOUND (İSBİKE API closed, data requests refused)",
            "4. Observed deployment reconstruction — NOT FOUND (no historical deployment dataset)",
        ],
        "target_vs_supply_vs_infrastructure_distinction": {
            "demand": "Observed user trips/usage — NOT AVAILABLE for shared bicycles/e-bikes in Istanbul as of this search.",
            "supply_deployment": "Operator station/fleet siting decisions — NOT AVAILABLE historically; current system is mid-transition with no public data.",
            "infrastructure": "The built environment (Phases 3A-3E) — fully available and unaffected by this phase; remains a valid explanatory layer regardless of target availability.",
        },
        "bicification_deep_inspection": {**bic_load_diag, **spatial_diag, "sampling_bias_checks": bias_diag},
        "target_feasibility_tests": feasibility_tests,
        "modeling_unit_feasibility": {
            "500m_grid": "Currently used for all Phase 3 predictors; ~24-31% cell coverage from the only trip-level data found — inadequate regardless of unit choice.",
            "station_based": "Not supported — no station-level observation data exists.",
            "trip_origin_destination_points": "The finest-grained unit the Bicification data could naturally support, but only 546 origin / 543 destination points citywide fall in the study area — far too sparse for point-pattern modeling either.",
            "road_network_segments": "Trips do follow real streets, but 626 trips spread across a road network of hundreds of kilometers gives negligible segment-level volume — not supported.",
            "conclusion": "No spatial unit is well-supported by available data; this is an observation-volume problem, not a unit-choice problem. The 500m grid is not being rejected in favor of a better unit — none of the four exists as a viable option today.",
        },
        "final_decision": decision,
        "output_files": {
            "target_data_inventory_csv": str(inventory_path),
            "predictor_leakage_audit_csv": str(leakage_path),
            "temporal_alignment_audit_csv": str(temporal_path),
            "candidate_target_parquet": None,
        },
    }

    report_path = TARGET_DIR / "target_feasibility_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print("\n--- BICIFICATION DEEP INSPECTION ---")
    print(json.dumps({**bic_load_diag, **spatial_diag}, indent=2, default=str))
    print("\n--- SAMPLING BIAS CHECKS ---")
    print(json.dumps(bias_diag, indent=2))
    print("\n--- LEAKAGE AUDIT SUMMARY ---")
    print(leakage_df["category"].value_counts().to_string())
    print("\n--- FINAL DECISION ---")
    print(json.dumps(decision, indent=2))
    print("\n--- OUTPUT FILES ---")
    for k, v in report["output_files"].items():
        print(f"  {k}: {v}")
    print(f"  target_feasibility_report_json: {report_path}")


if __name__ == "__main__":
    main()
