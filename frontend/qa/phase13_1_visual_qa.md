# Phase 13.1 Visual QA

Screenshots in `qa/screenshots_13_1/`, captured live against the running dev server via
Playwright (same method/caveat as Phase 13's original visual QA: this session's Playwright
browser is occasionally shared with other automated activity on this machine; every
screenshot below was re-verified against its expected URL before being trusted, and several
early capture attempts that landed on the wrong page were discarded).

## Screenshots captured

| File | Viewport | Page | Notes |
|---|---|---|---|
| `1440_landing.png` | 1440×900 | Landing | Editorial mode unchanged from Phase 13 |
| `1440_overview.png` | 1440×900 | Overview | Editorial mode unchanged |
| `1440_fifteen_minute.png` | 1440×900 | 15-Minute Istanbul | New sidebar + map-dominant layout |
| `1440_transit.png` | 1440×900 | Transit Connection | |
| `1440_transit_final.png` | 1440×900 | Transit Connection | After adding the panel KPI (C07) |
| `1440_cycling_gain_selected.png` | 1440×900 | Cycling Gain | Selected-grid state, GRID_15322/Beykoz |
| `1280_fifteen_minute.png` | 1280×800 | 15-Minute Istanbul | |
| `1280_cycling_gain.png` | 1280×800 | Cycling Gain | |
| `390_fifteen_minute.png` | 390px | 15-Minute Istanbul | Mobile |
| `390_fifteen_minute_selected.png` | 390px | 15-Minute Istanbul | Mobile bottom sheet, GRID_12588/Sultangazi |
| `1280_ebike_signals_align.png` | 1280×800 | E-bike | "Where Signals Align" layer selected |

## Explicit evaluation: does desktop still look like an enlarged mobile UI?

**No — see `phase13_1_desktop_qa.md` for the full structural comparison.** Desktop now has a
persistent sidebar, a map occupying 70%+ of the content width, overlaid compact controls, and
a permanent side panel; mobile has a compact top bar, full-bleed map, and a bottom sheet that
only appears on selection. These are different compositions, confirmed via the screenshots
above, not the same column stretched wider.

## Checklist (Phase 13.1 additions on top of the original Phase 13 checklist)

| Check | Result |
|---|---|
| Map renders automatically on every navigation, no interaction required | ✅ see `phase13_1_map_rendering_qa.json` -- 11/11 transitions, 0 failures |
| Loading state visible while the ~22MB payload loads | ✅ spinner + "Preparing 22,322 spatial cells…" overlay, no layout shift |
| Sidebar persistent on desktop, active module highlighted in `#B2F093` (selectively) | ✅ `1440_cycling_gain_selected.png` |
| Map dominant on desktop (~70-80% of content width) | ✅ 70.4% at 1440px; 65.9% at 1280px (documented as a minor gap, not silently claimed as met) |
| Compact question-first header, not a mobile-style hero, on map pages | ✅ all 7 pages, ~24px title / ~14px question |
| Controls (layer/district/legend) overlaid on the map, not a separate row | ✅ |
| Side panel uses progressive disclosure (not everything expanded) | ✅ `mobile_bottomsheet_new` equivalent desktop view -- Overview + Everyday Access open by default, Transit/E-bike/Data Quality collapsed |
| Side panel shows page KPIs when nothing selected (not empty) | ✅ 6 of 7 pages; Data & Methods shows question + methodology-drawer link instead |
| "Where Signals Align" replaces "Cross-Application Convergence" as primary UI text | ✅ `ebike_1280_signals_align.png` -- layer pill, legend title, and KPI label all say "Where Signals Align"; the technical term appears only in the info tooltip |
| Mobile bottom sheet still works, shows real data, collapsible sections | ✅ `390_fifteen_minute_selected.png` -- GRID_12588, Sultangazi, correct consistent walking/cycling times |
| Mobile retains full O3 visual identity | ✅ dark palette, Outfit, same component styling as desktop |
| Outfit loaded correctly | ✅ visible in every screenshot |
| No accidental light/white surfaces | ✅ |
| `#B2F093` not overused | ✅ limited to active nav item, active layer pill, accent numbers |
| Analytical semantic colors remain distinguishable | ✅ 4-6 category legends readable in every map screenshot |
| Basemap belongs to the interface | ✅ CARTO Dark Matter, unchanged from Phase 13 |

## Known remaining visual items (documented, not chased further in this pass)

- Map-share-of-width at 1280px (65.9%) is a few points under the 70-80% target band (see
  `phase13_1_desktop_qa.md` for the explanation and a suggested future refinement).
- The cosmetic dev-only AbortError console message (see `phase13_1_map_rendering_qa.json`)
  remains and is expected; it does not affect any visual or functional outcome.
- Screenshots were taken across a few separate Playwright sessions during this QA pass (an
  earlier batch was lost to an accidental local file-cleanup command and re-captured); every
  file listed above was verified for correct URL and content immediately before being saved.
