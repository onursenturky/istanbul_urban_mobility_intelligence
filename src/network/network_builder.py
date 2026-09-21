"""Phase 7 Network Intelligence Foundation: builds routable citywide
walking and cycling graphs from the existing local OSM PBF (no new
acquisition -- reuses data/raw/osm/pbf/road_network_extract.osm.pbf,
itself derived from the Phase 7A istanbul.osm.pbf extraction).

IMPORTANT discovered tool limitation (see network_intelligence_manifest.json
for the full write-up): pyrosm.OSM.to_graph() on THIS file silently drops
~40% of nodes -- the ENTIRE Asian side of Istanbul, a clean contiguous
geographic half, not a random scatter -- when called on the pre-filtered
get_network(network_type="walking"/"cycling") output, while the identical
to_graph() call on get_network(network_type="all") for the SAME file
retains 99%+ of nodes (already validated in Phase 7A). Root cause isolated
to pyrosm's Cython-level handling of a FILTERED get_network() result at
this scale, not a genuine data or connectivity gap (confirmed: pyrosm's own
get_network(network_type="walking") DOES return the missing nodes/edges;
they are lost specifically inside to_graph()).

WORKAROUND (not a silent repair -- this is a build-time engineering
decision, and the underlying tag rules are UNCHANGED and still fully
documented in network_rules.py): build ONE reliable "all" graph via
get_network(network_type="all") + to_graph() (the proven-good path), then
derive the walking and cycling graphs by applying the EXACT SAME
pyrosm/OSMnx walking_filter()/cycling_filter() tag-exclusion rules as a
post-hoc edge filter on that graph, instead of asking pyrosm to pre-filter
before graph construction.

Walking graph: UNDIRECTED (see network_rules.py for why).
Cycling graph: DIRECTED, respecting the generic `oneway` tag.

Both graphs are projected to EPSG:32635 (this project's metric CRS) and
carry an explicit `length_m` edge attribute recomputed from the PROJECTED
geometry (not trusted from pyrosm's pre-projection value), plus explicit
`travel_time_walk_s` / `travel_time_cycle_s` attributes computed from
transparent constant baseline speeds -- distance and time are stored as
separate attributes throughout, never conflated.
"""

from __future__ import annotations

import json
import pickle

import networkx as nx
import osmnx as ox
from pyrosm import OSM

from src.network import network_rules
from src.utils import config as cfg

PBF_PATH = cfg.DATA_RAW / "osm" / "pbf" / "road_network_extract.osm.pbf"
NETWORK_DIR = cfg.PROJECT_ROOT / "data" / "processed" / "network"

WALKING_SPEED_KMH = 5.0
CYCLING_SPEED_KMH = 15.0
WALKING_SPEED_MS = WALKING_SPEED_KMH / 3.6
CYCLING_SPEED_MS = CYCLING_SPEED_KMH / 3.6


def load_all_graph_projected():
    """The single reliable base graph (network_type='all'), reused for both
    modes. Cached to disk since it is the expensive step (~4 min)."""
    try:
        return load_graph("all_graph_projected"), {"loaded_from_cache": True}
    except FileNotFoundError:
        osm = OSM(str(PBF_PATH))
        nodes, edges = osm.get_network(network_type="all", nodes=True)
        n_raw_nodes, n_raw_edges = len(nodes), len(edges)
        G = osm.to_graph(nodes, edges, graph_type="networkx")
        G_proj = ox.project_graph(G, to_crs=cfg.METRIC_CRS)
        diag = {
            "n_raw_pyrosm_nodes": n_raw_nodes, "n_raw_pyrosm_edges": n_raw_edges,
            "n_graph_nodes_after_to_graph": G_proj.number_of_nodes(),
            "n_graph_edges_after_to_graph": G_proj.number_of_edges(),
            "node_retention_pct": round(G_proj.number_of_nodes() / n_raw_nodes * 100, 2),
        }
        save_graph(G_proj, "all_graph_projected")
        return G_proj, diag


