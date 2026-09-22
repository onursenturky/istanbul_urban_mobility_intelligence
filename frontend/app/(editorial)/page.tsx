import Link from "next/link";
import { getHeadlineKpis } from "@/lib/data";
import { ISTANBUL_SILHOUETTE_VIEWBOX, ISTANBUL_SILHOUETTE_PATH } from "@/lib/istanbulSilhouette";

export default async function LandingPage() {
  const { headline_findings } = await getHeadlineKpis();
  const h01 = headline_findings.find((h) => (h as { claim_id?: string }).claim_id === "H01") as { value_pct?: number } | undefined;
  const h03 = headline_findings.find((h) => (h as { claim_id?: string }).claim_id === "H03") as { value_pct?: number } | undefined;

  return (
    <div className="relative" style={{ background: "#113306" }}>
      {/* The actual Istanbul coastline (traced from the real district boundary data, see
          lib/istanbulSilhouette.ts) standing in for the map -- this IS the hero visual (per
          design direction: let the spatial product be the hero), not decorative illustration.
          Uses a POSITIVE z-index on the text section to stack above this (not a negative
          z-index on this layer) -- negative z-index values were found, in testing, to never
          paint at all in this environment regardless of cause (overflow/transform/opacity all
          ruled out), so the foreground is what gets the explicit stacking here, not the
          background. */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden>
        <svg
          className="absolute -right-24 top-1/2 -translate-y-1/2 h-[520px] md:h-[680px] w-auto max-w-none opacity-[0.22] pointer-events-none"
          viewBox={ISTANBUL_SILHOUETTE_VIEWBOX}
        >
          <path d={ISTANBUL_SILHOUETTE_PATH} fill="#B2F093" />
        </svg>
      </div>

      <section className="relative z-10 max-w-5xl mx-auto px-6 pt-20 pb-24 md:pt-32 md:pb-32 flex flex-col gap-8">
        <div>
          <p className="text-o3-text-secondary text-sm tracking-widest uppercase mb-3">Istanbul</p>
          <h1 className="text-o3-text-primary font-semibold text-5xl md:text-7xl leading-[1.05] tracking-tight">
            Urban Mobility
            <br />
            Intelligence
          </h1>
        </div>

        <p className="text-o3-text-primary text-xl md:text-2xl font-medium max-w-2xl">How accessible is everyday life across Istanbul?</p>
        <p className="text-o3-text-secondary text-base md:text-lg max-w-2xl leading-relaxed">
          Explore how urban form, walking, cycling and public transport shape access to everyday needs across the city.
          {typeof h01?.value_pct === "number" && (
            <>
              {" "}
              Today, modeled 15-minute walking access to Food, Healthcare and Education reaches{" "}
              <span className="text-o3-accent font-medium">{h01.value_pct}%</span> of the calibrated 2020 population.
            </>
          )}
        </p>

        <div className="flex flex-wrap items-center gap-4 pt-2">
          <Link
            href="/overview"
            className="rounded-full bg-o3-accent px-6 py-3 font-medium text-sm hover:brightness-105 transition"
            style={{ color: "#113306" }}
          >
            Explore the map
          </Link>
          <Link
            href="/methods"
            className="rounded-full border border-o3-card-strong px-6 py-3 font-medium text-sm text-o3-text-primary hover:bg-o3-card transition"
          >
            How it works
          </Link>
        </div>

        {(typeof h01?.value_pct === "number" || typeof h03?.value_pct === "number") && (
          <div className="flex flex-wrap gap-x-10 gap-y-4 pt-8 border-t border-o3-card max-w-2xl">
            {typeof h01?.value_pct === "number" && (
              <div className="flex flex-col gap-0.5">
                <span className="text-o3-text-primary text-3xl font-semibold leading-none">{h01.value_pct}%</span>
                <span className="text-o3-text-secondary text-xs">walking access, 15 min</span>
              </div>
            )}
            {typeof h03?.value_pct === "number" && (
              <div className="flex flex-col gap-0.5">
                <span className="text-o3-text-primary text-3xl font-semibold leading-none">{h03.value_pct}%</span>
                <span className="text-o3-text-secondary text-xs">cycling access, 15 min</span>
              </div>
            )}
          </div>
        )}

        <p className="text-o3-text-secondary/70 text-xs pt-2">An O3 Sustainability spatial intelligence project.</p>
      </section>
    </div>
  );
}
