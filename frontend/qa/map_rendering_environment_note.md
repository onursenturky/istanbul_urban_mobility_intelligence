# Map Basemap Rendering — RESOLVED (was: Test-Environment Finding)

**Status: RESOLVED.** This was a real, genuine bug in the production build — not a test-tool
artifact, as this document originally (incorrectly) concluded. It affected every user in every
browser, confirmed by the project owner opening the app in their own real desktop browser and
seeing the same stuck-loading symptom this document had, at the time, attributed to the test
environment. The root cause was found and fixed in the same session. Kept as a full record
(rather than deleted) because the underlying issue — bundler compatibility with MapLibre's
worker-loading mechanism — is a real, non-obvious constraint worth remembering for any future
MapLibre/dependency upgrade.

## Root cause

MapLibre GL JS 6.x (introduced with the Phase 14 dependency upgrade from 4.5.0) parses vector
tiles in a separate Web Worker, whose script it loads from a SEPARATE file,
`maplibre-gl-worker.mjs`, physically shipped alongside the main `maplibre-gl.mjs` in the npm
package. MapLibre computes this worker's URL at runtime as:

```js
new URL('./maplibre-gl-worker.mjs', import.meta.url)
```

This works fine when `maplibre-gl.mjs` is loaded directly as an ES module (its `import.meta.url`
correctly points at its own location, so the relative URL resolves next to it). It breaks once a
bundler (here: Next.js's webpack build) bundles `maplibre-gl.mjs`'s source into an app chunk:
`import.meta.url` inside that bundled code now resolves to the webpack chunk's own URL (e.g.
`/_next/static/chunks/251-xxxx.js`), not the original npm package location. Webpack 5 *can*
auto-detect and correctly bundle `new Worker(new URL(...))` patterns, but only when that
expression is written directly, inline, in a way its static analyzer can see — MapLibre wraps
the URL computation in a small helper function (`Ki()` in the minified bundle) with a
template-literal filename decision (`-dev.mjs` vs regular), which defeats that static analysis.
The result: `maplibre-gl-worker.mjs` was never copied into `.next/static/` at all.

At runtime, this meant `new Worker(<url>, {type: 'module'})` was constructed against a URL that
served nothing. The `Worker` object itself never throws on this — module worker script-load
failures don't reliably surface as a catchable JS-side error in this configuration — so
everything *looked* fine at the API level: the dispatcher created a real `Worker`, an actor was
registered, `postMessage` calls to it "succeeded" (no error), but no script ever executed inside
the worker to answer them. Every tile-load request was dispatched into the void and never
resolved, which is exactly the symptom observed: `map.loaded()` stuck at `false` forever,
`_inViewTiles` correctly showing the expected tiles all stuck at `state: "loading"`, the
dispatcher's actor showing pending `resolveRejects` that never cleared, and no `error` event
ever firing on the map.

## Why this session initially misdiagnosed it as a test-environment artifact

The investigation (across two work sessions) methodically ruled out network, CSP, generic
Worker-thread `fetch()`, and WebAssembly as causes — all correctly, all still true, all
irrelevant to the real cause. It concluded the fault was "isolated to MapLibre's own
worker-message-response cycle" — which was also correct, but was misread as environment-specific
because a hand-rolled `Blob`-URL worker (used to test generic Worker capability) *did* work,
creating a false sense that "Workers work fine here." That test used a `Blob` URL with inlined
code, not a fetched `.mjs` module file — a meaningfully different code path from MapLibre's own
`new Worker(url, {type:'module'})` against a real (broken) URL. The actual missing piece — that
`maplibre-gl-worker.mjs` was never emitted into the Next.js build output at all, and further,
that this same worker file itself imports a SECOND file (`maplibre-gl-shared.mjs`) via a
relative import — was found by directly reading MapLibre's own bundled source
(`node_modules/maplibre-gl/dist/maplibre-gl.mjs`) rather than only observing runtime symptoms,
after the project owner confirmed the bug reproduced in their own real browser and ruled out the
"test-tool-only" theory.

## The fix

1. Copy both files MapLibre needs at runtime — `maplibre-gl-worker.mjs` AND its own dependency
   `maplibre-gl-shared.mjs` — from `node_modules/maplibre-gl/dist/` into `public/`, so they are
   served at a stable, webpack-untouched URL (`/maplibre-gl-worker.mjs`,
   `/maplibre-gl-shared.mjs`).
2. Call MapLibre's own public, documented API for exactly this situation —
   `setWorkerUrl('/maplibre-gl-worker.mjs')` — once, before the first `Map` is constructed
   (`components/MapView.tsx`, module scope, guarded by `typeof window !== "undefined"`).
3. Automated the file copy via `npm run sync-maplibre-worker`, wired into `postinstall`
   (`package.json`), so a fresh `npm install` on any machine — or after any future `maplibre-gl`
   version bump — reproduces the correct files without a manual step. **After upgrading
   `maplibre-gl`, re-run `npm run sync-maplibre-worker` (or reinstall) to pick up the new
   version's worker bundle** — this is not automatic on a version bump alone if `node_modules`
   isn't reinstalled.

## Verification performed after the fix

- `map.loaded()` becomes `true` within ~2-3 seconds of navigation, on every one of the 7
  exploration pages, confirmed via direct evaluation against the actual production build.
- Visual confirmation (screenshots in `qa/screenshots_phase14/`): the basemap, all analytical
  color layers (typology clusters, 15-minute walk/cycle access, cycling gain, transit gaps,
  accessibility gaps, e-bike readiness, data confidence), and legends all render correctly.
- Click-to-select works end-to-end: clicking a map cell resolves the correct `grid_id` and
  `district`, fetches the correct per-district detail chunk, and populates the Grid Intelligence
  Card with correct data (spot-checked: a click resolved `GRID_14426`, Üsküdar, population 3.3K,
  Cluster 4 — matching the frozen source table).
- Layer switching works: toggling between a page's layer options (e.g. 15-Minute's
  Walking/Cycling tabs) correctly re-fetches/merges the new field and recolors the map.
- Full navigation stress test (Overview → 15-Minute → Cycling Gain → Transit → Gaps → E-bike →
  Typology → 15-Minute revisit) re-run with the map actually rendering: 0 console errors, and
  the map canvas reports correct non-zero dimensions with the loading spinner gone immediately
  on every single page load — no click/resize/tab-switch required, confirming the Phase 13.1
  container-sizing fixes hold under real rendering, not just in the absence of a working map.

## One remaining minor, non-blocking observation

When arriving at a page via a `?grid=&district=` URL, the map's `fitToDistrict` effect (meant to
zoom the camera to the selected district's bounds) did not visibly change the camera framing in
one spot-check (Gaps page, `?grid=GRID_15026&district=Kadıköy` — the district selector correctly
showed "Kadıköy" and the Grid Intelligence Card correctly showed the right cell's data, but the
map stayed at the full-city zoom level rather than framing Kadıköy specifically). This is
plausibly a timing race between `querySourceFeatures` (which only returns already-loaded tile
data) and the GeoJSON source's internal tiling completing. It does not affect data correctness —
only an optional camera convenience — and was not investigated further under this phase's time
budget. Worth a look in a future pass; not a blocker for this phase's completion decision.
