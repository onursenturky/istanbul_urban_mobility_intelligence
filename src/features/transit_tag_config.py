"""Phase 3B transit source definitions and mode-classification rules.

Two official, reproducible GTFS feeds cover all six required modes with no
OSM fallback needed (verified by inspection before writing this file):

- MAIN_GTFS ("Toplu Ulaşım GTFS Verisi", data.ibb.gov.tr) covers Metro
  İstanbul (agency 11), Marmaray/TCDD (agency 4), and ferry operators
  (agencies 6/20/33/48). Metro İstanbul's own agency also carries a few
  route_type=0 (tram) routes, including T3 Kadıköy-Moda, which is inside
  our study area — so tram is covered here too, not via OSM.
  This feed's own page states "Bu veri güncellenmeyecektir" (will not be
  updated); its calendar.csv service date ranges mostly end 2024-12-31
  (some as early as 2019) — i.e. every calendar entry has already expired
  as of the 2026 retrieval date. It is used ONLY for station/stop locations
  and route topology (which lines exist), never for departure frequency.

- IETT_GTFS ("İETT GTFS Verisi", data.ibb.gov.tr) covers İETT's bus network,
  which includes Metrobüs (BRT) — identifiable by "METROBÜS" appearing in
  route_long_name, not a separate feed/agency. Last updated 2026-03-17 (this
  session's retrieval date is 2026-09-18) and its calendar.csv service_id=0
  ("WEEKDAYS") is valid 2026-03-16 through 2026-12-31, i.e. current as of
  retrieval. Used for both infrastructure AND departure-frequency features.

No OSM fallback was required for any of the six modes given this coverage.
"""

MAIN_GTFS = {
    "provider": "İstanbul Büyükşehir Belediyesi (İBB) Açık Veri Portalı",
    "dataset_name": "Toplu Ulaşım GTFS Verisi (Public Transport GTFS Data)",
    "dataset_url": "https://data.ibb.gov.tr/dataset/public-transport-gtfs-data",
    "license": "İBB Açık Veri Lisansı (Istanbul Metropolitan Municipality Open Data License)",
    "modes_covered": ["metro", "tram", "rail", "ferry"],
    "encoding": "cp1254",
    "delimiter": ",",
    "resources": {
        "agency": "121a9892-7945-419a-9b89-49f6083926df/resource/42ae499d-ae9c-4906-ac5c-96e0c155e00b/download/agency.csv",
        "routes": "121a9892-7945-419a-9b89-49f6083926df/resource/36b554c7-cae0-4b7e-978f-fc6a43664e88/download/routes.csv",
        "stops": "121a9892-7945-419a-9b89-49f6083926df/resource/d1f7c258-bbc1-406f-9ab2-7a7c1797c673/download/stops.csv",
        "trips": "121a9892-7945-419a-9b89-49f6083926df/resource/dcee1700-e59f-4a5f-8009-f602045a4507/download/trips.csv",
        "stop_times": "121a9892-7945-419a-9b89-49f6083926df/resource/ac646b83-3b6f-4ca2-afb4-9071ab44d9af/download/stop_times.csv",
        "calendar": "121a9892-7945-419a-9b89-49f6083926df/resource/c84ca913-29ac-4f15-87cd-076aef3dccd6/download/calendar.csv",
    },
    "resource_last_modified": {  # as reported by the CKAN API at retrieval time
        "agency": "2024-03-13", "routes": "2023-03-01", "stops": "2023-03-01",
        "trips": "2024-03-13", "stop_times": "2024-03-13", "calendar": "2024-03-13",
    },
    "reliability_note": (
        "Page states this feed will not be updated; calendar.csv date ranges have all "
        "expired (mostly end 2024-12-31). Used for station locations and route topology "
        "only — NOT for departure frequency."
    ),
}

IETT_GTFS = {
    "provider": "İETT Genel Müdürlüğü, via İBB Açık Veri Portalı",
    "dataset_name": "İETT GTFS Verisi",
    "dataset_url": "https://data.ibb.gov.tr/dataset/iett-gtfs-verisi",
    "license": "İBB Açık Veri Lisansı (Istanbul Metropolitan Municipality Open Data License)",
    "modes_covered": ["bus", "metrobus"],
    "encoding": "utf-8-sig",
    "delimiter": ";",
    "resources": {
        "agency": "8540e256-6df5-4719-85bc-e64e91508ede/resource/df13606d-194b-4587-b868-39ecdc5f8769/download/agency.csv",
        "routes": "8540e256-6df5-4719-85bc-e64e91508ede/resource/46dbe388-c8c2-45c4-ac72-c06953de56a2/download/routes.csv",
        "stops": "8540e256-6df5-4719-85bc-e64e91508ede/resource/2299bc82-983b-4bdf-8520-5cef8c555e29/download/stops.csv",
        "trips": "8540e256-6df5-4719-85bc-e64e91508ede/resource/7ff49bdd-b0d2-4a6e-9392-b598f77f5070/download/trips.csv",
        "stop_times": "8540e256-6df5-4719-85bc-e64e91508ede/resource/23778613-16fe-4d30-b8b8-8ca934ed2978/download/stop_times.csv",
        "calendar": "8540e256-6df5-4719-85bc-e64e91508ede/resource/6c9623b1-3858-4b37-b936-8ffa78de2a69/download/calendar.csv",
    },
    "resource_last_modified": {
        "agency": "2024-03-13", "routes": "2026-03-17", "stops": "2026-03-17",
        "trips": "2026-03-17", "stop_times": "2026-03-17", "calendar": "2026-03-17",
    },
    "reliability_note": (
        "calendar.csv service_id=0 ('WEEKDAYS') valid 2026-03-16 to 2026-12-31 — current "
        "as of retrieval. Used for infrastructure AND departure-frequency (bus/metrobüs only)."
    ),
    "weekday_service_id": "0",
}

BASE_URL = "https://data.ibb.gov.tr/dataset/"

# main GTFS: (agency_id, route_type) -> mode. Agencies/route_types not listed
# here (19=Taksi Dolmuş, 37=Minibus, route_type 6/7=cable car/funicular) are
# out of scope for the six required modes and excluded.
MAIN_MODE_RULES = {
    ("11", "1"): "metro",
    ("11", "0"): "tram",
    ("4", "1"): "rail",     # Marmaray/TCDD; this feed miscodes it as route_type 1
    ("4", "2"): "rail",     # (standard GTFS rail code, kept in case of future correction)
    ("6", "4"): "ferry",
    ("20", "4"): "ferry",
    ("33", "4"): "ferry",
    ("48", "4"): "ferry",
}

# İETT: any route whose route_long_name contains this (case-insensitive)
# substring is Metrobüs (BRT); all other İETT routes are regular bus.
METROBUS_NAME_MARKER = "metrob"

ALL_MODES = ["metro", "tram", "rail", "metrobus", "bus", "ferry"]

# Duplicate-stop detection: two stops of the same mode within this distance
# are treated as the same physical stop mapped twice.
STOP_DEDUP_DISTANCE_M = 20
