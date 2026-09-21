"""Phase 7 Network Intelligence Foundation: point-to-point routing helpers,
used for sanity testing and as the building block accessibility.py wraps.
"""

from __future__ import annotations

import networkx as nx


def shortest_path_report(G, source_node, target_node, weight_time_attr: str, source_label: str = "", target_label: str = "") -> dict:
    """Returns a full diagnostic report for one origin-destination pair:
    straight-line distance, network distance, ratio, travel time, status.
    Never raises on unreachable pairs -- reports ROUTE_NOT_FOUND instead."""
    try:
        sx, sy = G.nodes[source_node]["x"], G.nodes[source_node]["y"]
        tx, ty = G.nodes[target_node]["x"], G.nodes[target_node]["y"]
    except KeyError:
        return {"status": "NODE_NOT_IN_GRAPH", "source": source_label, "target": target_label}

    straight_line_m = ((sx - tx) ** 2 + (sy - ty) ** 2) ** 0.5

    try:
        length_m = nx.shortest_path_length(G, source_node, target_node, weight="length_m")
        time_s = nx.shortest_path_length(G, source_node, target_node, weight=weight_time_attr)
        path = nx.shortest_path(G, source_node, target_node, weight="length_m")
        status = "OK"
    except nx.NetworkXNoPath:
        length_m, time_s, path, status = None, None, None, "ROUTE_NOT_FOUND"

    report = {
        "status": status, "source": source_label, "target": target_label,
        "source_node": source_node, "target_node": target_node,
        "straight_line_distance_m": round(straight_line_m, 1),
    }
    if status == "OK":
        ratio = length_m / straight_line_m if straight_line_m > 0 else float("inf")
        report.update({
            "network_distance_m": round(length_m, 1), "network_euclidean_ratio": round(ratio, 3),
            "estimated_travel_time_min": round(time_s / 60, 2), "n_path_nodes": len(path),
        })
    return report
