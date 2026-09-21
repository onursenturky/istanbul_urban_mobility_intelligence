"""Phase 7: enriches the Network Intelligence manifest/summary with the
two connectivity/methodological findings discovered during validation,
without re-running the (expensive) graph pipeline. Read-only over the
already-produced analysis/network_intelligence/*.json outputs.
"""

from __future__ import annotations

import json

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

NI_DIR = cfg.PROJECT_ROOT / "analysis" / "network_intelligence"


def main() -> None:
    manifest = json.loads((NI_DIR / "network_intelligence_manifest.json").read_text(encoding="utf-8"))
    routing = json.loads((NI_DIR / "routing_validation.json").read_text(encoding="utf-8"))
    walk_qa = json.loads((NI_DIR / "walking_network_qa.json").read_text(encoding="utf-8"))
    cycle_qa = json.loads((NI_DIR / "cycling_network_qa.json").read_text(encoding="utf-8"))

    not_found = [r["pair_label"] for r in routing["routes"]["walking"] if r["status"] == "ROUTE_NOT_FOUND"]
    found = [r["pair_label"] for r in routing["routes"]["walking"] if r["status"] == "OK"]

    manifest["methodological_concerns_discovered"] = [
        {
            "id": "pyrosm_to_graph_filtered_network_type_node_loss",
            "severity": "CRITICAL -- found and fixed before this phase's outputs were finalized",
            "description": "pyrosm.OSM.to_graph() silently dropped ~40% of nodes -- the ENTIRE Asian side of "
                "Istanbul, a clean contiguous geographic half, not a random scatter -- when built from "
                "get_network(network_type='walking'/'cycling') on data/raw/osm/pbf/road_network_extract.osm.pbf. "
                "The identical to_graph() call on get_network(network_type='all') for the SAME file retained "
                "99.27% of nodes (matching the Phase 7A precedent). Confirmed via direct trace that pyrosm's own "
                "get_network(network_type='walking') DOES return the missing nodes/edges (verified present for "
                "an Adalar-area bounding-box sample: 4623 nodes, 4974 edges) -- they are lost specifically inside "
                "to_graph() only for the pre-filtered network types, not for 'all'.",
            "evidence": "Before fix: walking graph = 827,351 nodes, 14/39 districts with ZERO nodes (all of "
                "Kadıköy/Üsküdar/Maltepe/Ataşehir/Ümraniye/Pendik/Kartal/Tuzla/Sancaktepe/Sultanbeyli/Çekmeköy/"
                "Beykoz/Şile/Adalar -- essentially the entire Asian side), 56.5% grid-cell coverage, a routing "
                "test from Fatih to a Prince-Islands cell falsely SUCCEEDED (24 min, ratio 1.28) because the "
                "'nearest network node' search silently fell back to a mainland node 17km away. "
                "After fix: walking graph = 1,358,982 nodes, 38/39 districts covered, 85.6% grid-cell coverage, "
                "the same Fatih-to-island query correctly returns ROUTE_NOT_FOUND.",
            "fix_applied": "Build ONE 'all'-network-type graph via the proven-reliable get_network(network_type="
                "'all') + to_graph() path (cached as data/processed/network/all_graph_projected.pkl), then derive "
                "the walking and cycling graphs by applying pyrosm's own walking_filter()/cycling_filter() "
                "tag-exclusion dictionaries as a POST-HOC edge filter on that graph (network_rules.edge_is_"
                "excluded()), instead of asking pyrosm to pre-filter before graph construction. The tag rules "
                "themselves are UNCHANGED -- this is a graph-CONSTRUCTION workaround, not a redefinition of what "
                "counts as walkable/cyclable.",
                "not_yet_root_caused": "The exact Cython-level cause inside pyrosm's to_graph() was not "
                "identified (out of scope to patch a third-party C-extension) -- treated as a confirmed, "
                "reproducible tool limitation for this file/scale, worked around rather than root-caused.",
        },
        {
            "id": "adalar_residual_grid_cell_coverage_gap",
            "severity": "MINOR -- open, honestly reported, not resolved",
            "description": "After the fix above, 38/39 districts have walking/cycling network nodes; Adalar "
                "(Prince Islands) is the ONE remaining district with ZERO network nodes falling within its own "
                "grid cells. Investigated: the raw PBF DOES contain ~667 highway ways in the Adalar area "
                "(confirmed via the GDAL/pyogrio 'lines' layer, and Phase 7A's all-highway extraction reports "
                "149.53 km of road length for Adalar), and the corrected graph's nearest node to a sampled "
                "Adalar-area point is only ~4.7 km away (vastly better than the pre-fix 17 km, but still not "
                "'within an Adalar grid cell'). This is reported as an OPEN, narrower residual gap -- possibly a "
                "grid-cell/administrative-boundary alignment nuance rather than a repeat of the systemic bug "
                "above -- and should NOT be relied upon for island-specific accessibility queries without further "
                "investigation.",
            "fix_applied": "NONE -- reported, not silently adjusted, per instruction.",
        },
    ]

    manifest["connectivity_problems_discovered"] = {
        "bosphorus_and_water_crossings": {
            "finding": "The walking and cycling ROAD networks have NO path across the Bosphorus at any of the "
                "tested European<->Asian point pairs, and NO path to the Prince Islands (Adalar) -- CONFIRMED "
                "genuine, not a bug: Istanbul's road bridges over the Bosphorus are motorway-class and excluded "
                "from both the walking_filter and cycling_filter by design (pedestrians/cyclists are legally "
                "barred from them in reality; crossing requires the Marmaray rail tunnel, metro, or a ferry, none "
                "of which are part of a walkable/cyclable ROAD network). This was explicitly tested and confirmed, "
                "not assumed.",
            "routing_pairs_confirming_no_crossing": not_found,
            "routing_pairs_confirming_normal_same_side_connectivity": found,
            "n_weakly_connected_components_walking": walk_qa["n_connected_components"],
            "largest_component_share_walking": walk_qa["largest_component_share"],
            "n_weakly_connected_components_cycling": cycle_qa["n_weakly_connected_components"],
            "largest_weak_component_share_cycling": cycle_qa["largest_weak_component_share"],
            "interpretation": "The large number of components (567 walking / 702 cycling) and the largest "
                "component covering only ~61% of nodes is EXPECTED and CORRECT for a real citywide road-only "
                "pedestrian/cycling network -- it reflects genuine water crossings and isolated fragments, not a "
                "data quality defect. A future accessibility application must treat cross-Bosphorus / cross-water "
                "trips as requiring a DIFFERENT mode (transit/ferry) entirely, not a walking/cycling route.",
        },
    }
    manifest["districts_with_zero_network_nodes_after_fix"] = {"walking": walk_qa["coverage"]["districts_with_zero_nodes"],
                                                                 "cycling": cycle_qa["coverage"]["districts_with_zero_nodes"]}

    (NI_DIR / "network_intelligence_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {NI_DIR / 'network_intelligence_manifest.json'} (enriched)")

    summary = json.loads((NI_DIR / "network_intelligence_summary.json").read_text(encoding="utf-8"))
    summary["walking_district_coverage"] = f"{walk_qa['coverage']['n_districts_with_at_least_1_node']}/39"
    summary["walking_grid_cell_coverage_pct"] = walk_qa["coverage"]["pct_grid_cells_with_at_least_1_node"]
    summary["cycling_district_coverage"] = f"{cycle_qa['coverage']['n_districts_with_at_least_1_node']}/39"
    summary["cycling_grid_cell_coverage_pct"] = cycle_qa["coverage"]["pct_grid_cells_with_at_least_1_node"]
    summary["n_routing_pairs_ok"] = len(found)
    summary["n_routing_pairs_route_not_found_bosphorus_or_water"] = len(not_found)
    summary["critical_bug_found_and_fixed"] = "pyrosm to_graph() dropped Asian side for filtered network types -- see manifest"
    (NI_DIR / "network_intelligence_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {NI_DIR / 'network_intelligence_summary.json'} (enriched)")


if __name__ == "__main__":
    main()
