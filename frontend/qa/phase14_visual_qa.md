# Phase 14 Visual QA

All screenshots below are from the actual **production build** (`npm run build` + `npx next
start`), not `npm run dev`, per Section 42 requirements. Stored under
`frontend/qa/screenshots_phase14/`.

**The map renders correctly in every screenshot below.** An earlier version of this document
(and `qa/map_rendering_environment_note.md`) described a map-rendering blocker that was
initially (incorrectly) attributed to the automated test environment. The project owner checked
in their own real browser, saw the same symptom, and that prompted a real root-cause
investigation: MapLibre 6.x's separate worker script was never being emitted by the Next.js
build (a bundler/`import.meta.url` incompatibility), so tile loading silently never completed.
Fixed via MapLibre's own `setWorkerUrl()` API plus copying the two files it needs into `public/`
(full writeup: `qa/map_rendering_environment_note.md`). All screenshots in this document were
recaptured after the fix.

**REAL BROWSER VERIFICATION: PASSED.** After the fix, the project owner independently opened
`http://localhost:3002/fifteen-minute` in their own real desktop browser (not this project's
automated test tooling) and confirmed the map renders correctly. This closes out the map
rendering question definitively — it is a resolved bug, not a remaining product limitation.

## 1440×900 (primary desktop)

| Page | File | Notes |
|---|---|---|
| Landing | `landing_1440.png` | Full hero, correct "calibrated 2020 population" phrasing, CTAs present |
| Overview | `overview_1440.png` | 3 KPI cards + narrative sections render correctly with real registry data |
| Urban Typology | `typology_1440.png` | Map renders with all 5 typology clusters correctly colored across Istanbul |
| 15-Minute Istanbul | `fifteen_minute_1440.png` | Map renders, green/orange/red walking-access gradient visible |
| Cycling Gain | `cycling_gain_1440.png` | Map renders with cycling-intervention categories colored |
| Transit Connection | `transit_1440.png` | Map renders with transit-gap categories colored |
| Accessibility Gaps | `gaps_1440.png` | Map renders, legend and 9-category gap coloring visible |
| E-bike | `ebike_1440.png` | Map renders with e-bike readiness/opportunity/convergence layer |
| Data & Methods | `methods_1440.png` | Map renders with the data-confidence reliability layer |
| Selected-grid state | `selected_grid_1440.png` | Gaps page, `?grid=GRID_15026&district=Kadıköy` — map renders, Grid Intelligence Card shows correct real data (population 4.6K, Cluster 1, correct walk/cycle minutes); district dropdown correctly shows "Kadıköy" |
| 404 | `not_found_1440.png` | Branded "This route is off the map" page, correct HTTP 404 status |

## 1280×800 (secondary desktop)

| Page | File | Notes |
|---|---|---|
| 15-Minute Istanbul | `fifteen_minute_1280.png` | Map renders correctly, layout holds at this width |
| Cycling Gain | `cycling_gain_1280.png` | Map renders correctly, layout holds at this width |
| Selected-grid state | `selected_grid_1280.png` | Cycling Gain page, `?grid=GRID_17420&district=Pendik` — map renders, card content correct |

## 390px (mobile)

| Page | File | Notes |
|---|---|---|
| Landing | `landing_390.png` | Hamburger menu, stacked layout, readable text, correctly sized touch targets |
| 15-Minute Istanbul | `fifteen_minute_390.png` | Map renders correctly at mobile width, layer pills wrap correctly, district selector fits |
| Selected-grid state | `selected_grid_390.png` | 15-Minute page — mobile bottom sheet correctly appears fixed to the viewport bottom with a close button and full card content, map visible above it |

## Additional assets

| Asset | File | Notes |
|---|---|---|
| Social preview (OG image) | `og_image.png` | 1200×630, generated via `next/og`, O3 dark background, grid-cell motif, cream/lime typography, no unsupported statistics |

## Live interaction verification (beyond static screenshots)

- **Click-to-select**: clicking the rendered map canvas at a real coordinate resolved an actual
  cell (GRID_14426, Üsküdar) and correctly populated the Grid Intelligence Card (population 3.3K,
  Cluster 4) — the full click → feature detection → district-chunk fetch → render chain works.
- **Layer switching**: toggling the 15-Minute page's Walking/Cycling tabs correctly re-colored
  the map and updated the legend while preserving the selected cell's card.

## Data-integrity spot checks visible in these screenshots

- Landing/Overview: "82.49%" / "95.57%" / "2.10M" KPI values and "calibrated 2020 population"
  phrasing match `public/data/headline_kpis.json` / `claims_registry.json` exactly.
- Selected-grid screenshots and the ad-hoc map-click test: GRID_15026 (Kadıköy), GRID_17420
  (Pendik), and GRID_14426 (Üsküdar) all match the frozen `dashboard_grid.parquet` source table
  exactly — see `qa/data_qa.json` and `qa/phase14_production_qa.json`.

## Known minor, non-blocking item

The map camera doesn't always visibly re-frame to a district's bounds when arriving via a
`?grid=&district=` URL (data/selection is correct regardless — only the camera framing is
affected). See `qa/map_rendering_environment_note.md`'s closing note.
