"""Explicit OSM tag -> feature-category mapping for Phase 3A.

This file defines WHAT counts as each feature category. It contains no
processing logic (that lives in src/features/*_features.py) so category
definitions stay auditable in one place.

POI CATEGORY RULES
-------------------
`POI_CATEGORY_RULES` is an ORDERED list of (category_name, tag_key, allowed
values or None-for-"any value"). Every fetched POI is assigned to the FIRST
rule it matches, so the 12 categories are mutually exclusive by
construction — a single OSM object can never be double-counted across two
categories. Order therefore encodes precedence, e.g. a clinic tagged both
`amenity=clinic` and `healthcare=yes` is classified once, as "healthcare".

A POI that matches none of these 12 rules (e.g. amenity=bench,
shop=vacant) is fetched (because the acquisition query is broad) but is not
counted in any feature — this is intentional: Phase 3A keeps the feature
space to categories with plausible mobility relevance rather than exhaustively
encoding every OSM tag.
"""

POI_CATEGORY_RULES = [
    # (category, osm_key, allowed_values | None = any non-null value)
    ("hospital_count", "amenity", ["hospital"]),
    ("hospital_count", "healthcare", ["hospital"]),
    ("university_count", "amenity", ["university"]),
    ("school_count", "amenity", ["school"]),
    # healthcare_count: outpatient/primary care, distinct from hospital_count above.
    ("healthcare_count", "healthcare", None),
    ("healthcare_count", "amenity", ["clinic", "doctors", "dentist", "pharmacy"]),
    ("cafe_count", "amenity", ["cafe"]),
    # restaurant_count folds in fast_food as the same food-service mobility signal.
    ("restaurant_count", "amenity", ["restaurant", "fast_food"]),
    ("bar_pub_count", "amenity", ["bar", "pub", "biergarten"]),
    ("supermarket_count", "shop", ["supermarket"]),
    # retail_count: any other shop=* value (supermarket already claimed above).
    ("retail_count", "shop", None),
    ("office_count", "office", None),
    ("tourism_count", "tourism", None),
    ("leisure_count", "leisure", None),
]

POI_CATEGORIES = sorted({c for c, _, _ in POI_CATEGORY_RULES})

# Overpass/osmnx tag filter for the single combined POI acquisition query.
# `True` = fetch any object carrying this key, regardless of value; refined
# classification into POI_CATEGORY_RULES happens afterward, locally.
POI_FETCH_TAGS = {
    "amenity": True,
    "shop": True,
    "office": True,
    "tourism": True,
    "leisure": True,
    "healthcare": True,
}

BUILDING_FETCH_TAGS = {"building": True}

# --- Road network classification -----------------------------------------
# OSMnx network_type="all" is used so the network includes footways/cycleways
# needed for walkable/cycle-accessible length, not just motor-vehicle roads.
#
# "Major" and "local" mirror OSM's own road-class hierarchy. Walkable/cycle
# accessibility are defined by EXCLUSION (Turkish traffic law bars
# pedestrians/cyclists from limited-access roads; nothing else is excluded by
# default) rather than by trying to enumerate every walkable highway value.
MAJOR_ROAD_HIGHWAY_CLASSES = {
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link",
}
LOCAL_ROAD_HIGHWAY_CLASSES = {
    "tertiary", "tertiary_link", "residential", "living_street",
    "unclassified", "service", "road",
}
# Pedestrians are legally/physically excluded from limited-access roads.
NOT_WALKABLE_HIGHWAY_CLASSES = {"motorway", "motorway_link", "trunk", "trunk_link"}
# Cyclists are additionally excluded from stairs.
NOT_CYCLE_ACCESSIBLE_HIGHWAY_CLASSES = NOT_WALKABLE_HIGHWAY_CLASSES | {"steps"}

# --- Green space -----------------------------------------------------------
# All qualifying polygons across these three keys are pooled and dissolved
# (unary_union) into one layer before intersecting with grid cells, so an
# area double-mapped under two tagging schemes (e.g. natural=wood inside a
# leisure=nature_reserve) is not counted twice.
# leisure=pitch is deliberately excluded: many pitches are hard-surface or
# artificial turf, not necessarily vegetated ground.
GREEN_LEISURE_VALUES = {"park", "garden", "nature_reserve", "recreation_ground", "golf_course"}
GREEN_LANDUSE_VALUES = {"forest", "grass", "meadow", "recreation_ground", "allotments", "village_green"}
GREEN_NATURAL_VALUES = {"wood", "scrub", "grassland", "heath"}

# --- Land-use composition ---------------------------------------------------
# Each category is dissolved separately before intersecting with grid cells
# (removes duplicate/nested polygons within a category); categories are not
# forced to sum to 100% of land_area_m2 — uncovered area is reported as a
# coverage-quality metric rather than fabricated.
LANDUSE_COMPOSITION_VALUES = {
    "residential_area_ratio": "residential",
    "commercial_area_ratio": "commercial",
    "retail_area_ratio": "retail",
    "industrial_area_ratio": "industrial",
}

LANDUSE_FETCH_TAGS = {
    "leisure": sorted(GREEN_LEISURE_VALUES),
    "landuse": sorted(GREEN_LANDUSE_VALUES | set(LANDUSE_COMPOSITION_VALUES.values())),
    "natural": sorted(GREEN_NATURAL_VALUES),
}
