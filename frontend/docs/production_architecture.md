# Production Architecture Summary (Phase 14)

A consolidated reference for how this app is built for production, pulling together decisions
documented in more detail elsewhere. This is a summary, not a duplicate — see the linked docs
for full reasoning.

## Rendering model

- Next.js 15 App Router. Two route groups with structurally different shells:
  `(editorial)` (landing, overview — top nav, scrolling page) and `(exploration)` (the 7
  map-driven pages — persistent sidebar, map filling the viewport). See
  `docs/frontend_architecture.md`.
- Editorial pages (`/`, `/overview`) are statically prerendered (`○` in the build output).
  Exploration pages are server-rendered on demand (`ƒ`) because they read `?grid=`/`?district=`
  search params server-side to hydrate initial client state.

## Data delivery

Three-tier split (base geometry / per-field layer lookups / per-district detail chunks) instead
of two bulk files. Full rationale and the PMTiles-vs-GeoJSON decision:
`docs/map_delivery_decision.md`. Field-by-field source mapping: `docs/data_contract.md`.

- **Base geometry** (`public/data/base/grid_geometry.json`, ~5.2MB): every exploration page's
  one map-shape fetch, cached in memory for the session (`lib/mapDataCache.ts`).
- **Layer lookups** (`public/data/layers/<field>.json`, 12 files): fetched and merged
  client-side only for the field(s) a page actually colors by.
- **District details** (`public/data/details/<district>.json`, 39 files): fetched on demand,
  per district, only when a cell in that district is selected (`lib/useGridAttributes.ts`).
- **Registries / summaries** (district summaries, KPI/claims/methodology registries, case
  studies): small, read server-side via `lib/data.ts`, unchanged from Phase 13.

## Caching strategy

- All client-side data fetches (base geometry, layer lookups, district chunks, grid-district
  index) are deduplicated and cached for the lifetime of the page session via module-level
  `Map`/singleton caches in `lib/mapDataCache.ts` — a field or district is fetched at most once
  per session, regardless of how many times a user revisits it.
- Static JSON under `public/data/` is served by Next.js/the host's CDN with standard immutable
  caching for hashed/versioned static assets; regenerating `public/data/` (via
  `npm run prepare-data`) and redeploying is the update path — there is no runtime invalidation
  logic to reason about.
- No client-side storage (no `localStorage`/`sessionStorage`/cookies) is used for analytical
  data — every session starts from a clean fetch, which is appropriate for a read-only
  analytical product with no per-user state to persist.

## Lazy loading

- Non-active map layers are never fetched until selected (see Data delivery above).
- A district's cell details are never fetched until a cell in that district is selected.
- The methodology drawer's full content (`methodology_registry.json`) is small enough to not
  need separate lazy-loading, but is only rendered (not fetched-then-hidden) when opened.
- The navigation shell, sidebar, and map container render immediately on every page — nothing
  about lazy-loading the analytical layers delays the page's basic chrome or the map's own
  container from appearing.

## Error handling

- `app/error.tsx` — generic app-wide error boundary (O3-styled, "Something went wrong," a
  "Try again" reset button and a link home; no raw stack trace shown).
- `app/(exploration)/error.tsx` — a map-specific error boundary scoped to the 7 exploration
  routes ("We couldn't load this map," same reset/home pattern), so a map/data-fetch failure on
  those pages gets map-appropriate copy instead of the generic message.
- `app/not-found.tsx` — branded 404 ("This route is off the map"), replacing Next's default.
- `components/MapView.tsx` also listens for MapLibre's own `error` event and logs it via
  `console.error` (visible in browser devtools / server logs) rather than failing silently,
  without exposing that detail in the UI.
- `GridIntelligenceCard`/`useGridAttributes` degrade gracefully to a "No data available for this
  cell" message rather than throwing if a grid_id can't be resolved to a district or record.

## Security posture

Full detail: `qa/security_dependency_audit.md`. Summary: Next.js 15.5.25, MapLibre 6.10.0,
postcss 8.5.28 (including Next's internally-bundled copy, forced via an `overrides` entry) —
`npm audit` reports **0 known vulnerabilities**. No tracking scripts, no analytics SDKs, no
cookies, no API keys or secrets anywhere in the app (verified by a repo-wide pattern scan — see
Task #113 in `PHASE14_HANDOFF.md`/session notes for the scan methodology).

## Accessibility

Global `:focus-visible` ring (O3 accent color) applied app-wide; every interactive control
audited for this phase carries an accessible name (`aria-label` on icon-only buttons, `<label>`
wrapping the district `<select>`, `role="tablist"`/`role="tab"` with `aria-selected` on the
layer selector, `aria-current="page"` on active nav links, `aria-expanded` on the mobile menu
toggle and info tooltips). Color is never the only signal on analytical layers — every layer has
a text legend mapping each color to a plain-language label.

## MapLibre worker bundling (resolved bug, keep this in mind on future upgrades)

MapLibre GL JS 6.x loads a separate worker script (`maplibre-gl-worker.mjs`, plus its own
dependency `maplibre-gl-shared.mjs`) at a URL it computes via `import.meta.url` at runtime. Under
Next.js's webpack build, that computation resolves to the wrong location and the worker file is
never emitted by the build — silently breaking all map tile loading with no thrown error (a real
bug, confirmed in a real browser, not a test-tool artifact; full root-cause writeup in
`qa/map_rendering_environment_note.md`). Fixed by copying both files into `public/` and calling
MapLibre's own `setWorkerUrl()` API before constructing any `Map` (`components/MapView.tsx`).
**After any future `maplibre-gl` version upgrade, re-run `npm run sync-maplibre-worker`** (also
wired into `postinstall`) to refresh these two files, or map rendering will silently break again
in exactly this way.
