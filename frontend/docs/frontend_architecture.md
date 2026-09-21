# Frontend Architecture

## Stack

Next.js 14 (App Router) + React 18 + TypeScript, Tailwind CSS, MapLibre GL JS 4, Recharts.
No backend, no database — every page is a server component that reads static JSON at
request time from `frontend/public/data/`.

## Directory map

```
frontend/
  app/                     Pages (App Router). One folder per route.
    layout.tsx             Root layout: Outfit font, AppShell wrapper.
    globals.css            O3 design tokens (CSS custom properties) + base styles.
    page.tsx                /            Landing / hero
    overview/page.tsx       /overview    Story sequence, case studies, shareable card
    typology/page.tsx       /typology
    fifteen-minute/page.tsx /fifteen-minute
    cycling-gain/page.tsx   /cycling-gain   (flagship map)
    transit/page.tsx        /transit
    gaps/page.tsx            /gaps
    ebike/page.tsx           /ebike
    methods/page.tsx         /methods
  components/              Reusable UI. See "Component map" below.
  lib/
    data.ts                 Server-only data loaders (fs reads of public/data/*.json)
                             + getClaim(claimId) -- the claim-safety contract.
    theme.ts                 O3 color tokens (TS mirror of globals.css).
    labels.ts                 Enum -> human-readable label maps; confidenceClass() helper.
    mapColors.ts               Per-field color maps + buildMatchExpression() for MapLibre.
    useGridAttributes.ts        Client-side singleton cache for the ~27MB attribute lookup.
  types/data.ts             Shared TypeScript interfaces for every JSON shape.
  content/content_hooks.json Editorial hooks (TR+EN) referencing claims_registry.
  data/prepare_frontend_data.py  Python data-prep pipeline (analysis/ -> public/data/).
  qa/                        data_qa.py + its JSON output, performance_qa.json, visual_qa.md.
  docs/                      This file, data_contract.md, brand_and_content.md.
```

## Component map

- **AppShell** — page chrome: `Navigation` + `<main>` + footer disclaimer.
- **Navigation** — top nav, active-route highlight in `#B2F093`, mobile hamburger menu.
- **O3BrandMark** — small/full brand lockup used in the nav and shareable card.
- **PageMapExplorer** — the shared client-side shell used by every map-driven page
  (Typology, 15-Minute, Cycling Gain, Transit, Gaps, E-bike, Methods). Owns the
  active-layer / selected-district / selected-grid state and composes `MapView` +
  `MapLegend` + `LayerSelector` + `DistrictSelector` + `GridIntelligenceCard`. Reads
  `?grid=` / `?district=` from the URL on first render (Section 31 URL state) and renders
  the Grid Intelligence Card as a desktop side panel or a mobile fixed bottom sheet.
- **MapView** — the MapLibre wrapper. Loads `/data/base/grid_geometry.json` once (cached across
  pages via `lib/mapDataCache.ts`), fetches and merges in the small `/data/layers/<field>.json`
  lookup for whichever field(s) the page colors by, colors the `grid-fill` layer via a `match`
  expression built from the page's `colorMap` prop, handles hover/click/selected feature-state,
  and fits bounds to a selected district. See `docs/map_delivery_decision.md` for why this is
  split instead of one bulk GeoJSON file (Phase 14).
- **MapLegend / LayerSelector / DistrictSelector / ModeToggle / TimeThresholdControl** —
  small controlled UI primitives, all theme-token-driven, no hardcoded hex outside `lib/theme.ts`.
- **GridIntelligenceCard** — reads the selected grid's full attributes from
  `useGridAttributes(gridId)`, which resolves the grid's district (via the small
  grid-district index) and fetches only that one district's detail chunk on demand, and
  renders the Section 12 structure (population, walking/cycling everyday access, accessibility
  change, transit, e-bike context, data confidence).
- **QualityBadge** — renders `confidenceClass()`'s result as a colored pill.
- **KpiCard** — renders a `ClaimRecord` (never a hand-written number) with an expandable
  methodology note.
- **InsightCard** — editorial card, optional O3 highlight-panel variant (`#F1FFE0` bg).
- **MethodologyDrawer** — slide-over panel over `methodology_registry.json` rows.
- **CaseStudyNavigator** — the 9 frozen case studies as clickable cards; navigates to the
  relevant page with `?grid=&district=` set.
- **ChartCard** — Recharts bar chart wrapper themed to the O3 palette.
- **ShareableInsightCard** — fixed-aspect-ratio (1:1 / 4:5 / 16:9) social-style card built
  from a `ClaimRecord`; one working example is used on `/overview`.

## Data flow

```
analysis/framework_synthesis/  (frozen, Phase 12 output)
        │  data/prepare_frontend_data.py  (documented transformations only)
        ▼
frontend/public/data/{base,layers,details}/*.json + top-level registries/*.json
        │  lib/data.ts (server components, per-request fs read -- registries/summaries)
        │  lib/mapDataCache.ts (client, per-field/per-district fetch+cache -- map geometry/color)
        │  lib/useGridAttributes.ts (client, per-district on-demand fetch+cache -- cell detail)
        ▼
Pages / components
```

No analytical value is recomputed in the frontend. Two small *presentation-only* derived
fields were added during data prep (documented in `qa/_data_prep_manifest.json` and
`docs/data_contract.md`): `cross_app_convergence` and `data_confidence` — both are 4-way
categorical overlays of already-frozen categorical fields, not new scores.

## State management

No global state library. Each `PageMapExplorer` instance owns its own React state
(`useState`) for active layer / district / selected grid; the only cross-page shared state
is the `useGridAttributes()` in-memory cache (module-level singleton, populated once on
first Grid Intelligence Card open).

## Known bugs found and fixed during Phase 13 QA

See `qa/visual_qa.md` for the full account of the two real bugs (a data mis-mapping
traced back to Phase 11, and a `h-full`-on-flex percentage-height CSS bug) found via live
browser testing and fixed at their root cause.
