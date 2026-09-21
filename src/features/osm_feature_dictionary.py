"""Human-readable metadata for every column in osm_urban_features.*.

Kept separate from processing code so the meaning of each feature is
auditable without reading the pipeline. Exported as
data/processed/features/osm_feature_dictionary.csv by build_osm_features.py.
"""

from src.utils import config as cfg

_SRC = "OpenStreetMap contributors (ODbL 1.0)"
_DATE = cfg.OSM_RETRIEVAL_DATE

_POI_METHOD = (
    "Representative point per POI (post node/way dedup within "
    f"{cfg.POI_DEDUP_DISTANCE_M} m), spatially joined to one grid cell, counted."
)

FEATURE_DICTIONARY = [
    # --- POI counts ---
    {"feature_name": "cafe_count", "description": "Cafes in the cell", "unit": "count",
     "osm_tags": "amenity=cafe", "processing_method": _POI_METHOD},
    {"feature_name": "restaurant_count", "description": "Restaurants and fast-food outlets in the cell", "unit": "count",
     "osm_tags": "amenity=restaurant, amenity=fast_food", "processing_method": _POI_METHOD},
    {"feature_name": "bar_pub_count", "description": "Bars, pubs and beer gardens in the cell", "unit": "count",
     "osm_tags": "amenity=bar, amenity=pub, amenity=biergarten", "processing_method": _POI_METHOD},
    {"feature_name": "supermarket_count", "description": "Supermarkets in the cell", "unit": "count",
     "osm_tags": "shop=supermarket", "processing_method": _POI_METHOD},
    {"feature_name": "retail_count", "description": "Other shops in the cell (supermarkets excluded, counted separately)", "unit": "count",
     "osm_tags": "shop=* (excluding supermarket)", "processing_method": _POI_METHOD},
    {"feature_name": "school_count", "description": "Schools in the cell", "unit": "count",
     "osm_tags": "amenity=school", "processing_method": _POI_METHOD},
    {"feature_name": "university_count", "description": "Universities in the cell", "unit": "count",
     "osm_tags": "amenity=university", "processing_method": _POI_METHOD},
    {"feature_name": "healthcare_count", "description": "Outpatient/primary healthcare (clinics, doctors, dentists, pharmacies) in the cell, excludes hospitals", "unit": "count",
     "osm_tags": "healthcare=* ; amenity=clinic|doctors|dentist|pharmacy", "processing_method": _POI_METHOD},
    {"feature_name": "hospital_count", "description": "Hospitals in the cell", "unit": "count",
     "osm_tags": "amenity=hospital, healthcare=hospital", "processing_method": _POI_METHOD},
    {"feature_name": "office_count", "description": "Offices in the cell", "unit": "count",
     "osm_tags": "office=*", "processing_method": _POI_METHOD},
    {"feature_name": "tourism_count", "description": "Tourism-related POIs (hotels, attractions, museums, etc.) in the cell", "unit": "count",
     "osm_tags": "tourism=*", "processing_method": _POI_METHOD},
    {"feature_name": "leisure_count", "description": "Leisure POIs in the cell (also contributes to green_area_m2 if vegetated, e.g. leisure=park - these measure different things: presence/count vs. spatial coverage)", "unit": "count",
     "osm_tags": "leisure=*", "processing_method": _POI_METHOD},
    {"feature_name": "total_poi_count", "description": "Sum of the 12 POI category counts above", "unit": "count",
     "osm_tags": "derived", "processing_method": "Sum across the 12 mutually-exclusive POI category columns."},
    {"feature_name": "poi_density_km2", "description": "POIs per km^2 of the cell's actual land area", "unit": "count / km^2",
     "osm_tags": "derived", "processing_method": "total_poi_count / (land_area_m2 / 1e6); uses actual clipped land area, not the nominal 250,000 m^2 cell, so boundary cells are not under/over-stated."},
    {"feature_name": "poi_category_count", "description": "Number of the 12 POI categories present at all in the cell (diversity of presence, not weighted by count)", "unit": "count (0-12)",
     "osm_tags": "derived", "processing_method": "Count of category columns > 0."},
    {"feature_name": "poi_entropy", "description": "Shannon entropy (base 2) of the POI category count distribution - higher means POIs are spread evenly across categories, lower means dominated by one category", "unit": "bits",
     "osm_tags": "derived", "processing_method": "-sum(p_i * log2(p_i)) over the 12 categories, p_i = category share of total_poi_count."},
    # --- Buildings ---
    {"feature_name": "building_count", "description": "Buildings in the cell", "unit": "count",
     "osm_tags": "building=*", "processing_method": "Each building assigned to exactly one cell via its representative point."},
    {"feature_name": "building_footprint_area_m2", "description": "Total building footprint area actually inside the cell", "unit": "m^2",
     "osm_tags": "building=*", "processing_method": "Per-building geometric intersection with the cell, summed - a building straddling two cells contributes only its true in-cell portion to each, never its full area to both."},
    {"feature_name": "building_coverage_ratio", "description": "Share of the cell's land area covered by building footprints", "unit": "ratio (0-1, can exceed 1 if source buildings overlap)",
     "osm_tags": "derived", "processing_method": "building_footprint_area_m2 / land_area_m2."},
    {"feature_name": "mean_building_footprint_m2", "description": "Mean full footprint area of buildings assigned to the cell (unclipped, i.e. each building's total area, not its partial in-cell slice)", "unit": "m^2",
     "osm_tags": "building=*", "processing_method": "Mean of building_area_m2 for buildings assigned to the cell by representative point."},
    # --- Road network ---
    {"feature_name": "road_length_m", "description": "Total physical road/path length inside the cell", "unit": "m",
     "osm_tags": "highway=*", "processing_method": "Undirected network (ox.convert.to_undirected, deduplicating bidirectional edge pairs) clipped per cell, lengths summed."},
    {"feature_name": "road_density_km_per_km2", "description": "Road length per km^2 of land area", "unit": "km / km^2",
     "osm_tags": "derived", "processing_method": "(road_length_m / 1000) / (land_area_m2 / 1e6)."},
    {"feature_name": "intersection_count", "description": "Street intersections in the cell (nodes with street degree >= 3)", "unit": "count",
     "osm_tags": "derived from highway=* network topology", "processing_method": "Undirected-graph node degree >= 3, node point spatially joined to one cell."},
    {"feature_name": "intersection_density_km2", "description": "Intersections per km^2 of land area", "unit": "count / km^2",
     "osm_tags": "derived", "processing_method": "intersection_count / (land_area_m2 / 1e6)."},
    {"feature_name": "major_road_length_m", "description": "Length of motorway/trunk/primary/secondary classes (and their links) in the cell", "unit": "m",
     "osm_tags": "highway in {motorway, motorway_link, trunk, trunk_link, primary, primary_link, secondary, secondary_link}", "processing_method": "Same clipped-length method as road_length_m, filtered to this class set."},
    {"feature_name": "local_road_length_m", "description": "Length of tertiary/residential/service/local-street classes in the cell", "unit": "m",
     "osm_tags": "highway in {tertiary, tertiary_link, residential, living_street, unclassified, service, road}", "processing_method": "Same clipped-length method as road_length_m, filtered to this class set."},
    {"feature_name": "walkable_road_length_m", "description": "Length of network usable by pedestrians (all classes except motorway/trunk, which prohibit pedestrians)", "unit": "m",
     "osm_tags": "highway NOT in {motorway, motorway_link, trunk, trunk_link}", "processing_method": "Same clipped-length method as road_length_m; not mutually exclusive with major/local - a residential street counts toward local_road_length_m AND walkable_road_length_m."},
    {"feature_name": "cycle_accessible_road_length_m", "description": "Length of network usable by cyclists (walkable set minus stairs)", "unit": "m",
     "osm_tags": "highway NOT in {motorway, motorway_link, trunk, trunk_link, steps}", "processing_method": "Same clipped-length method as road_length_m."},
    # --- Green space / land use ---
    {"feature_name": "green_area_m2", "description": "Vegetated/park land area inside the cell (parks, gardens, nature reserves, forest, grass, scrub, etc.)", "unit": "m^2",
     "osm_tags": "leisure in {park,garden,nature_reserve,recreation_ground,golf_course}; landuse in {forest,grass,meadow,recreation_ground,allotments,village_green}; natural in {wood,scrub,grassland,heath}", "processing_method": "All qualifying polygons dissolved (union_all) before intersecting with the cell, so overlapping source polygons are not double-counted."},
    {"feature_name": "green_area_ratio", "description": "Share of the cell's land area that is green space", "unit": "ratio (0-1)",
     "osm_tags": "derived", "processing_method": "green_area_m2 / land_area_m2."},
    {"feature_name": "residential_area_ratio", "description": "Share of land area classified as residential land use", "unit": "ratio (0-1)",
     "osm_tags": "landuse=residential", "processing_method": "Category dissolved (union_all) then intersected with the cell; ratio to land_area_m2."},
    {"feature_name": "commercial_area_ratio", "description": "Share of land area classified as commercial land use", "unit": "ratio (0-1)",
     "osm_tags": "landuse=commercial", "processing_method": "Category dissolved (union_all) then intersected with the cell; ratio to land_area_m2."},
    {"feature_name": "retail_area_ratio", "description": "Share of land area classified as retail land use (area zoning, distinct from the retail_count POI tag)", "unit": "ratio (0-1)",
     "osm_tags": "landuse=retail", "processing_method": "Category dissolved (union_all) then intersected with the cell; ratio to land_area_m2."},
    {"feature_name": "industrial_area_ratio", "description": "Share of land area classified as industrial land use", "unit": "ratio (0-1)",
     "osm_tags": "landuse=industrial", "processing_method": "Category dissolved (union_all) then intersected with the cell; ratio to land_area_m2."},
    {"feature_name": "landuse_data_coverage_pct", "description": "Share of the cell's land area covered by ANY classified land-use polygon (residential+commercial+retail+industrial, deduplicated) - reports OSM land-use tagging completeness rather than assuming full coverage", "unit": "percent (0-100)",
     "osm_tags": "derived", "processing_method": "Union of the four land-use category layers, intersected with the cell, divided by land_area_m2."},
    {"feature_name": "landuse_entropy", "description": f"Shannon entropy (base 2) of the four land-use ratios; only produced when mean landuse_data_coverage_pct across all cells is >= {cfg.LANDUSE_ENTROPY_MIN_MEAN_COVERAGE_PCT:.0f}%, otherwise omitted rather than computed from sparse tagging", "unit": "bits",
     "osm_tags": "derived", "processing_method": "-sum(p_i * log2(p_i)) over the 4 land-use categories, p_i = category share of the classified (non-zero) portion."},
]

FEATURE_DICTIONARY_COLUMNS = [
    "feature_name", "description", "unit", "osm_tags", "processing_method", "source", "retrieval_date",
]


def as_dataframe():
    import pandas as pd

    rows = [dict(row, source=_SRC, retrieval_date=_DATE) for row in FEATURE_DICTIONARY]
    return pd.DataFrame(rows, columns=FEATURE_DICTIONARY_COLUMNS)
