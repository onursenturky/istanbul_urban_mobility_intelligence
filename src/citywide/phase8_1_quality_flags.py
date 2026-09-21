"""Phase 8.1 step 2: data-driven component classification + corrected
accessibility quality flags. Does NOT recompute accessibility -- only
reclassifies the already-computed results' quality interpretation.

Classification thresholds (derived from network_component_audit.csv's
actual size/population distribution, not chosen a priori):

  MAJOR_VALID_COMPONENT: the two components with >500,000 nodes each
    (ranks 1-2). This threshold falls squarely inside the single largest
    gap in the entire distribution (log10 gap of 2.71 between rank 2's
    521,850 nodes and rank 3's 1,021 -- every OTHER consecutive gap in the
    distribution is <=0.24 log10, i.e. a <2x change). Together these two
    components hold 99.28% of all network nodes, 99.998% of anchored
    population, and span 25 + 14 districts respectively (European side and
    Asian side) -- unambiguously real, large, internally-coherent regional
    networks. A cell here being unable to reach the OTHER side is a real
    geographic fact (no walkable Bosphorus crossing), not a quality defect.

  Among the remaining 565 components (max 1,021 nodes, median 5, p90 34):
  LARGE_LOCAL_VALID_COMPONENT: >=1 anchored grid cell AND calibrated
    population >= 1,000 -- a real, substantively populated local network,
    genuinely separate from the two mega-components (e.g. a coastal
    neighborhood cut off by a highway with no pedestrian crossing).
  SMALL_LOCAL_COMPONENT: >=1 anchored grid cell AND 0 < population < 1,000
    -- a real but minor local network (a handful of buildings/a small
    settlement).
  QUESTIONABLE_FRAGMENT: 0 anchored grid cells, OR >=1 cell with exactly
    0 recorded population -- most likely a genuine small mapping/topology
    gap (a short dead-end path, a gated-complex service road not linked to
    the surrounding grid) rather than a real, separately-functioning
    neighborhood. 463 of the 565 tail components (82%) have ZERO anchored
    grid cells at all -- they do not affect any cell's accessibility
    result and are catalogued for completeness only.
  KNOWN_NETWORK_LIMITATION: any component whose ONLY district is Adalar
    (confirmed: exactly one such component, 2 nodes, 2 anchored cells, 0
    population) -- matches the already-documented Phase 7/8 Adalar
    network-coverage limitation.
"""

from __future__ import annotations

import json

import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

APP_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city"
VAL_DIR = APP_DIR / "validation"

MAJOR_NODE_THRESHOLD = 500_000
LARGE_LOCAL_POP_THRESHOLD = 1_000


def classify_component(row) -> str:
    if row["n_nodes"] >= MAJOR_NODE_THRESHOLD:
        return "MAJOR_VALID_COMPONENT"
    districts = str(row["districts"]).split(",") if pd.notna(row["districts"]) and row["districts"] else []
    if districts == ["Adalar"]:
        return "KNOWN_NETWORK_LIMITATION"
    if row["n_anchored_grid_cells"] == 0 or row["calibrated_population"] == 0:
        return "QUESTIONABLE_FRAGMENT"
    if row["calibrated_population"] >= LARGE_LOCAL_POP_THRESHOLD:
        return "LARGE_LOCAL_VALID_COMPONENT"
    return "SMALL_LOCAL_COMPONENT"


def corrected_flag(row, largest_component_id: int) -> str:
    if row["district"] == "Adalar":
        return "KNOWN_NETWORK_LIMITATION_ADALAR"
    if row["walking_snap_quality"] == "QUESTIONABLE":
        return "QUESTIONABLE_ANCHOR"
    cc = row["component_class"]
    if cc == "MAJOR_VALID_COMPONENT":
        # The single largest component is the primary reference network;
        # any OTHER major component (e.g. the Asian side) is fully
        # reliable but genuinely separate from it -- both are "valid",
        # this distinguishes the two rather than collapsing them.
        return "RELIABLE" if row["walking_component_id"] == largest_component_id else "RELIABLE_SEPARATE_COMPONENT"
    if cc in ("LARGE_LOCAL_VALID_COMPONENT", "SMALL_LOCAL_COMPONENT"):
        return "RELIABLE_SEPARATE_COMPONENT"
    if cc == "KNOWN_NETWORK_LIMITATION":
        return "KNOWN_NETWORK_LIMITATION_ADALAR"
    return "SMALL_COMPONENT_CAUTION"


