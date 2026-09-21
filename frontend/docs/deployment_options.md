# Deployment Options (Evaluation Only — Not Configured)

Per the Phase 14 stop condition, this document evaluates hosting options and gives a
recommendation. **Nothing here has been deployed, no account has been created, no DNS has been
configured.** Deployment is the next explicit step after this phase, not part of it.

## What the app needs from a host

- Next.js 15 App Router support (server components, dynamic routes with `searchParams`, the
  `next/og` `ImageResponse` route for the social preview image).
- Static file serving for `public/data/` (~39MB total, served as plain JSON — no special
  handling required, just correct caching headers for immutable content).
- No database, no server-side session state, no environment secrets (the app has none).
- A custom domain option (for the eventual `mobility.o3sustainability.com` or
  `o3sustainability.com/projects/istanbul-mobility` structure — see below).
- Reasonable free/low-cost tier, since this is a portfolio-style spatial-intelligence product,
  not a high-traffic SaaS.

## Options considered

### Vercel (recommended)

- **Next.js compatibility**: first-party — Vercel builds and maintains Next.js. Every feature
  this app uses (App Router, server components, `next/og`, dynamic routes) works with zero
  configuration.
- **Static assets**: `public/data/`'s ~39MB is well within Vercel's static asset limits per
  deployment; served from their CDN with correct immutable caching automatically.
- **MapLibre**: purely client-side (loads the CARTO basemap and this app's own static JSON
  directly from the browser) — no server-side map rendering is needed, so there's nothing
  Vercel-specific to configure here.
- **Cost**: free Hobby tier covers this app's traffic profile comfortably (no server-side
  compute beyond serving pages and the one dynamic OG-image route, which is cheap and rarely
  invoked — social crawlers, not every visitor).
- **Custom domain**: trivial to attach either a subdomain (`mobility.o3sustainability.com`) or a
  path if O3's main site is not itself on Vercel (would need a reverse-proxy/rewrite rule on the
  main site pointing `/projects/istanbul-mobility` at this deployment — see "Domain structure"
  below).
- **Scalability**: not a concern at this app's expected traffic; Vercel's CDN handles far more.

### Cloudflare Pages (credible alternative)

- **Next.js compatibility**: good via `@cloudflare/next-on-pages`, but App Router features this
  app relies on (server components reading the filesystem via `fs/promises` in `lib/data.ts`,
  the `next/og` image route) need the Node.js compatibility flag enabled and occasionally lag
  behind Vercel's same-day Next.js support. Workable, not zero-friction.
- **Static assets**: excellent — Cloudflare's CDN is very strong for exactly this kind of large-
  static-JSON-plus-small-app workload.
- **Cost**: generous free tier, arguably even more generous than Vercel's for pure static/CDN
  traffic.
- **Custom domain**: easiest of all three if O3's own DNS is already on Cloudflare.
- **Trade-off vs. Vercel**: slightly more setup friction for the dynamic parts of this specific
  app (the `fs`-reading server components and `next/og` route); no functional blocker found,
  just less "zero-config."

### Netlify (workable, not preferred)

- **Next.js compatibility**: supported via their official Next.js runtime, comparable feature
  coverage to Cloudflare Pages, historically a step behind Vercel on newest App Router features.
- **Static assets / cost / domain**: all comparable to the above two, no meaningful differentiator
  in either direction for this specific app.
- Included for completeness; no specific advantage over Vercel or Cloudflare Pages was found for
  this app's needs.

## Recommendation

**Vercel**, as the primary recommendation, because this app uses nothing beyond mainstream
Next.js App Router features and gets first-party, zero-configuration support for all of them
(including the one dynamic route, the OG image generator) at no cost for this traffic profile.

**Cloudflare Pages** as the credible alternative, specifically if O3 Sustainability's own domain
and DNS already live on Cloudflare — the domain-attachment story would then be simpler than
pointing a Cloudflare-managed domain at a Vercel deployment.

This is a hosting-platform choice, not a popularity choice: both were evaluated specifically
against this app's actual requirements (static JSON payload size, App Router feature surface,
zero database/secrets, expected traffic), and Vercel wins on setup friction for the *specific*
features this app already uses, not on brand recognition.

## Domain structure (planning only — no DNS changes made)

Two structures were considered for where this product would live once deployed:

1. `mobility.o3sustainability.com` — a dedicated subdomain. Cleanest separation, easiest to
   point directly at a Vercel/Cloudflare deployment via a single CNAME, no interaction with
   O3's main site's own routing.
2. `o3sustainability.com/projects/istanbul-mobility` — a path under the main O3 site. Requires
   the main site's own host to support a reverse-proxy/rewrite rule forwarding that path to this
   app's deployment (straightforward on most platforms, but is a dependency on however the main
   O3 site itself is hosted, which is outside this project's scope to assume).

**No recommendation is forced between these two** — it depends on whether O3 wants this treated
as a flagship subdomain product or one entry in a `/projects/` index, which is a brand/marketing
decision, not a technical one. Both are technically straightforward with either recommended
host. This is documented for the next explicit deployment step, not decided here.
