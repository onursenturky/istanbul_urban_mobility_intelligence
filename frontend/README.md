# Istanbul Urban Mobility Intelligence — Frontend

An O3 Sustainability spatial intelligence product. This is the interactive product layer built
on top of the finished, frozen analytical framework (`analysis/`). **The analytics are done** —
this app only presents them, and never recomputes, rounds, or reclassifies anything.

Brand identity: O3 Sustainability dark palette (`#194B0A` / `#113306` / `#B2F093` / `#6BAF82` /
`#F1FFE0` / `#C5DFC9`), Outfit typeface. See `docs/brand_and_content.md` and
`docs/terminology_guide.md` for the full identity and language rules.

## What this product is

A 9-route Next.js app: a landing page and an overview page (editorial, scrolling), plus 7
map-driven exploration pages — Urban Typology, 15-Minute Istanbul, Cycling Gain, Transit
Connection, Accessibility Gaps, E-bike, and Data & Methods — each answering one plain-language
question about accessibility across Istanbul's 22,322 analysis cells, with an interactive
MapLibre map, a legend, a district selector, and a Grid Intelligence Card for any selected cell.

## Requirements

- Node.js 18+ (developed against Node 25)
- Python 3.11+ with the project's `.venv` (only needed to regenerate `public/data/` — the repo's
  system `python3` does NOT have `pandas` installed, so data-prep must use `.venv`)

## Installation

```bash
cd frontend
npm install
```

`npm install` automatically runs `postinstall` → `sync-maplibre-worker`, which copies two files
MapLibre needs at runtime (`maplibre-gl-worker.mjs`, `maplibre-gl-shared.mjs`) into `public/` —
required for the map to render at all (see Known limitations below). If you ever see the map
stuck on "Loading the Istanbul accessibility map" forever, re-run `npm run sync-maplibre-worker`.

## Data preparation

