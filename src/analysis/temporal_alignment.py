"""Phase 4 temporal alignment audit: reference date of every predictor
family vs. the only candidate target period found (Bicification, 2022-06 to
2022-12)."""

from __future__ import annotations

import pandas as pd

CANDIDATE_TARGET_PERIOD = "2022-06 to 2022-12 (Bicification pilot — NOT adopted as a target; see feasibility decision)"

TEMPORAL_ALIGNMENT_ROWS = [
    {
        "predictor_family": "OSM (POI, buildings, road network, green space/land use)",
        "reference_date_or_period": "Live database snapshot retrieved 2026-09-18; individual feature edit history is cumulative and undated in our extract",
        "predates_candidate_target": False,
        "postdates_candidate_target": True,
        "notes": "~4 years after the candidate 2022 target period. New buildings/POIs/roads may exist now that didn't in 2022; historically-tagged features that existed in 2022 are also included but not separately distinguishable in this extract.",
    },
    {
        "predictor_family": "GTFS — main feed (metro, tram, rail, ferry)",
        "reference_date_or_period": "Resource last-modified 2021-02 to 2024-03 (frozen; feed explicitly 'will not be updated'); calendar.csv service windows expired by 2024-12-31",
        "predates_candidate_target": True,
        "postdates_candidate_target": True,
        "notes": "Straddles the 2022 target: some components predate it (2021), the Metro İstanbul component (Jan 2023) postdates it. Mixed alignment; station topology for lines open before 2022 is usable, newer stations/lines are not.",
    },
    {
        "predictor_family": "GTFS — İETT feed (bus, metrobüs)",
        "reference_date_or_period": "Resources last-modified 2026-03-17",
        "predates_candidate_target": False,
        "postdates_candidate_target": True,
        "notes": "~4 years after the candidate target. Current bus route/frequency structure cannot be assumed equal to 2022.",
    },
    {
        "predictor_family": "Population (WorldPop constrained, UN-adjusted + ADNKS calibration)",
        "reference_date_or_period": "2020",
        "predates_candidate_target": True,
        "postdates_candidate_target": False,
        "notes": "The ONE predictor family that correctly precedes the candidate 2022 target period — the right causal direction for a predictor, though still a 2-year gap.",
    },
    {
        "predictor_family": "Terrain (Copernicus DEM GLO-30)",
        "reference_date_or_period": "TanDEM-X acquisition 2011-2015",
        "predates_candidate_target": True,
        "postdates_candidate_target": False,
        "notes": "Predates the candidate target and is not time-sensitive at urban timescales — topography does not meaningfully change over a decade absent major earthworks.",
    },
    {
        "predictor_family": "Cycling infrastructure (İBB bike paths + OSM)",
        "reference_date_or_period": "İBB dataset updated 2025-06-05; per-feature construction years span 2015-2024; OSM retrieved 2026-09-18",
        "predates_candidate_target": None,
        "postdates_candidate_target": True,
        "notes": "Mixed at the per-feature level: of the 219 'existing' İBB features used in Phase 3E, 25 (~11%) have a construction year of 2023-2024 — i.e. built AFTER the 2022 candidate target period and would overstate 2022 infrastructure if used naively against it. The dataset does carry a genuine per-feature reference year (YAPIM_YILI), so a 2022-filtered subset COULD in principle be reconstructed if this target were ever pursued.",
    },
    {
        "predictor_family": "Candidate target — Bicification",
        "reference_date_or_period": CANDIDATE_TARGET_PERIOD,
        "predates_candidate_target": None,
        "postdates_candidate_target": None,
        "notes": "Reference row — all comparisons above are against this period.",
    },
]


def build_temporal_alignment_table() -> pd.DataFrame:
    return pd.DataFrame(TEMPORAL_ALIGNMENT_ROWS)
