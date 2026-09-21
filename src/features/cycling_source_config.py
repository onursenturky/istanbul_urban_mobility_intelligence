"""Phase 3E cycling infrastructure source definitions and category rules.

SOURCES INVESTIGATED
---------------------
İBB (authoritative, checked first):
  - "Istanbul Bicycle Paths Data" (istanbul-bisiklet-yollari-verisi): 341
    LineString/MultiLineString features, GeoJSON, EPSG:4326, updated
    2025-06-05, İBB Open Data License. Carries an official PRJ_ASAMA
    (project stage) field distinguishing existing-separated,
    existing-shared, planned, and under-construction facilities, plus a
    YAPIM_YILI (construction year) per feature — a genuine reference year,
    not assumed. SELECTED as the primary/authoritative infrastructure
    source. Known limitation: no field distinguishes a physically-separated
    "track" from a painted-only "lane" within its "Ayrılmış" (separated)
    category — treated as PROTECTED (the category name itself specifies
    separation), but finer subdivision was not attempted since the source
    doesn't support it.
  - "Bicycle and Micromobility Parking Areas" (bisiklet-ve-mikromobilite-park-alanlari):
    384 points, GeoJSON, EPSG:4326, updated 2025-06-05, İBB Open Data
    License. Park_Tipi field distinguishes "Bisiklet Park Alanı" (182,
    bicycle-specific — used for bicycle_parking_count) from "Mikromobilite
    Park Alanı" (202, scooter/e-bike-oriented — reported separately, not
    counted as bicycle_parking per the source's own labeling).
  - "Bisiklet Bakım İstasyonları" (bicycle maintenance/repair stations):
    investigated, updated 2026-04-06 (current), XLSX format. Not used for
    any Phase 3E feature (not requested in scope) but noted as available
    for a future phase.
  - "Bicification Project Data": investigated — an EIT-funded gamified
    personal-trip-tracking pilot (2022), NOT infrastructure. Individual
    GPS trip LineStrings with timestamps. Kept entirely separate under
    data/raw/shared_mobility/ (see module docstring on shared mobility) —
    never merged into this infrastructure feature table.

OpenStreetMap (complementary, checked second):
  - highway=cycleway ways (standalone cycle-path geometry) and
    cycleway=* / cycleway:left=* / cycleway:right=* / cycleway:both=*
    tags on other highway=* ways (a road's own cycling-facility attribute,
    no separate geometry). Verified via a live Overpass query before
    committing to any category (see below) — not assumed complete, and
    NOT treated as equivalent to the İBB inventory: OSM geometries
    overlapping an İBB "Mevcut" (existing) facility are treated as
    duplicate representations and excluded from length totals (İBB takes
    precedence as the authoritative source); non-overlapping OSM
    geometries are kept and tagged source="osm" as a genuine complement.
  - amenity=bicycle_parking: investigated as a completeness cross-check
    against the İBB parking dataset, reported in QA, NOT merged into the
    primary bicycle_parking_count (İBB is authoritative and used alone,
    per the stated source priority).

CATEGORY DEFINITIONS (grounded in what each source can actually support —
no protection level is inferred where the source doesn't state one)
---------------------------------------------------------------------
- protected_separated: İBB PRJ_ASAMA="Mevcut Ayrılmış"; OSM highway=cycleway
  with foot=no; OSM cycleway(:left/right/both)=track.
- dedicated_lane: OSM cycleway(:left/right/both)=lane (a marked, exclusive
  bicycle lane on the carriageway, not physically separated from traffic).
- shared_path: İBB PRJ_ASAMA="Mevcut Paylaşımlı"; OSM highway=cycleway with
  foot=designated or foot=yes (explicitly shared with pedestrians).
- painted_on_road: OSM cycleway(:left/right/both)=shared_lane or
  =opposite_lane (a sharrow/marking only, no dedicated space).
- other_unknown: İBB PRJ_ASAMA="Mevcutla Örtüşen UTK" (existing but
  administratively ambiguous); OSM highway=cycleway with no foot tag
  (cannot determine shared-vs-exclusive without inferring); any other
  cycleway=* value not covered above (e.g. bare "cycleway=right/left"
  used non-standardly as a side indicator rather than a facility type).

EXCLUDED (not "existing" infrastructure, or explicit non-facility values):
  İBB PRJ_ASAMA in {"UTK kararı alınan", "İnşaat Aşamasında",
  "Proje Aşamasında", "Belirsiz"} — planned, under construction, or
  undetermined, not current infrastructure. OSM cycleway=no/crossing —
  no facility present. OSM cycleway(:side)=separate — an explicit OSM
  signal that the real facility is mapped as its own way (i.e. this IS
  the dedup case, handled by excluding these road-attribute values
  outright rather than needing geometry matching for them).
"""