The app reads static JSON from `public/data/`, generated from the frozen
`analysis/framework_synthesis/` package (Phase 12 output). Regenerate it after any change to the
frozen analysis (or if you're setting this up fresh):

```bash
npm run prepare-data
# or directly:
/path/to/repo/.venv/bin/python data/prepare_frontend_data.py
```

This never modifies anything under `analysis/` — it only reads from it and writes to
`public/data/`. Every transformation is documented in `qa/_data_prep_manifest.json` after each
run. See `docs/data_contract.md` for the full field-by-field contract.

**`public/data/` is committed to the repo, not regenerated at build time** — `npm run build`
does not run `prepare-data` automatically, so the generated files must be present (they are, by
default) for `next build`/`next start` to serve the app correctly.

## Development

```bash
npm run dev
```

## Production build

```bash
npm run build
npm run start          # or: npx next start -p <port>
```

**Do not run `next dev` and `next start` (or two `next build`s) against the same `.next/`
directory at the same time** — both write to it, and a dev-mode build will overwrite a
production build's chunk manifest (or vice versa), producing `ChunkLoadError` / `400` responses
for static chunks in whichever server is still running. If this happens: stop every Next
process, `rm -rf .next`, and rebuild once, cleanly, before restarting.

## Data-delivery architecture (Phase 14)

The 22,322-cell analytical grid is NOT shipped as one bulk file. It is split into three tiers
under `public/data/`, each independently cacheable client-side (`lib/mapDataCache.ts`):

| Tier | Path | What it is | Fetched when |
|---|---|---|---|
| Base geometry | `base/grid_geometry.json` (~5.2MB) | `grid_id` + `district` + geometry only | Once per session, by every exploration page, on map mount |
| Layer lookups | `layers/<field>.json` (12 files, ~7.15MB total) | Flat `{grid_id: value}` per categorical field | Only the 1-3 field(s) the current page colors by |
| District details | `details/<district>.json` (39 files, ~28MB total) | Full attribute record per cell | Only the ONE district containing a selected cell, on demand |

A typical single-layer page's real initial map payload is ~5.5-6MB (base + one layer) — well
under the old ~22.6MB `grid_map.geojson` this replaced. See `docs/map_delivery_decision.md` for
why this approach was chosen over PMTiles/vector tiles, and `qa/phase14_performance_report.json`
for the full before/after measurement.

## Architecture

See `docs/frontend_architecture.md` for the full component/page map. In short:

- **Next.js 15 App Router + TypeScript** — server components fetch JSON from `public/data/`
  at request time (via `lib/data.ts`); client components (`MapView`, `GridIntelligenceCard`,
  `PageMapExplorer`, charts) handle interactivity.
- **MapLibre GL JS 6.x** with the free CARTO Dark Matter basemap (no API key) — see
  `components/MapView.tsx`.
- **Tailwind CSS** with a single O3 design-token system (`app/globals.css` custom properties,
  mirrored in `lib/theme.ts`).
- **Claim safety**: every headline analytical statement resolves through `getClaim(claim_id)`
  in `lib/data.ts`, backed by `public/data/claims_registry.json` — never hand-written inline.

## Data vintages (never conflate these)

- **Population**: a calibrated **2020** population distribution — frozen, never updated to a
  current estimate. The UI describes it as "calibrated 2020 population distribution" at the
  Data & Methods page, the Grid Intelligence Card, and the Overview methodology note; it is
  never presented as current population.
- **Roads / buildings / land use / POIs**: an exact OpenStreetMap snapshot (see
  `docs/data_contract.md` for the exact date).
- **Cycling infrastructure**: an exact İBB (Istanbul Metropolitan Municipality) snapshot.
- **Transit**: GTFS feed coverage, with explicit uncertainty flags where coverage is
  insufficient (never silently treated as "no service").

## Analytical freeze

This app must never change routing results, accessibility results, urban typology, e-bike MCDA,
population allocation, classifications, thresholds, model weights, district statistics, headline
KPI values, claims, or methodology. `qa/data_qa.py` (12 checks, A-L) verifies this after every
data-prep run and must show `ALL_DATA_QA_PASS: true`.

## Known limitations

- No database, external API, or server-side route is used for cell-detail lookup — per-district
  static JSON chunks fetched client-side, by design (see `docs/map_delivery_decision.md`). This
  is intentional for 22,322 cells / 39 districts, not a stopgap.
- No automated visual regression suite; QA is a manual Playwright-driven pass documented under
  `qa/`.
- Transit-specific map layers distinguish General vs. Fixed-Guideway through a single combined
  `transit_gap_type` field; a dedicated fixed-guideway-only boolean layer would need one more
  field joined in from `analysis/applications/first_last_mile_transit/`, noted as a natural next
  increment, not implemented.
- **MapLibre worker bundling**: MapLibre GL JS 6.x loads a separate worker script at a
  runtime-computed URL that Next.js's webpack build cannot resolve on its own. This is fixed via
  `npm run sync-maplibre-worker` (wired into `postinstall`) plus `setWorkerUrl()` in
  `components/MapView.tsx` — **re-run `npm run sync-maplibre-worker` after any future
  `maplibre-gl` version upgrade**, or map rendering will silently break with no thrown error.
  Full root-cause writeup: `qa/map_rendering_environment_note.md`.
- The map camera doesn't always visibly re-frame to a district's bounds when arriving via a
  `?grid=&district=` URL (selection/data is correct regardless — a camera-only nuance, not
  investigated further this phase).

## Deployment

Not yet deployed. See `docs/deployment_options.md` for the evaluated hosting options and
recommendation, and `docs/production_architecture.md` for the full production-readiness
architecture summary. Deployment itself is an explicit next step, not part of this phase.

## Not implemented (out of scope by design)

Backend/database, user accounts, third-party analytics or tracking, automated social posting,
new analytical applications, population updates, DNS/domain configuration.