def main() -> None:
    print("=" * 72)
    print("Phase 8.1 step 2: component classification + corrected quality flags")
    print("=" * 72)

    comp_df = pd.read_csv(VAL_DIR / "network_component_audit.csv")
    comp_df["component_class"] = comp_df.apply(classify_component, axis=1)
    print("\n[1/3] Component classification counts:")
    print(comp_df["component_class"].value_counts().to_string())
    comp_df.to_csv(VAL_DIR / "network_component_audit.csv", index=False)  # add component_class column in place

    class_pop = comp_df.groupby("component_class")["calibrated_population"].sum()
    class_cells = comp_df.groupby("component_class")["n_anchored_grid_cells"].sum()
    print("\n  population by component class:")
    print(class_pop.round(1).to_string())
    print("\n  anchored grid cells by component class:")
    print(class_cells.to_string())

    print("\n[2/3] Rebuilding corrected quality flags for every grid cell...")
    membership = pd.read_parquet(VAL_DIR / "_grid_component_membership.parquet")
    original_quality = pd.read_parquet(APP_DIR / "accessibility_quality_flags.parquet")

    merged = original_quality.merge(
        membership[["grid_id", "walking_component_id"]], on="grid_id", how="left"
    ).merge(
        comp_df[["component_id", "component_class", "n_nodes", "n_anchored_grid_cells", "calibrated_population"]]
        .rename(columns={"component_id": "walking_component_id", "n_nodes": "component_n_nodes",
                          "n_anchored_grid_cells": "component_n_anchored_cells",
                          "calibrated_population": "component_population"}),
        on="walking_component_id", how="left",
    )
    largest_component_id = int(comp_df.loc[comp_df["n_nodes"].idxmax(), "component_id"])
    merged["corrected_quality_flag"] = merged.apply(corrected_flag, axis=1, largest_component_id=largest_component_id)

    n_changed = int((merged["interpretation_status"] != merged["corrected_quality_flag"]).sum())
    print(f"  {n_changed} / {len(merged)} cells changed quality interpretation "
          f"({n_changed/len(merged)*100:.2f}%)")

    transition = pd.crosstab(merged["interpretation_status"], merged["corrected_quality_flag"])
    print("\n  transition (original Phase 8 flag -> corrected flag):")
    print(transition.to_string())

    out_cols = ["grid_id", "district", "walking_snap_quality", "walking_has_local_node",
                "walking_component_id", "component_class", "component_n_nodes",
                "component_n_anchored_cells", "component_population",
                "interpretation_status", "corrected_quality_flag"]
    merged = merged.rename(columns={"interpretation_status": "original_phase8_quality_flag"})
    out_cols = [c if c != "interpretation_status" else "original_phase8_quality_flag" for c in out_cols]
    merged[out_cols].to_parquet(VAL_DIR / "corrected_accessibility_quality_flags.parquet")
    print(f"\n[save] {VAL_DIR / 'corrected_accessibility_quality_flags.parquet'}")

    print("\n[3/3] New corrected flag distribution:")
    print(merged["corrected_quality_flag"].value_counts().to_string())

    diag = {
        "n_cells_interpretation_changed": n_changed,
        "pct_cells_interpretation_changed": round(n_changed / len(merged) * 100, 2),
        "original_flag_counts": original_quality["interpretation_status"].value_counts().to_dict(),
        "corrected_flag_counts": merged["corrected_quality_flag"].value_counts().to_dict(),
        "transition_matrix": transition.to_dict(),
        "component_classification_thresholds": {
            "MAJOR_VALID_COMPONENT": f">={MAJOR_NODE_THRESHOLD:,} nodes",
            "LARGE_LOCAL_VALID_COMPONENT": f">=1 anchored cell AND population>={LARGE_LOCAL_POP_THRESHOLD:,}",
            "SMALL_LOCAL_COMPONENT": ">=1 anchored cell AND 0<population<1,000",
            "QUESTIONABLE_FRAGMENT": "0 anchored cells, OR anchored cells with 0 population",
            "KNOWN_NETWORK_LIMITATION": "component's only district is Adalar",
        },
        "key_finding": "Reclassifying the Asian-side mega-component (521,850 nodes, 14 districts, 5.44M "
            "population) from ISOLATED_NETWORK_COMPONENT to RELIABLE_SEPARATE_COMPONENT/RELIABLE is the single "
            "largest correction -- it was never a network-quality problem, only a genuine, expected Bosphorus "
            "separation.",
    }
    (VAL_DIR / "quality_flag_correction_diagnostics.json").write_text(json.dumps(diag, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {VAL_DIR / 'quality_flag_correction_diagnostics.json'}")


if __name__ == "__main__":
    main()
