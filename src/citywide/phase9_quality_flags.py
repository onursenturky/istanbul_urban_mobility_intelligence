"""Phase 9, quality flags for CYCLING accessibility -- built proactively
using the SAME corrected-classification method Phase 8.1 validated for
walking (component_class + Adalar + questionable-anchor), rather than
Phase 8's original over-broad approach. Uses the cycling-specific
component classes derived in phase9_network_and_anchor_audit.py
(cycling_network_component_audit.csv), NOT walking's exact thresholds.
"""

from __future__ import annotations

import json

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

OUT_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "cycling_accessibility"
NET_DIR = cfg.PROJECT_ROOT / "analysis" / "network_intelligence"


def corrected_flag(row, largest_component_id: int) -> str:
    if row["district"] == "Adalar":
        return "KNOWN_NETWORK_LIMITATION_ADALAR"
    if row["cycling_snap_quality"] == "QUESTIONABLE":
        return "QUESTIONABLE_ANCHOR"
    cc = row["component_class"]
    if cc == "MAJOR_VALID_COMPONENT":
        return "RELIABLE" if row["cycling_component_id"] == largest_component_id else "RELIABLE_SEPARATE_COMPONENT"
    if cc in ("LARGE_LOCAL_VALID_COMPONENT", "SMALL_LOCAL_COMPONENT"):
        return "RELIABLE_SEPARATE_COMPONENT"
    if cc == "KNOWN_NETWORK_LIMITATION":
        return "KNOWN_NETWORK_LIMITATION_ADALAR"
    return "SMALL_COMPONENT_CAUTION"


def main() -> None:
    print("=" * 72)
    print("Phase 9: cycling accessibility quality flags (corrected classification, applied from the start)")
    print("=" * 72)

    anchors = pd.read_parquet(NET_DIR / "grid_network_anchors.parquet",
                               columns=["grid_id", "cycling_anchor_node", "cycling_snap_quality", "cycling_has_local_node"])
    membership = pd.read_parquet(OUT_DIR / "_grid_cycling_component_membership.parquet")
    comp_df = pd.read_csv(OUT_DIR / "cycling_network_component_audit.csv")

    merged = anchors.merge(membership[["grid_id", "district", "cycling_component_id"]], on="grid_id", how="left")
    merged = merged.merge(
        comp_df[["component_id", "component_class", "n_nodes", "n_anchored_grid_cells", "calibrated_population"]]
        .rename(columns={"component_id": "cycling_component_id", "n_nodes": "component_n_nodes",
                          "n_anchored_grid_cells": "component_n_anchored_cells",
                          "calibrated_population": "component_population"}),
        on="cycling_component_id", how="left",
    )
    largest_component_id = int(comp_df.loc[comp_df["n_nodes"].idxmax(), "component_id"])
    merged["corrected_quality_flag"] = merged.apply(corrected_flag, axis=1, largest_component_id=largest_component_id)

    print("\nCorrected cycling quality flag distribution:")
    print(merged["corrected_quality_flag"].value_counts().to_string())

    out_cols = ["grid_id", "district", "cycling_snap_quality", "cycling_has_local_node",
                "cycling_component_id", "component_class", "component_n_nodes",
                "component_n_anchored_cells", "component_population", "corrected_quality_flag"]
    merged[out_cols].to_parquet(OUT_DIR / "cycling_accessibility_quality_flags.parquet")
    print(f"\n[save] {OUT_DIR / 'cycling_accessibility_quality_flags.parquet'}")

    diag = {
        "method": "Same evidence-based classification method validated in Phase 8.1 for walking, applied here "
                  "from the start (no separate 'original' vs 'corrected' pass needed for cycling since this is "
                  "the FIRST classification, not a revision).",
        "flag_counts": merged["corrected_quality_flag"].value_counts().to_dict(),
        "key_finding_adalar": "Adalar has ZERO actual cycling-network nodes (unlike its 2-node walking component); "
                               "all Adalar grid cells anchor ACROSS WATER to the mainland Asian-side mega-component. "
                               "Every Adalar cell is flagged KNOWN_NETWORK_LIMITATION_ADALAR regardless of which "
                               "component its anchor node falls in -- any 'cycling accessibility' value for Adalar "
                               "is an artifact of cross-water snapping, not a real cycling route.",
        "largest_component_id": largest_component_id,
    }
    (OUT_DIR / "_phase9_quality_flags_diagnostics.json").write_text(json.dumps(diag, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {OUT_DIR / '_phase9_quality_flags_diagnostics.json'} (intermediate)")


if __name__ == "__main__":
    main()
