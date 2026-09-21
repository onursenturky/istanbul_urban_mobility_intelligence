# Security & Dependency Audit (Phase 14)

## Summary

**Before**: `npm audit` reported 3 vulnerabilities (1 high, 2 critical).
**After**: `npm audit` reports **0 vulnerabilities**.

## Findings and actions

| Package | Before | After | Reason | Compatibility result |
|---|---|---|---|---|
| `next` | 14.2.35 | **15.5.25** | Two CRITICAL advisories affect this app's actual version: [GHSA-p293-qw3h-jr36](https://github.com/advisories/GHSA-p293-qw3h-jr36) (unauthenticated RCE on Windows-hosted servers) and [GHSA-2xp9-vwfh-vxw4](https://github.com/advisories/GHSA-2xp9-vwfh-vxw4) (unauthenticated RCE in the Image Optimization API via AVIF). Neither advisory lists a 14.x backport — the fix floor is 15.5.24+. Chose the latest 15.x patch (15.5.25) rather than jumping to 16.x, since 15.x already resolves every listed advisory and keeps React on 18.x (avoiding an additional, unrelated React 19 migration in the same phase). | Build succeeds, 0 TypeScript errors, production server verified serving all routes, map verified rendering and coloring correctly (see qa/phase13_1_map_rendering_qa.json re-verification below). One required code change: Next 15 makes `searchParams` (and `params`) a `Promise` in page props — all 7 exploration pages updated to `Promise<{...}>` + `await searchParams`. |
| `maplibre-gl` | 4.5.0 | **6.10.0** | CRITICAL advisory [GHSA-jrc7-96c5-q579](https://github.com/advisories/GHSA-jrc7-96c5-q579) (XSS Sanitizer Bypass in `DOM.sanitize()`), affects `<=6.4.0`. Chose the latest stable (6.10.0). | Required code change: MapLibre 6.x is ESM-only with **named exports only** (no default export) — `import maplibregl, { Map } from "maplibre-gl"` no longer works. Rewrote `components/MapView.tsx` to `import { Map as MLMap, NavigationControl, LngLatBounds, type MapLayerMouseEvent } from "maplibre-gl"`. All other APIs used by this app (`Map` constructor options, `addSource`/`addLayer`/`setPaintProperty`/`setFeatureState`, `fitBounds`, `NavigationControl`, cutoff/event handling) are unchanged between 4.x and 6.x for this app's usage -- verified via a full production-build map interaction test (see below). |
| `postcss` (top-level, dev) | 8.4.40 | **8.5.28** | High-severity advisories (arbitrary file read via `sourceMappingURL`, path traversal). | No code impact -- build tool only. |
| `postcss` (transitive, bundled inside `next`) | 8.4.31 (Next's own internal copy) | **8.5.28** (forced) | Next.js 15.5.25 still bundles its own older internal postcss copy. Added an npm `overrides` field (`"overrides": { "postcss": "8.5.28" }`) to force every instance of postcss in the dependency tree to the patched version -- a standard, non-destructive way to fix a transitive advisory without altering Next's own major version. | `npm audit` confirms 0 vulnerabilities after this override; build output unaffected (postcss is a build-time-only tool here, not part of the runtime bundle). |
| `react` / `react-dom` | 18.3.1 | **18.3.1 (unchanged)** | No advisory required a React upgrade, and staying on 18.x avoided a second, unrelated migration (React 19) inside the same dependency-upgrade change. | N/A |
| `recharts` | 2.12.7 | **2.12.7 (unchanged)** | No security advisory. `npm install` prints a deprecation notice recommending v3, but v3 is a larger API migration (recharts v3 changed several prop APIs) and out of scope for a security-driven update; not currently used on any user-critical path beyond the (currently unused-in-production-pages) `ChartCard` component. Flagged as a non-urgent future upgrade. | N/A |

## Verification performed after upgrading

1. `npm install` — clean install, 0 vulnerabilities reported immediately.
2. `npm run build` — compiled successfully, 0 TypeScript errors, all 9 routes generated.
3. `npx next start -p 3002` — production server started and served all routes with HTTP 200.
4. Live browser check (Playwright) against the **production** build: `canvas.getBoundingClientRect()` confirmed correct non-zero dimensions, `map.getPaintProperty('grid-fill','fill-color')` confirmed a full match expression (not the flat fallback), and the only console entry was the pre-existing cosmetic missing-favicon 404 -- the Phase 13.1 StrictMode-only AbortError was absent, as expected in production.

## Remaining status

**0 known high/critical advisories remain** (`npm audit` output: `found 0 vulnerabilities`) as of this writing. This audit should be re-run periodically after deployment, since new advisories are published continuously; it is not a one-time guarantee.

## Re-confirmation (Phase 14 resume session, after the data-architecture optimization work)

Re-ran `npm audit` after all Phase 14 code changes (data architecture split, favicon/metadata/
error-page additions) — **0 vulnerabilities**, unchanged from the initial upgrade. No new
dependencies were added that carry runtime security surface (`next/og`'s `ImageResponse` is
part of the already-audited `next` package itself, not a separate dependency).

Explicit status for the production-readiness decision:
- **Next.js version**: 15.5.25 (current dependencies: `react`/`react-dom` 18.3.1, `maplibre-gl`
  6.10.0, `recharts` 2.12.7, dev-only `postcss` 8.5.28 + `tailwindcss` 3.4.7 + `typescript`
  5.5.4).
- **Remaining HIGH vulnerabilities**: none.
- **Remaining CRITICAL vulnerabilities**: none.
- **Does any remaining advisory affect the intended production deployment?** No known advisory
  remains at all in this dependency tree as of this audit. This does not block a
  production-ready decision on security grounds.

## Final re-confirmation (after clean install + MapLibre worker-bug fix)

Re-ran `npm audit` after a full clean-environment cycle (`rm -rf .next node_modules/.cache`,
fresh `npm install`, `npm run build`, `npx next start`) that also included the fix for the
MapLibre worker-bundling bug (`components/MapView.tsx`'s `setWorkerUrl()` call plus the new
`sync-maplibre-worker` script, see `qa/map_rendering_environment_note.md`) — **still 0
vulnerabilities**. No new runtime dependency was introduced by that fix (it copies two files
already shipped inside the existing, already-audited `maplibre-gl` package; no new package.json
dependency was added).

- **npm audit**: 0 vulnerabilities
- **Next.js**: 15.5.25
- **maplibre-gl**: 6.10.0
- **postcss**: 8.5.28 (both top-level and Next's internally-bundled copy, via `overrides`)
- **Production build**: succeeds
- **REAL BROWSER VERIFICATION** (map rendering, separate from this security audit but recorded
  here for the combined production-readiness record): **PASSED** — the project owner
  independently confirmed the map renders correctly in their own real desktop browser.
