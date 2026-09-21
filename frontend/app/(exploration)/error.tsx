"use client";

// Scoped to the exploration route group (Typology, 15-Minute, Cycling Gain, Transit, Gaps,
// E-bike, Methods) so a map/data-fetch failure on one of these pages shows map-specific
// copy, while a failure on an editorial page (landing/overview) falls through to the more
// generic app/error.tsx instead. No raw stack traces shown to the user (Phase 14 Section 29).
export default function ExplorationError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="h-screen flex items-center justify-center" style={{ background: "#113306" }}>
      <section className="max-w-md mx-auto px-6 flex flex-col gap-5 text-center items-center">
        <p className="text-o3-text-secondary text-sm tracking-widest uppercase">Map error</p>
        <h1 className="text-o3-text-primary font-semibold text-2xl md:text-3xl leading-tight">We couldn&apos;t load this map.</h1>
        <p className="text-o3-text-secondary text-sm max-w-sm">
          This is a display problem, not a change to the underlying data. Try again, or return to the overview.
        </p>
        <div className="flex gap-3 mt-1">
          <button
            onClick={reset}
            className="rounded-full bg-o3-accent px-5 py-2.5 font-medium text-sm hover:brightness-105 transition"
            style={{ color: "#113306" }}
          >
            Try again
          </button>
          <a
            href="/overview"
            className="rounded-full border border-o3-card-strong px-5 py-2.5 font-medium text-sm text-o3-text-primary hover:bg-o3-card transition"
          >
            Back to overview
          </a>
        </div>
      </section>
    </div>
  );
}
