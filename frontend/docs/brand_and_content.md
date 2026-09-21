# Brand & Content

## Identity hierarchy

**Primary product**: Istanbul / Urban Mobility Intelligence.
**Publisher identity**: O3 Sustainability, present but subordinate — "An O3 Sustainability
spatial intelligence project" appears on the landing page and in the footer, never as the
primary heading. The analytical framework is the product; O3 is the creator/publisher.

## Design tokens (single source of truth: `app/globals.css` + `lib/theme.ts`)

| Token | Hex | Use |
|---|---|---|
| `--o3-bg-primary` | `#194B0A` | Nav, sidebars, branded surfaces |
| `--o3-bg-deep` | `#113306` | Page background |
| `--o3-accent` | `#B2F093` | CTA, active nav, selected states — used selectively |
| `--o3-green` | `#6BAF82` | Secondary accents, chart bars |
| `--o3-text-primary` | `#F1FFE0` | Titles, KPI values |
| `--o3-text-secondary` | `#C5DFC9` | Body/metadata |
| `--o3-highlight` / `--o3-highlight-text` | `#F1FFE0` / `#113306` | Editorial highlight panels |

Typography: **Outfit** throughout, loaded via `next/font/google` in `app/layout.tsx`
(weights 400/500/600/700), exposed as `--font-outfit` and wired into Tailwind's
`font-outfit` + the `body` default in `globals.css`.

## Analytical semantic palette (deliberately NOT five shades of green)

Defined in `lib/theme.ts` (`semanticColors`) and `lib/mapColors.ts`:

- **positive** `#6BAF82` — complete / already-sufficient
- **gain** `#B2F093` — cycling closes the gap (flagship positive signal)
- **partial** `#E0C168` — partial gain (warm-neutral, visually distinct)
- **gap** `#E0785A` — remaining accessibility gap
- **uncertain** `#8C9A91` — evidence uncertain
- **transitLimit** `#7D8BB0` — transit-data limitation
- **knownLimit** `#A98CC7` — known network limitation (Adalar)

## Human-readable language (`lib/labels.ts`)

Every raw analytical enum has a human-readable mapping used as the PRIMARY UI label,
with the raw value retained only for color-matching, filtering, and links to the claims/
methodology registries. Example: `CYCLING_CLOSES_EVERYDAY_GAP` → "Cycling closes the gap",
never shown as the bare enum string in body text.

## Claim safety

Every headline analytical statement in the UI resolves through `getClaim(claimId)`
(`lib/data.ts`), backed by `claims_registry.json`. Components (`KpiCard`,
`ShareableInsightCard`) render `claim.claim_text` / `claim.exact_value` directly — no
component hand-writes a headline number or its wording. This is the mechanism that
prevents the prohibited-overclaim phrasings (e.g. "lives in a 15-minute city") from ever
reaching the UI; see `claims_registry.csv`'s `prohibited_overclaim` column and
`qa/data_qa.py` check J for the automated guard.

## Content hooks (`content/content_hooks.json`)

10 editorial hooks (TR + EN), each tagged with a `claim_id`, a `related_dashboard_page`,
and an `interpretation_note` restating the guardrail language. These are prompts for future
editorial/social content, not published copy — no automated posting exists or is planned in
this phase.

## Prohibited language (enforced editorially + spot-checked programmatically)

Never: "15-minute city" (unqualified), "residents would benefit", "validates", "proves",
"service desert", "mobility poverty", "underserved community", "deprived". Always prefer:
"modeled accessibility", "potentially closes", "calibrated population distribution",
"cross-application convergence" (never "external validation").
