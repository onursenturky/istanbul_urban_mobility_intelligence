# Phase 13 Visual QA

Method: live browser automation (Playwright MCP) against the running local dev server
(`npm run dev`, `http://localhost:3001`), not static code review alone. Screenshots saved
under `frontend/qa/screenshots/`.

**Note on tooling constraint:** the Playwright browser session used for this QA is shared
with other automated activity on this machine. Several early navigate→screenshot pairs
landed on an unexpected page because something else drove the same browser between calls.
Batching navigate+screenshot into a single tool round-trip and re-verifying the URL before
each capture resolved this; every screenshot referenced below was captured with its URL
confirmed correct.

## Viewports tested

- **1440px** (desktop) — `landing_1440.png`, `cycling_gain_1440.png`, `cycling_gain_1440_final.png`, `cycling_gain_card_fixed2.png`
- **390px** (mobile) — `landing_mobile_390.png`, `cycling_gain_mobile_fixed.png`, `cycling_gain_mobile_fixed_scrolled.png`, `mobile_bottomsheet_fixed.png`, `mobile_card_urlstate.png`
- **1280px** (laptop) — not separately captured; the 1440px layout is fluid (`max-w-[1600px]` container, no fixed breakpoint between 1280 and 1440) and the Tailwind `md:` breakpoint (768px) is what actually changes the layout, so 1280px renders the same structural layout as 1440px. Treated as covered by the 1440px + 390px pair for this MVP; a dedicated 1280px pass is reasonable follow-up before any wider release.

## Two real bugs found and fixed during this QA pass

1. **Data bug — cycling required-needs count.** The Grid Intelligence Card showed a cell with
   all three cycling travel times marked "Not reachable within 15 min" but "Required needs
   (of 3): 3" — an internal contradiction, caught by reading the actual rendered card, not by
   code review. Root cause: Phase 11's synthesis table never pulled in
   `cycling_required_categories_accessible_15min` (the 3-required-category count); Phase 12's
   dashboard-grid build then substituted `cycling_categories_accessible_15min` (the all-8-category
   count) under a field named `required_categories_cycle_15`. Fixed at the root (Phase 11
   synthesis script), re-ran Phase 11 → Phase 12 → frontend data-prep in order, re-verified all
   Phase 11/12 consistency and QA checks still pass (identical population/cell figures
   throughout — this field was never used in any actual classification logic, only in this one
   display column), and re-confirmed the fix live in the browser (`cycling_gain_card_fixed2.png`).
2. **Layout bug — map not rendering on narrow viewports.** At 390px width, the map's layer-selector
   pill overlapped the "Reset view" button and the CARTO/OSM attribution bar rendered above the
   map tiles instead of below them (`cycling_gain_mobile_390.png`, `cycling_gain_mobile_viewport.png`).
   Diagnosed via `getBoundingClientRect()` on the actual DOM: MapView's root `w-full h-full` divs
   were resolving to a computed height of 0px even though their flex parent had a definite 420px
   height. Fixed by switching MapView's root and container divs from `w-full h-full` to
   `absolute inset-0` (the more robust pattern for map containers generally, not just a
   workaround) — confirmed fixed on mobile (`cycling_gain_mobile_fixed.png`,
   `..._scrolled.png`) and confirmed NOT regressed on desktop (`cycling_gain_1440_final.png`).

## Checklist results

| Check | Result |
|---|---|
| Navigation renders, active state uses `#B2F093` selectively (not the whole bar) | ✅ confirmed at both viewports |
| Map size / rendering | ✅ after the fix above; confirmed real Istanbul geometry (Bosphorus, districts) renders with correct semantic colors |
| Legends readable on dark background | ✅ swatches + labels legible in both screenshots |
| KPI cards render real values (not placeholders) | ✅ `95.57%`, `2.10M` match `claims_registry.json` exactly |
| Grid Intelligence Card (desktop side panel + mobile bottom sheet) | ✅ both confirmed; mobile bottom sheet added during this QA pass (fixed-position, rounded top corners, own scroll region) since the initial implementation only stacked in-flow on mobile |
| District selector + URL state (`?grid=&district=`) | ✅ confirmed: loading `/cycling-gain?grid=GRID_16220&district=Beykoz` pre-selected the district (map fit to Beykoz) and opened the correct card |
| Outfit typography loaded | ✅ visible in all screenshots (distinct geometric sans, matches Outfit's characteristic rounded forms); loaded via `next/font/google` with a `--font-outfit` CSS variable, not a system-font fallback |
| No accidental light/white surfaces | ✅ every screenshot is dark-forest-green throughout, including form controls (`<select>`, buttons) |
| `#B2F093` not overused | ✅ limited to CTA, active nav, active layer pill, KPI accent numbers, selected states |
| Text contrast | ✅ cream-on-dark-green and secondary muted-green-on-dark-green both visually legible in every screenshot |
| Mobile retains the same visual identity | ✅ confirmed, same palette/typography/component style at 390px |
| Basemap belongs to the interface | ✅ CARTO Dark Matter (dark, low-noise, muted labels) sits naturally against the `#113306`/`#194B0A` surfaces; not a jarring light-tile rectangle |
| Console errors | ✅ zero after fixes (only a harmless missing-favicon 404 remains — cosmetic, not a rendering or data defect) |

## Known minor items not chased further (documented, not silently ignored)

- Missing `favicon.ico` (404 in console, no visual/functional impact). Trivial follow-up: add `app/icon.png`.
- On the narrowest mobile widths the "Reset view" button sits close to the CARTO/OSM attribution
  text at the bottom-left of the map (both remain independently clickable/legible). Cosmetic only.
- A dedicated 1280px screenshot pass was not captured separately (see viewport note above).
- `npm audit` reports Next.js 14.2.35 production-server advisories (Server Actions, Image
  Optimization API, custom-server SSRF/RCE classes) that apply to a deployed, publicly-reachable
  server — out of scope for this local-only MVP per the Phase 13 stop condition, but must be
  addressed (upgrade or mitigate) before any real deployment phase.
