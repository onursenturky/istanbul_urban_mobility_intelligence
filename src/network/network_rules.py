"""Phase 7 Network Intelligence Foundation: transparent, documented OSM tag
inclusion/exclusion rules for the WALKING and CYCLING routable networks.

Reuses pyrosm's predefined network filters (pyrosm.config.osm_filters),
which themselves reproduce OSMnx's own "walk" and "bike" network-type
filters exactly (see that module's docstring) -- a well-established,
widely-used tag ruleset, not a bespoke reinterpretation. This module's job
is to make those rules EXPLICIT and machine-exportable (as JSON) for this
project's documentation requirements, and to document the two additional,
NOT-yet-applied refinements as known limitations rather than silently
pretending they are handled:

  1. oneway:bicycle contraflow exceptions exist in the source tags (verified
     present on the Istanbul road extract) but are NOT applied to override
     edge directionality in the baseline cycling graph -- the cycling graph
     respects the generic `oneway` tag only, the same default OSMnx uses.
  2. The walking graph is built UNDIRECTED: pedestrians are not bound by
     vehicle oneway restrictions, and OSM's own oneway:foot tagging is too
     sparse citywide to support a reliable directed pedestrian graph.
"""

from __future__ import annotations

from pyrosm.config.osm_filters import cycling_filter, walking_filter

WALKING_NETWORK_TYPE = "walking"
CYCLING_NETWORK_TYPE = "cycling"


def _filter_to_json(filter_dict: dict) -> dict:
    return {k: list(v) for k, v in filter_dict.items()}


def walking_rules() -> dict:
    f = walking_filter()
    return {
        "network_type": WALKING_NETWORK_TYPE,
        "source": "pyrosm.config.osm_filters.walking_filter() -- reproduces OSMnx's 'walk' network-type filter",
        "semantics": "EXCLUDE dict: a way is DROPPED if it carries any of the listed values for that key. "
                     "Everything else is included by default.",
        "exclude": _filter_to_json(f),
        "directedness": "UNDIRECTED -- pedestrians are not bound by vehicle-oneway restrictions; oneway:foot "
                        "tagging is too sparse citywide to support a reliable directed pedestrian graph "
                        "(documented limitation, not silently assumed to be handled).",
        "notes": [
            "highway values always excluded regardless of mode: abandoned/construction/no/planned/platform/"
            "proposed/raceway/razed/rest_area/services (not a physical or current part of the street network).",
            "Additionally excludes motorway/motorway_link/bus_guideway/cycleway (motor-only or cycle-only ways).",
            "access=private and service=private ways excluded; foot=no ways excluded explicitly.",
            "Ways whose sidewalk is separately mapped (sidewalk[:both/:left/:right]=separate) are excluded so "
            "the separately-digitized sidewalk way is not double-counted.",
            "Service roads (parking-lot lanes, alleys) ARE included -- walkable in practice even if unpleasant.",
        ],
    }


def cycling_rules() -> dict:
    f = cycling_filter()
    return {
        "network_type": CYCLING_NETWORK_TYPE,
        "source": "pyrosm.config.osm_filters.cycling_filter() -- reproduces OSMnx's 'bike' network-type filter",
        "semantics": "EXCLUDE dict: a way is DROPPED if it carries any of the listed values for that key. "
                     "Everything else is included by default.",
        "exclude": _filter_to_json(f),
        "directedness": "DIRECTED -- respects the generic `oneway` tag (standard default). "
                        "oneway:bicycle contraflow exceptions ARE present in the source data (verified) but are "
                        "NOT yet applied to override directionality in this baseline -- a documented limitation, "
                        "not a silent gap.",
        "notes": [
            "highway values always excluded regardless of mode: abandoned/construction/no/planned/platform/"
            "proposed/raceway/razed/rest_area/services.",
            "Additionally excludes motorway/motorway_link/bus_guideway/corridor/elevator/escalator/footway/steps "
            "(motor-only or foot-only ways).",
            "access=private and service=private ways excluded; bicycle=no ways excluded explicitly.",
            "Unlike walking, sidewalk-mapped-separately is not a cycling-relevant exclusion (cycleways are "
            "handled by the highway=cycleway inclusion, not a sidewalk tag).",
        ],
    }


def export_rules_json() -> dict:
    return {"walking": walking_rules(), "cycling": cycling_rules()}


def edge_is_excluded(edge_data: dict, filter_dict: dict) -> bool:
    """Applies a pyrosm exclude-filter dict (see walking_filter()/
    cycling_filter()) to one edge's attributes, checking both flat columns
    and the raw `tags` dict (pyrosm exposes some keys, e.g. sidewalk:both,
    only inside `tags`, not as their own column)."""
    tags = edge_data.get("tags") or {}
    if isinstance(tags, str):
        try:
            import json as _json
            tags = _json.loads(tags)
        except Exception:
            tags = {}
    for key, excluded_values in filter_dict.items():
        val = edge_data.get(key)
        if val is None or (isinstance(val, float) and val != val):  # NaN check without pandas dependency
            val = tags.get(key)
        if val is None:
            continue
        if val in excluded_values:
            return True
    return False