IBB_BIKE_PATHS = {
    "provider": "İBB Açık Veri Portalı",
    "dataset_name": "İstanbul Bisiklet Yolları Verisi (Istanbul Bicycle Paths Data)",
    "dataset_page": "https://data.ibb.gov.tr/dataset/istanbul-bisiklet-yollari-verisi",
    "download_url": "https://data.ibb.gov.tr/dataset/58636f00-06cc-4744-a2d4-2db082da1323/resource/884dc0b8-41b9-4341-b755-f682e57b90c7/download/istanbul_bisiklet_yollari.geojson",
    "geometry_type": "MultiLineString",
    "source_crs": "EPSG:4326 (not declared in file; verified by coordinate range)",
    "license": "İBB Açık Veri Lisansı",
    "last_modified": "2025-06-05",
    "reference_year_field": "YAPIM_YILI (per-feature construction year, where present)",
    "coverage": "341 features covering all of Istanbul (39 districts); 8-34 features per district in our study area's districts",
    "known_limitations": [
        "PRJ_ASAMA distinguishes existing-separated vs existing-shared vs planned/under-construction, "
        "but does not further distinguish physically-barrier-separated tracks from paint-only within "
        "the 'Ayrılmış' category.",
        "Some features have missing/blank YAPIM_YILI.",
    ],
}

IBB_PARKING = {
    "provider": "İBB Açık Veri Portalı",
    "dataset_name": "Bisiklet ve Mikromobilite Park Alanları (Bicycle and Micromobility Parking Areas)",
    "dataset_page": "https://data.ibb.gov.tr/dataset/bisiklet-ve-mikromobilite-park-alanlari",
    "download_url": "https://data.ibb.gov.tr/dataset/e310a322-368d-4d7d-8574-266de136ad09/resource/f6f9a6af-84d6-4718-b509-4a9ccfba038f/download/bisiklet_mikromobilite.geojson",
    "geometry_type": "Point",
    "source_crs": "EPSG:4326",
    "license": "İBB Açık Veri Lisansı",
    "last_modified": "2025-06-05",
    "coverage": "384 points citywide: 182 'Bisiklet Park Alanı' (bicycle-specific, used here) + 202 'Mikromobilite Park Alanı' (scooter/e-bike-oriented, reported separately)",
}

IBB_MAINTENANCE = {
    "provider": "İBB Açık Veri Portalı",
    "dataset_name": "Bisiklet Bakım İstasyonları (Bicycle Maintenance Stations)",
    "dataset_page": "https://data.ibb.gov.tr/dataset/bisiklet-bakim-istasyonlari",
    "last_modified": "2026-04-06",
    "note": "Investigated, current, but not used for any Phase 3E feature (out of requested scope).",
}

# İBB PRJ_ASAMA -> our category, or None to exclude (not current infrastructure)
IBB_STAGE_TO_CATEGORY = {
    "Mevcut Ayrılmış": "protected_separated",
    "Mevcut Paylaşımlı": "shared_path",
    "Mevcutla Örtüşen UTK": "other_unknown",
    "UTK kararı alınan": None,
    "İnşaat Aşamasında": None,
    "Proje Aşamasında": None,
    "Belirsiz": None,
}

OSM_CYCLEWAY_KEYS = ["cycleway", "cycleway:left", "cycleway:right", "cycleway:both"]
OSM_CYCLEWAY_EXCLUDE_VALUES = {"no", "separate", "crossing"}
OSM_CYCLEWAY_VALUE_TO_CATEGORY = {
    "track": "protected_separated",
    "lane": "dedicated_lane",
    "shared_lane": "painted_on_road",
    "opposite_lane": "painted_on_road",
}
# Anything else present (e.g. bare "left"/"right" used non-standardly) falls
# back to "other_unknown" rather than being guessed.

OSM_LICENSE = "ODbL 1.0 (https://www.openstreetmap.org/copyright)"
