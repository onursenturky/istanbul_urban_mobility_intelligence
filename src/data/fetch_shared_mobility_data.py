"""Phase 3E shared-mobility investigation — NEVER merged into the predictor table.

Shared-bike/e-bike deployment (supply) and usage/ridership are conceptually
different from cycling infrastructure and risk target leakage if merged into
the predictor table now. This script only documents what was found and
caches one small sample of the most promising usage-adjacent dataset, all
under data/raw/shared_mobility/ — a directory the Phase 3E feature pipeline
never reads from.

Findings (see shared_mobility_investigation.json for the full record):

1. İSBİKE (İSPARK A.Ş., İBB's public bike-share, launched 2017, 300
   stations / 3,000 bikes): its real-time station-status API
   ("İsbike İstasyon Durumları Web Servisi") is CONFIRMED OFFICIALLY CLOSED
   — the dataset's own notes field states "Bu servis geçici olarak
   kullanıma kapatılmıştır" (temporarily closed), metadata last modified
   2026-02-27. No current station list/status is obtainable from this
   source as of the retrieval date.

2. Istanbul is mid-transition to a NEW licensed station-free e-bike model:
   a 2025 Shared Bicycle Regulation created the legal basis; operator
   permits were to be announced 2026-01-26; licensed operators deploy
   within 90 days of approval. As of retrieval, no public station/geofence
   dataset for this new system was found — consistent with a system still
   being stood up.

3. Martı (private operator: e-bikes/e-scooters/e-mopeds, ~30 Turkish
   cities): no public GBFS feed (station_information.json,
   free_bike_status.json, geofencing_zones.json) was found via the GBFS
   systems registry or web search. Not independently obtainable.

4. "Bicification Project Data" (İBB, EIT-funded gamified cycling-trip pilot,
   2022): genuine individual GPS trip LineStrings (start/end lat-lon +
   timestamps, session IDs) — the closest thing found to real cycling
   usage/behavior data. BUT: ~300 trips/month citywide (a tiny,
   self-selected, reward-app-driven sample), 2022 vintage (~4 years stale),
   and it is PERSONAL cycling-app usage, not shared-bike usage specifically
   — no confirmed link to İSBİKE or any shared fleet. One monthly sample
   cached here for reference; NOT proposed as a ridership target without
   much more scrutiny.

No dataset found in this investigation is spatially/temporally resolved and
current enough to serve as a shared-bike deployment or ridership variable
today. This is reported as a finding, not worked around by substituting
something weaker.
"""

from __future__ import annotations

import json

import requests

from src.utils import config as cfg

BICIFICATION_BASE = "https://data.ibb.gov.tr/dataset/215159bf-e4e8-45a1-896c-a08a0cd1c087/resource"
BICIFICATION_MONTHLY_RESOURCES = {
    "06-2022": "601127c7-b21f-484a-98d0-00ada90e4054",
    "07-2022": "aa49b592-b071-4139-9e92-183d3db7376d",
    "08-2022": "292593a1-1c23-491e-bd9b-471cb31afe46",
    "09-2022": "bcbe943a-3e9b-47ff-b7d9-2a64057519fd",
    "10-2022": "65dba620-83d9-4c46-be8f-e0054ad0e542",
    "11-2022": "e1085b20-67cb-4606-9e86-55f91e48b453",
    "12-2022": "7bca88bb-5b21-413a-a330-e8aba32e0826",
}

INVESTIGATION_RECORD = {
    "isbike_public_bikeshare": {
        "provider": "İSPARK A.Ş. / İBB",
        "system": "İSBİKE (station-based, launched 2017: 300 stations, 3,000 bikes)",
        "dataset_checked": "https://data.ibb.gov.tr/dataset/isbike-stations-status-web-service",
        "status": "API confirmed CLOSED — dataset notes state 'Bu servis geçici olarak kullanıma kapatılmıştır' (temporarily closed for use)",
        "metadata_last_modified": "2026-02-27",
        "usable_now": False,
    },
    "new_licensed_ebike_system_2026": {
        "context": "2025 Shared Bicycle Regulation approved; station-free e-bike model; operator permits to be announced 2026-01-26; 90-day deployment window after approval",
        "public_station_or_geofence_dataset_found": False,
        "usable_now": False,
    },
    "marti_private_operator": {
        "company": "Marti Technologies, Inc.",
        "fleet": "e-bikes, e-scooters, e-mopeds; ~30 Turkish cities as of Aug 2026",
        "gbfs_feed_found": False,
        "usable_now": False,
    },
    "bicification_2022_pilot": {
        "provider": "İBB (EIT-funded Bicification project)",
        "dataset_page": "https://data.ibb.gov.tr/dataset/bicification-projesi-verileri",
        "data_shape": "Individual GPS trip LineStrings with start/end coords + timestamps + session id, monthly files, 2022 only",
        "sample_size": "~312 trips for June 2022 (citywide)",
        "limitations": [
            "Personal gamified-app pilot, not confirmed shared-bike usage",
            "~4 years stale relative to the 2026 retrieval date",
            "Small, self-selected sample — not representative",
        ],
        "usable_now": False,
        "recommendation": "Do not use as a ridership target without substantial further vetting.",
    },
    "conclusion": (
        "No shared-bike deployment or ridership dataset found is current and resolved enough to "
        "safely inform a predictor or target variable today. Cycling infrastructure (Phase 3E) "
        "remains a pure explanatory layer; shared-mobility supply/usage stays a separate, "
        "unmerged, and largely unresolved question for a later phase."
    ),
}


def fetch_bicification_full() -> list:
    """Fetches all 7 monthly files (the complete obtainable Bicification
    dataset, not just one sample month) — needed for Phase 4's proper
    inspection of total trips, date range, and spatial coverage."""
    out_dir = cfg.DATA_RAW_SHARED_MOBILITY / "bicification_pilot_2022"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for month, resource_id in BICIFICATION_MONTHLY_RESOURCES.items():
        out_path = out_dir / f"bicification_{month}.geojson"
        if out_path.exists():
            print(f"[cache] Bicification {month} already cached at {out_path}")
            paths.append(out_path)
            continue
        url = f"{BICIFICATION_BASE}/{resource_id}/download/{month}.geojson"
        resp = requests.get(url, timeout=90, headers={"User-Agent": "istanbul-mobility-research/0.1"})
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        print(f"[cache] wrote Bicification {month} ({len(resp.content)/1e3:.0f} KB) -> {out_path}")
        paths.append(out_path)
    return paths


def write_investigation_record():
    cfg.DATA_RAW_SHARED_MOBILITY.mkdir(parents=True, exist_ok=True)
    path = cfg.DATA_RAW_SHARED_MOBILITY / "shared_mobility_investigation.json"
    path.write_text(json.dumps({**INVESTIGATION_RECORD, "retrieval_date": cfg.CYCLING_RETRIEVAL_DATE}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[write] shared-mobility investigation record -> {path}")
    return path


def main() -> None:
    print("=" * 72)
    print("Istanbul Urban Mobility Intelligence — Phase 3E: Shared-mobility investigation")
    print("(NOT part of the predictor table — see module docstring)")
    print("=" * 72)
    fetch_bicification_full()
    write_investigation_record()


if __name__ == "__main__":
    main()
