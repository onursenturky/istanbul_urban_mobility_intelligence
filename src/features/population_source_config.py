"""Phase 3C population source definition and provenance.

Source investigation, in the project's stated priority order:

1. TÜİK / İBB fine-resolution spatial population data — investigated, NOT
   used. İBB's own "Population Information" (nufus-bilgileri) dataset is
   district-level only (39 districts total for all of Istanbul — no finer
   than what Phase 1 already captured from OSM boundaries, and only 3
   numbers for our whole study area). TÜİK's ADNKS system does publish
   neighborhood (mahalle) level counts, but only through an interactive
   query portal (MEDAS / nip.tuik.gov.tr) with no documented bulk-download
   or API access, and with no accompanying geometry (a separate, less
   certain boundary source and a name-matching join would be needed). This
   fails the reproducibility bar this project has held to since Phase 1
   (no login-gated or non-scriptable sources) — not a resolution problem,
   an access problem.

2. GHSL GHS-POP — investigated, NOT used. Scientifically the strongest
   candidate (EU JRC, well-documented dasymetric methodology), but its only
   distribution mechanism found was a tile-based interactive web map
   requiring manual click-to-select; no documented country/bbox query
   endpoint or published tile-index formula was found. Reverse-engineering
   an undocumented tiling scheme was judged not worth the reproducibility
   risk versus a well-documented, single-URL alternative.

3. WorldPop constrained population count, 2020, UN-adjusted, 100m —
   SELECTED. Single stable, directly downloadable per-country GeoTIFF
   (verified reachable at acquisition time); well-documented Random-Forest
   dasymetric methodology restricted to pixels containing residential
   building footprints (Maxar/Ecopia, Google, Microsoft building datasets)
   plus GHSL/World Settlement Footprint built-up layers, with the country
   total calibrated to the UN World Population Prospects (2019) estimate
   for Turkey.

   The "constrained" variant (vs. the plain "unconstrained" global mosaic)
   was chosen deliberately: constrained places population mass only on
   pixels identified as containing residential buildings, which is far more
   appropriate for intra-city, 500m-grid analysis than the unconstrained
   product's coarser land-cover-based spread across all land.
"""

WORLDPOP = {
    "provider": "WorldPop, University of Southampton (funded by the Bill & Melinda Gates Foundation)",
    "dataset_name": "Constrained Individual Countries 2020, UN-adjusted (100m) — Turkey",
    "dataset_listing_url": "https://hub.worldpop.org/geodata/listing?id=78",
    "download_url": "https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/BSGM/TUR/tur_ppp_2020_UNadj_constrained.tif",
    "license": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
    "citation": (
        "WorldPop (www.worldpop.org - School of Geography and Environmental Science, "
        "University of Southampton; Department of Geography and Geosciences, University "
        "of Louisville; Departement de Geographie, Universite de Namur) and Center for "
        "International Earth Science Information Network (CIESIN), Columbia University "
        "(2018). Global High Resolution Population Denominators Project - Funded by The "
        "Bill and Melinda Gates Foundation (OPP1134076). "
        "https://dx.doi.org/10.5258/SOTON/WP00647"
    ),
    "reference_year": 2020,
    "native_resolution": "3 arc-seconds (~100m at the equator)",
    "native_crs": "EPSG:4326 (WGS84)",
    "methodology": (
        "Random Forest-based dasymetric redistribution, constrained to pixels containing "
        "residential building footprints (Maxar/Ecopia, Google, Microsoft building "
        "datasets) and built settlement (GHSL, World Settlement Footprint); national total "
        "calibrated to the UN World Population Prospects (2019) estimate for Turkey."
    ),
    "represents": "counts (estimated number of people per ~100m grid cell) — not a density surface",
    "known_limitations": [
        "Reference year 2020 — 5-6 years older than most other project datasets (OSM 2026, "
        "GTFS 2023-2026); documented, not silently ignored.",
        "Modeled/estimated at this resolution, not a direct census enumeration — subject to "
        "dasymetric model error, checked against official district totals in QA.",
        "Represents RESIDENTIAL population only — no daytime/employment/tourism signal.",
        "UN-adjustment calibrates the COUNTRY total, not district or neighborhood totals — "
        "local under/over-estimation is possible.",
    ],
}

# External sanity check / calibration reference: official TÜİK ADNKS district
# population totals for 2020 (same year as the WorldPop raster).
#
# AUDIT UPDATE (2026-09-19): originally sourced via secondary aggregators
# (nufusu.com, Wikipedia). Re-verified during the population validation audit
# against İBB's own "Nüfus Bilgileri" open dataset — a directly downloadable,
# no-login XLSX explicitly described as TÜİK-sourced (ADNKS), covering all 39
# Istanbul districts by year/sex/5-year age band since 2007. See
# data/raw/population/ibb_nufus_bilgileri_tuik_sourced.xlsx(.meta.json).
# The 2020 totals below are IDENTICAL to the original secondary-source
# figures — this update strengthens provenance, it does not correct a value.
OFFICIAL_DISTRICT_POPULATION_2020 = {
    "Kadıköy": 481_983,
    "Üsküdar": 520_771,
    "Maltepe": 515_021,
}
OFFICIAL_POPULATION_SOURCE_NOTE = (
    "TÜİK Adrese Dayalı Nüfus Kayıt Sistemi (ADNKS) 2020 district results, via İBB's "
    "'Nüfus Bilgileri' open dataset (https://data.ibb.gov.tr/dataset/nufus-bilgileri), which "
    "states it is built from TÜİK ADNKS data. Directly downloadable without login; summed "
    "across all sex/age columns for the 2020 row of each district."
)

# --- Boundary validation (population audit, 2026-09-19) ---
# No independently-obtainable, scriptably-accessible official district
# boundary polygon was found (İBB: login-gated data-request only; TÜİK: no
# geometry published, only an interactive tabular portal; ulasav.csb.gov.tr:
# API returned 403/404 for the district-boundary resource; Harita Genel
# Müdürlüğü's free boundary product explicitly disclaims official status and
# is tiled by map sheet with no simple bbox query). Full polygon-level IoU
# could not be computed for this reason.
#
# As a partial but still informative check, OSM polygon AREAS (Phase 1/2)
# were compared against area figures published by each district's own
# municipality/kaymakamlık site:
BOUNDARY_AREA_CHECK_KM2 = {
    "Kadıköy": {"osm": 25.117, "cited_official": 25.09, "pct_diff": 0.11},
    "Üsküdar": {"osm": 35.358, "cited_official": 35.70, "pct_diff": -0.96},
    "Maltepe": {"osm": 53.948, "cited_official": 50.00, "pct_diff": 7.90},
}
BOUNDARY_AREA_CHECK_NOTE = (
    "Üsküdar's OSM boundary area is within 1% of its cited official area — a boundary "
    "mismatch large enough to explain a +49% population discrepancy would require a "
    "comparably large area error, which is not present. This rules out gross boundary "
    "mismatch as the explanation for Üsküdar's WorldPop overestimate. Maltepe's OSM area "
    "runs ~8% larger than one cited figure (sources vary 50-53 km²) but Maltepe's "
    "population is UNDERestimated by WorldPop (-18.6%) — the opposite direction a "
    "too-large boundary would push, so boundary size is not the driver there either."
)
