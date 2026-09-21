# Istanbul Urban Mobility Intelligence

GeoAI for micromobility demand/potential, fleet deployment, and sustainable
transport planning in Istanbul.

> **Note on this document:** the "Status" section below reflects the very first phases of the
> project (spatial-foundation setup). The analytical framework has since progressed
> substantially further (through frozen city-wide accessibility, cycling, transit, e-bike, and
> typology analysis) and an interactive frontend product now exists on top of it. That
> methodology and status history is intentionally preserved below rather than rewritten. **See
> `frontend/README.md` for the current interactive product** — an O3 Sustainability spatial
> intelligence web app built on the finished, frozen analysis, with its own setup and
> architecture documentation.

Adapted and extended from *Predicting Mobility Demand from Urban Features*
for a Turkish urban context. No observed bike-sharing trip data is assumed
to exist; until such data is obtained and verified, this project targets a
**micromobility potential / infrastructure gap** framing rather than
observed demand. Any suitability/potential score produced here is explicitly
labeled as such and is never presented as observed demand.

## Status

- **Phase 1 — Project structure**: done.
- **Phase 2 — Study area & spatial grid**: done, pending review.
- **Phase 3 — Urban feature engineering**: not started.
- **Phase 4 — Target variable**: not started.
- **Phase 5 — Machine learning**: not started.

## Pilot study area

Kadıköy, Üsküdar, Maltepe (İstanbul, Türkiye). Chosen as a manageable first
slice before a possible city-wide extension.

## Data provenance (Phase 2)

| Item | Value |
|---|---|
| Boundary source | OpenStreetMap contributors — administrative boundary relations, `admin_level=6`, `network=TR34-districts` |
| Fetch method | `osmnx.geocode_to_gdf(by_osmid=True)` → Nominatim `/lookup` |
| OSM relation IDs | Kadıköy `R1276548`, Üsküdar `R1276889`, Maltepe `R1276407` |
| License | ODbL 1.0 (https://www.openstreetmap.org/copyright) |
| Retrieval date | 2026-09-18 |
| Metric CRS (all distance/area/grid calculations) | EPSG:32635 (WGS84 / UTM zone 35N) |
| Storage CRS (`.geojson` outputs) | EPSG:4326, per RFC 7946 convention |
| Grid resolution | 500 m × 500 m |
| Grid retention threshold | keep cell if land-intersection ≥ 10% of nominal cell area (adjustable; `land_area_m2`/`cell_area_m2`/`pct_in_study_area` are retained per cell so this can be re-tested at 25%/50% without re-fetching data) |
| Ambiguous-district rule | flagged when the second-largest overlapping district's area is ≥ 20% of the largest overlapping district's area |

**Why OSM instead of İBB's open data portal:** İBB's portal
(`data.ibb.gov.tr`) does not expose a scriptable, login-free district
(ilçe) boundary download as of the retrieval date above — boundary/location
data there is gated behind an authenticated "data request" flow. OSM's
Turkey admin boundaries carry the official `TR34-districts` network tag and
their computed areas (Kadıköy 25.1 km², Üsküdar 35.4 km², Maltepe 53.9 km²)
match published district figures closely. If a scriptable İBB (or other
official) boundary export becomes available, `src/data/build_study_grid.py`
should be updated to use it, with the change documented here.

Raw fetched boundaries are cached at
`data/raw/boundaries/osm_district_boundaries_raw.geojson` (+ a `.meta.json`
sidecar) and are **never modified** — reruns of the pipeline load this
cache instead of re-fetching. Delete the cache file to force a re-fetch.

## Project structure

```
data/
  raw/            # fetched, never modified after download
    boundaries/
    osm/ transit/ population/ cycling/ dem/   # for Phase 3+
  processed/      # pipeline outputs, safe to regenerate
    features/                                  # for Phase 3+
src/
  data/           # ingestion / spatial-foundation scripts
  features/       # for Phase 3+
  models/         # for Phase 5+
  utils/          # shared config/constants
notebooks/
outputs/
  maps/ figures/ models/
app/               # for the Phase-5+ Streamlit dashboard
```

## Running the Phase 1+2 pipeline

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m src.data.build_study_grid
```

Outputs:
- `data/processed/districts.geojson` — the three district boundaries, preserved individually (EPSG:4326)
- `data/processed/study_area.geojson` — dissolved pilot study area (EPSG:4326)
- `data/processed/mobility_grid_500m.geojson` — filtered, district-assigned 500 m grid (EPSG:4326)
- `data/processed/*_metric.gpkg` — same three layers in EPSG:32635, for Phase 3+ metric feature joins without re-reprojecting
- `data/processed/pipeline_metadata.json` — full run metadata (sources, CRS, thresholds, diagnostics)
- `outputs/maps/study_area_validation.png` — validation map

## Methodological rules (project-wide)

- All distance/area/grid computations happen in EPSG:32635, never in EPSG:4326.
- Raw and processed datasets are kept in separate directories; raw files are immutable once fetched.
- Every feature added in later phases must record source, reference year, original resolution, and any transformation applied.
- Synthetic suitability/potential scores are never labeled as observed demand.
- Spatial cross-validation (not random splits) will be used once modeling begins, to avoid spatial leakage.
