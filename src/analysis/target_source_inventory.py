"""Phase 4: dedicated target-data search — full inventory of sources checked.

Every candidate examined for a shared-bike/e-bike demand, origin-destination,
station, or deployment target, whether or not it turned out usable. Compiled
from direct API/portal checks plus a dedicated web-research pass covering
İBB, İSPARK, UYM, and academic/research repositories (Zenodo, Mendeley Data,
Figshare, GitHub, and papers with data-availability statements).
"""

TARGET_SOURCES = [
    {
        "source_name": "İsbike İstasyon Durumları Web Servisi (station status API)",
        "provider": "İSPARK A.Ş. / İBB",
        "geographic_coverage": "Citywide (station-based)",
        "dates_covered": "N/A — real-time only, no historical archive",
        "temporal_resolution": "Real-time (when live)",
        "spatial_resolution": "Station-level (point)",
        "n_observations": 0,
        "transport_mode": "Public bike-share (İSBİKE)",
        "accessible_now": False,
        "license": "İBB Açık Veri Lisansı (moot — service closed)",
        "coords_or_ids_reconstructable": False,
        "notes": "Dataset's own metadata states the service is 'temporarily closed for use' "
                 "(confirmed directly via the İBB CKAN API, metadata last modified 2026-02-27). "
                 "İSBİKE has been effectively non-operational since ~Jan 2024.",
    },
    {
        "source_name": "İBB data request: hourly/daily station pickup counts",
        "provider": "İBB Open Data Portal (public data-request queue)",
        "geographic_coverage": "N/A — request was never fulfilled",
        "dates_covered": "N/A",
        "temporal_resolution": "N/A",
        "spatial_resolution": "N/A",
        "n_observations": 0,
        "transport_mode": "İSBİKE",
        "accessible_now": False,
        "license": None,
        "coords_or_ids_reconstructable": False,
        "notes": "A public data-request ticket asking for exactly this (hourly/daily pickup counts, "
                 "return duration/station) was closed with no dataset delivered.",
    },
    {
        "source_name": "İBB data request: historical daily rental counts (academic request, 2011-2012)",
        "provider": "İBB Open Data Portal (public data-request queue)",
        "geographic_coverage": "N/A — request refused",
        "dates_covered": "Requested: Nov 2011 - Nov 2012",
        "temporal_resolution": "Daily (requested)",
        "spatial_resolution": "Unspecified (requested)",
        "n_observations": 0,
        "transport_mode": "İSBİKE",
        "accessible_now": False,
        "license": None,
        "coords_or_ids_reconstructable": False,
        "notes": "A named academic researcher's request for daily rental counts was closed with "
                 "'Accepted dataset: None' — i.e. explicitly refused. Direct evidence that this "
                 "exact data need has been tried through official channels and failed.",
    },
    {
        "source_name": "Istanbul Bicycle Map / Bicycle Paths Data (station LOCATIONS only)",
        "provider": "İBB Açık Veri Portalı",
        "geographic_coverage": "Citywide",
        "dates_covered": "Snapshot, last updated 2025-06-05",
        "temporal_resolution": "Static snapshot",
        "spatial_resolution": "Point (station) / line (path)",
        "n_observations": None,
        "transport_mode": "İSBİKE (historical station locations), cycling infrastructure",
        "accessible_now": True,
        "license": "İBB Açık Veri Lisansı",
        "coords_or_ids_reconstructable": True,
        "notes": "Already used in Phase 3E for infrastructure (not demand). Gives WHERE stations "
                 "were, never usage/capacity/occupancy — supply-side geometry only, not a behavioral target.",
    },
    {
        "source_name": "Zenodo (search: Istanbul bike-share / shared mobility trips)",
        "provider": "Zenodo (CERN/OpenAIRE)",
        "geographic_coverage": None, "dates_covered": None, "temporal_resolution": None, "spatial_resolution": None,
        "n_observations": 0, "transport_mode": None, "accessible_now": False, "license": None,
        "coords_or_ids_reconstructable": False,
        "notes": "Nothing Istanbul-specific found; only generic global micromobility literature.",
    },
    {
        "source_name": "Mendeley Data — 'Public bike sharing systems database'",
        "provider": "Mendeley Data (compiled by T. Matrai)",
        "geographic_coverage": "Global system-level metadata",
        "dates_covered": "Unclear from listing", "temporal_resolution": "System-level, not trip-level",
        "spatial_resolution": "System/city-level, not station or trip-level",
        "n_observations": None, "transport_mode": "Various bike-share systems",
        "accessible_now": True, "license": "Unclear",
        "coords_or_ids_reconstructable": False,
        "notes": "Global inventory of bike-share SYSTEMS (existence/scale metadata), not trip or "
                 "station-level usage records. Would not support spatial demand modeling even if "
                 "İSBİKE is listed.",
    },
    {
        "source_name": "TUMFTM european-bike-sharing-dataset (GitHub)",
        "provider": "Technical University of Munich (TUMFTM)",
        "geographic_coverage": "267 European bike-share systems",
        "dates_covered": "Unclear (25M trips aggregate)", "temporal_resolution": "Trip-level (for included systems)",
        "spatial_resolution": "Station/trip-level (for included systems)",
        "n_observations": None, "transport_mode": "Bike-share",
        "accessible_now": True, "license": "Open (GitHub)",
        "coords_or_ids_reconstructable": None,
        "notes": "Scoped to 'European' systems; Turkish/Istanbul inclusion could not be confirmed "
                 "(index file fetch failed) and is framed as unlikely given the project's scope.",
    },
    {
        "source_name": "Academic papers on Istanbul e-scooter/micromobility adoption",
        "provider": "Various (e.g. Wiley — Çallı, e-scooter adoption in Turkey)",
        "geographic_coverage": "Turkey (survey-based)", "dates_covered": "2024 publication",
        "temporal_resolution": "Cross-sectional survey", "spatial_resolution": "None (respondent survey, ~118 respondents)",
        "n_observations": 118, "transport_mode": "Shared e-scooter",
        "accessible_now": False, "license": None,
        "coords_or_ids_reconstructable": False,
        "notes": "Structural-equation-model adoption survey, not a released spatial trip dataset. "
                 "No data-availability statement releasing raw records was found (page access-blocked).",
    },
    {
        "source_name": "Martı (private operator) — public trip data / GBFS feed / research collaboration data",
        "provider": "Marti Technologies, Inc.",
        "geographic_coverage": None, "dates_covered": None, "temporal_resolution": None, "spatial_resolution": None,
        "n_observations": 0, "transport_mode": "e-bike / e-scooter / e-moped",
        "accessible_now": False, "license": None,
        "coords_or_ids_reconstructable": False,
        "notes": "No public GBFS feed or open dataset found. Only corporate/press material "
                 "(NYSE listing, city-expansion announcements) — no usage data.",
    },
    {
        "source_name": "Bicification Projesi Verileri (personal cycling GPS trip pilot)",
        "provider": "İBB (EIT-funded pilot)",
        "geographic_coverage": "Citywide Istanbul; 626 of 2,033 usable trips touch the 3-district study area",
        "dates_covered": "2022-06-16 to 2022-12-17",
        "temporal_resolution": "Individual trip timestamps",
        "spatial_resolution": "Individual GPS coordinates (start/end lat-lon per trip)",
        "n_observations": 2033,
        "transport_mode": "PERSONAL bicycle trips (gamified rewards app) — NOT confirmed shared-bike or e-bike",
        "accessible_now": True,
        "license": "İBB Açık Veri Lisansı",
        "coords_or_ids_reconstructable": True,
        "notes": "The only genuine trip-level lead found anywhere in this search. See "
                 "bicification_analysis.py / target_feasibility_report.json for the full inspection: "
                 "self-selected participant pool, no persistent user ID (sessionid is 1:1 with "
                 "trips), severe coordinate corruption requiring a manual fix, only 626 trips "
                 "touch the study area, only ~24% of the 514 grid cells receive any observation. "
                 "Documentation never claims these are shared-bike trips.",
    },
]