def _filter_directed_graph(G_all, filter_dict: dict) -> nx.MultiDiGraph:
    G = G_all.copy()
    to_drop = [(u, v, k) for u, v, k, data in G.edges(keys=True, data=True)
               if network_rules.edge_is_excluded(data, filter_dict)]
    G.remove_edges_from(to_drop)
    G.remove_nodes_from(list(nx.isolates(G)))
    return G, len(to_drop)


def _finalize_edges(G, speed_ms: float, speed_attr: str) -> tuple[object, dict]:
    """Recomputes length_m from projected geometry, drops zero-length/
    missing-geometry edges (reporting exactly how many, never silently),
    and adds the travel-time attribute."""
    to_drop = []
    n_no_geom = 0
    n_zero_length = 0
    for u, v, k, data in G.edges(keys=True, data=True):
        geom = data.get("geometry")
        if geom is None or geom.is_empty:
            n_no_geom += 1
            to_drop.append((u, v, k))
            continue
        length_m = float(geom.length)
        if length_m <= 0:
            n_zero_length += 1
            to_drop.append((u, v, k))
            continue
        data["length_m"] = length_m
        data[speed_attr] = length_m / speed_ms
    G.remove_edges_from(to_drop)
    diag = {"n_edges_dropped_no_geometry": n_no_geom, "n_edges_dropped_zero_length": n_zero_length,
            "n_edges_remaining": G.number_of_edges()}
    return G, diag


def build_walking_graph() -> tuple[nx.MultiGraph, dict]:
    G_all, base_diag = load_all_graph_projected()
    G_filtered, n_excluded = _filter_directed_graph(G_all, network_rules.walking_filter())
    G_undirected = ox.convert.to_undirected(G_filtered)
    G_final, finalize_diag = _finalize_edges(G_undirected, WALKING_SPEED_MS, "travel_time_walk_s")
    diag = {
        "network_type": "walking", "directedness": "undirected",
        "base_all_graph_diagnostics": base_diag,
        "n_edges_excluded_by_walking_filter": n_excluded,
        "n_directed_edges_after_filter": G_filtered.number_of_edges(),
        "n_undirected_edges_after_merge": G_undirected.number_of_edges(),
        "speed_kmh": WALKING_SPEED_KMH, **finalize_diag,
    }
    return G_final, diag


def build_cycling_graph() -> tuple[nx.MultiDiGraph, dict]:
    G_all, base_diag = load_all_graph_projected()
    G_filtered, n_excluded = _filter_directed_graph(G_all, network_rules.cycling_filter())
    G_final, finalize_diag = _finalize_edges(G_filtered, CYCLING_SPEED_MS, "travel_time_cycle_s")
    diag = {
        "network_type": "cycling", "directedness": "directed",
        "base_all_graph_diagnostics": base_diag,
        "n_edges_excluded_by_cycling_filter": n_excluded,
        "speed_kmh": CYCLING_SPEED_KMH, **finalize_diag,
    }
    return G_final, diag


def save_graph(G, name: str) -> str:
    """Pickled, not GraphML: preserves shapely geometries and arbitrary
    tag-dict attributes exactly as-is; this is an internal reuse artifact,
    not a GIS-interchange file."""
    NETWORK_DIR.mkdir(parents=True, exist_ok=True)
    out_path = NETWORK_DIR / f"{name}.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)
    return str(out_path)


def load_graph(name: str):
    path = NETWORK_DIR / f"{name}.pkl"
    if not path.exists():
        raise FileNotFoundError(path)
    with open(path, "rb") as f:
        return pickle.load(f)


if __name__ == "__main__":
    print("Building walking graph...")
    G_walk, walk_diag = build_walking_graph()
    print(json.dumps(walk_diag, indent=2, default=str))
    print("Building cycling graph...")
    G_cycle, cycle_diag = build_cycling_graph()
    print(json.dumps(cycle_diag, indent=2, default=str))
