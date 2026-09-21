# Phase 13.1 Desktop QA

Assessed at 1440×900 (primary target) and 1280×800 (secondary). Method: live Playwright
screenshots against the running dev server; see `qa/screenshots_13_1/`.

## The explicit test: "Does desktop still look like an enlarged mobile UI?"

**No.** Before this pass, every analytical page was a single scrolling column: a large hero
heading, two big KPI cards stacked full-width, then a modestly-sized map, then more stacked
cards below it -- structurally identical at 1440px and 390px, just wider. That is exactly the
"mobile UI stretched to a large screen" failure mode described in the correction brief.

After this pass, desktop and mobile are **structurally different compositions**, not the same
layout at different widths:

| | Before (Phase 13) | After (Phase 13.1) |
|---|---|---|
| Navigation | Top bar, full-width | Persistent 224px left sidebar (desktop) / compact top bar (mobile) |
| Page header | Large hero heading + paragraph, ~15-20% of viewport height | Slim single-line title + question, ~64px total |
| Map | ~50-60% of viewport width, competing with stacked cards above/below | ~74-80% of viewport width, fills essentially the entire remaining height |
| KPIs / cell details | Full-width cards stacked in page flow (same on mobile and desktop) | Persistent 360px right-hand panel on desktop (map stays visible beside it); becomes a mobile-only fixed bottom sheet below 768px |
| Controls (layer/district/legend) | A separate row above the map, ~60-80px of vertical space | Overlaid directly on the map (top-left, top-right, bottom-left) -- zero extra vertical space taken from the map |

## Map dominance (Section 14 target: ~70-80% of horizontal space)

Measured directly from the 1440×900 screenshots (`qa/screenshots_13_1/1440_cycling_gain_selected.png`
and others): sidebar 224px + map ~856px + panel 360px = 1440px total.
**Map share of the content area (excluding sidebar): 856 / (856+360) = 70.4%.**
Without a cell selected (panel still showing page KPIs, not collapsed): same 70.4% split,
confirmed in `1440_cycling_gain.png`.

At 1280×800 (`qa/screenshots_13_1/1280_fifteen_minute.png`, `1280_cycling_gain.png`): sidebar
224px + map ~696px + panel 360px = 1280px. **Map share: 696/(696+360) = 65.9%** -- slightly
below the 70-80% target at this narrower width because the panel and sidebar widths are fixed
in pixels rather than proportional; still map-dominant and clearly not mobile-stretched, but
noted as a known limitation (see below) rather than silently claimed as fully within spec.

## Information hierarchy (Section 22 five-question test)

Walked through on the Cycling Gain page as the flagship example:

1. **What question am I looking at?** — "Cycling Gain / What changes when we add cycling?" in
   the slim header, visible without scrolling. Pass.
2. **What does the map color mean?** — Legend card, bottom-left, always visible, plain-language
   labels ("Cycling closes the gap," not the raw enum). Pass.
3. **What can I click?** — Grid cells (cursor changes to pointer on hover, confirmed in
   `components/MapView.tsx`); layer pill buttons; district dropdown. Pass.
4. **What does this result mean?** — Clicking a cell opens the intelligence panel with the
   plain-language "Cycling closes the gap" / "Multiple-need gap (all three)" summary before any
   raw numbers. Pass (verified live: GRID_15322, Beykoz -- see `1440_cycling_gain_selected.png`).
5. **How reliable is it?** — "Data Quality" section in the panel (collapsed by default,
   one click away) plus the dedicated Data & Methods reliability map. Pass.

## Typography scale (Section 20)

- Map-page title: 20-24px (`text-xl md:text-2xl`) -- within the ~24-32px target range at the
  md breakpoint, slightly under at pure mobile width (acceptable, mobile compresses further).
- Question/description: 12-14px (`text-xs md:text-sm`) -- within the 14-18px target at md,
  slightly under at the smallest widths.
- Control labels (layer pills, district selector): 12px (`text-xs`) -- within the 12-14px target.
- Landing/Overview retain the large editorial display scale (`text-5xl`-`text-7xl` on the hero) --
  unchanged, confirmed still distinct from the compact map-page scale.

## Known limitations (not silently hidden)

- At 1280×800 the map's share of content width (65.9%) is a few points under the 70-80% target
  band, because the sidebar and panel are fixed-pixel widths rather than percentage-based. A
  future refinement could make the panel width responsive (e.g. `min(360px, 28vw)`) to hold the
  ratio steadier across widths; not implemented in this pass to avoid scope creep beyond the
  correction brief.
- The persistent right-hand panel's default (no-selection) state shows a headline KPI on 6 of
  7 exploration pages (Urban Typology, 15-Minute Istanbul, Cycling Gain, Transit Connection,
  Accessibility Gaps, E-bike). Data & Methods intentionally shows question/description only --
  no single headline number fits a page about reliability -- and instead surfaces the "View
  full methodology" drawer in its header. Every page's panel always shows at least the question
  framing, never an empty area.
