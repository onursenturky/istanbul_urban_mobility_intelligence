import Link from "next/link";
import { getHeadlineKpis } from "@/lib/data";

export default async function LandingPage() {
  const { headline_findings } = await getHeadlineKpis();
  const h01 = headline_findings.find((h) => (h as { claim_id?: string }).claim_id === "H01") as { value_pct?: number } | undefined;

  return (
    <div className="relative overflow-hidden">
      <div
        className="absolute inset-0 -z-10"
        style={{
          background:
            "radial-gradient(1200px 600px at 15% -10%, rgba(178,240,147,0.14), transparent 60%), radial-gradient(1000px 500px at 100% 0%, rgba(107,175,130,0.14), transparent 55%), #113306",
        }}
        aria-hidden
      />
      {/* subtle Istanbul-grid motif standing in for the map, built from CSS, not stock imagery */}
      <div className="absolute inset-0 -z-10 opacity-[0.15]" aria-hidden>
        <svg width="100%" height="100%" preserveAspectRatio="none">
          <defs>
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#B2F093" strokeWidth="0.5" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>
      </div>

      <section className="max-w-5xl mx-auto px-6 pt-20 pb-24 md:pt-32 md:pb-32 flex flex-col gap-8">
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

        <p className="text-o3-text-secondary/70 text-xs pt-10">An O3 Sustainability spatial intelligence project.</p>
      </section>
    </div>
  );
}
