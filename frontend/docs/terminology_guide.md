# Terminology Guide (Phase 13.1)

This documents the full terminology audit (Section 24) behind `frontend/lib/terminology.ts`
and `frontend/lib/labels.ts`. Every occurrence of research/analytical vocabulary in the
frontend was classified:

- **A** — appropriate for general UI as-is
- **B** — should be simplified for primary UI copy
- **C** — should move to methodology/info tooltip only

Internal field names, data files, and code comments are **never** renamed — this is a
display-layer mapping only.

| Term | Classification | Primary UI treatment | Where the technical term still lives |
|---|---|---|---|
| Cross-Application Convergence | B | "Where Signals Align" (title, legend, KPI label) | `InfoTooltip` on the E-bike page; `docs/data_contract.md`; `analysis/framework_synthesis` |
| E-bike Readiness | B | "E-bike Suitability" | Field name `ebike_readiness` unchanged; tooltip explains the model basis |
| E-bike Opportunity | A (kept, clarified) | "E-bike Opportunity" (name kept, explanation added) | Tooltip: "modeled potential," not measured interest |
| Fixed-guideway (transit) | B | "Rail & Metrobüs Access" | `conceptCopy.fixedGuidewayAccess.tooltip`; internal field `fixed_transit_*` unchanged |
| Required needs / required categories | B | "Everyday Essentials" | Internal fields `required_categories_walk_15` etc. unchanged |
| Accessibility Gap | B | "What's Out of Reach?" (question framing) / "Access Gaps" (nav label) | `everyday_gap_type` field and full class names kept internally |
| Data Confidence | B | "How Reliable Is This View?" | `data_confidence` field, `QualityBadge` internal labels kept |
| Typology / Urban Typology | A | Kept as-is ("Urban Typology" nav label, "What kind of urban environment is this?" question) | Cluster numbers (0-4) shown as "Cluster N" -- no invented names, since no authoritative name mapping exists in the frozen artifact (verified: `v2_typology_manifest.json` has no name/label field) |
| Calibrated population | C | Shown as plain "Population" in the Grid Intelligence Card; "calibrated 2020" caveat kept in KPI methodology notes and the Methods page | `docs/data_contract.md`, KPI registry `quality_status` fields |
| Quality-aware / network component / feed coverage | C | Never shown verbatim; surfaced only as "Reliable evidence" / "Network limitation" / "Data insufficient for transit interpretation" / "Known special case (Adalar)" via `lib/labels.ts confidenceClass()` | `docs/data_contract.md`, `methodology_registry.json` |
| Opportunity / Readiness (robustness classes: ROBUST_HIGH etc.) | C | Shown as "Robustly high" / "Frequently high" / etc. (`robustnessLabelMap`) | Raw enum retained in `ebike_readiness_robustness` / `ebike_opportunity_robustness` fields for filtering |
| Modeled (e.g. "modeled accessibility") | A | Kept -- this word is doing real epistemic work (distinguishing model output from observed behavior) and is not jargon in the way the others are | n/a |
| NO_FEED_COVERAGE / NO_TRANSIT_ACCESS_GAP etc. | C | Never shown verbatim; `transitGapTypeLabel` / `transitDataQualityLabel` maps every raw class to a plain sentence, with `TRANSIT_DATA_UNCERTAIN` and `NO_FEED_COVERAGE` both mapping to the SAME user-facing phrase "Data insufficient for transit interpretation" -- deliberately, so the underlying data-coverage reason never leaks into a false "no service" reading | `lib/labels.ts` |
| CYCLE_ONLY_GAIN / CYCLING_CLOSES_EVERYDAY_GAP etc. | C | `activeMobilityInterventionLabel` / `cyclingGapClosureLabel` map every raw enum to a full sentence ("Cycling closes the gap," "Gap remains," etc.) | `lib/labels.ts`; raw values retained for map color-matching |

## Question-first page headers

Every exploration page's header was rewritten to lead with a plain question (Section 4),
sourced from `frontend/lib/terminology.ts` `pageCopy`:

| Page | Old header (Phase 13) | New header (Phase 13.1) |
|---|---|---|
| Urban Typology | "Urban Typology" / long methodology paragraph | "Urban Typology" / **"What kind of urban environment is this?"** |
| 15-Minute Istanbul | "15-Minute Istanbul" / "How much of everyday life..." | "15-Minute Istanbul" / **"What's within a 15-minute walk?"** |
| Cycling Gain | "Cycling Gain" / "What changes when cycling becomes part of the accessibility equation?" | "Cycling Gain" / **"What changes when we add cycling?"** |
| Transit Connection | "Transit Connection" / "Can cycling bring public transport closer?" | unchanged (already question-first) |
| Accessibility Gaps | "Accessibility Gaps" / "Where do mapped accessibility gaps remain..." | **"Access Gaps"** / **"What's still out of reach?"** |
| E-bike | "E-bike" / "Where does the urban environment appear more compatible..." | "E-bike" / **"Where could e-bikes fit best?"** |
| Data & Methods | "Data & Methods" / "How this framework was built..." | "Data & Methods" / **"How was this built, and how reliable is it?"** (with the map framed as **"How Reliable Is This View?"**) |

## What did NOT change

- No underlying analytical field, class name, threshold, or computed value.
- Raw enum values remain fully available in `public/data/layers/*.json` and
  `public/data/details/<district>.json` (Phase 14 split, was `grid_attributes.json`) and are
  used internally for map color-matching and filtering -- only their *display* is humanized.
- Methodology/provenance detail (full `methodology_registry` content) is one click away via
  the "View full methodology" drawer on the Data & Methods page, not deleted.
