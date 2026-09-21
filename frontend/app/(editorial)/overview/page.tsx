import Link from "next/link";
import { getClaim, getCaseStudies } from "@/lib/data";
import { KpiCard } from "@/components/KpiCard";
import { InsightCard } from "@/components/InsightCard";
import { CaseStudyNavigator } from "@/components/CaseStudyNavigator";
import { ShareableInsightCard } from "@/components/ShareableInsightCard";

const STORY = [
  {
    n: "01",
    title: "Istanbul is not one urban environment",
    body: "A frozen five-cluster typology built from ~94 spatial indicators shows Istanbul is made of recurring, structurally different urban regimes -- not a single uniform city.",
    cta: { href: "/typology", label: "Explore urban typology" },
  },
  {
    n: "02",
    title: "Everyday access is highly concentrated",
    body: "Complete 15-minute walking access to Food, Healthcare and Education is concentrated in a small share of grid cells that hold a large share of the population -- a real property of Istanbul's population distribution, not a modeling artifact.",
    cta: { href: "/fifteen-minute", label: "See 15-Minute Istanbul" },
  },
  {
    n: "03",
    title: "Cycling changes the map",
    body: "Modeled cycling accessibility reaches a much larger share of the population than walking alone, and materially expands where residents could potentially reach everyday needs.",
    cta: { href: "/cycling-gain", label: "See the Cycling Gain" },
  },
  {
    n: "04",
    title: "Cycling can also extend transit catchments",
    body: "Beyond everyday needs, cycling potentially expands how many residents can reach general transit and, especially, fixed-guideway/high-capacity transit stops within a modeled time budget.",
    cta: { href: "/transit", label: "See Transit Connection" },
  },
  {
    n: "05",
    title: "Some gaps remain",
    body: "Not every accessibility gap is closed by cycling. Where destinations themselves are sparse, no mode-shift can create access that does not exist.",
    cta: { href: "/gaps", label: "See Accessibility Gaps" },
  },
  {
    n: "06",
    title: "Data quality matters",
    body: "Network and transit-feed quality vary across the city. This product treats uncertainty as a first-class signal, not something to hide inside an average.",
    cta: { href: "/methods", label: "See Data & Methods" },
  },
];

export default async function OverviewPage() {
  const [c01, c02, c03] = await Promise.all([getClaim("C01"), getClaim("C02"), getClaim("C03")]);
  const { cases } = await getCaseStudies();

  return (
    <div className="max-w-6xl mx-auto px-6 py-14 flex flex-col gap-14">
      <header className="flex flex-col gap-3 max-w-3xl">
        <h1 className="text-o3-text-primary text-3xl md:text-4xl font-semibold">Overview</h1>
        <p className="text-o3-text-secondary text-base md:text-lg">
          What does accessibility look like across Istanbul, and what changes when walking, cycling and transit are considered together?
        </p>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {c01 && <KpiCard label="Walking access (Food+Healthcare+Education, 15min)" claim={c01} />}
        {c03 && <KpiCard label="Cycling access (Food+Healthcare+Education, 15min)" claim={c03} />}
        {c02 && <KpiCard label="Cycling accessibility gain" claim={c02} />}
      </div>

      <div className="flex flex-col gap-6">
        {STORY.map((s) => (
          <InsightCard key={s.n} eyebrow={s.n} title={s.title}>
            <p>{s.body}</p>
            <Link href={s.cta.href} className="inline-block mt-3 text-o3-accent text-sm font-medium hover:underline">
              {s.cta.label} →
            </Link>
          </InsightCard>
        ))}
      </div>

      <section className="flex flex-col gap-4">
        <h2 className="text-o3-text-primary text-xl font-semibold">Explore examples</h2>
        <p className="text-o3-text-secondary text-sm max-w-2xl">
          Nine representative cells, selected by analytical archetype (not by picking extremes), each linking to the relevant module with
          the cell already selected.
        </p>
        <CaseStudyNavigator cases={cases} />
      </section>

      {c02 && (
        <section className="flex flex-col gap-4">
          <h2 className="text-o3-text-primary text-xl font-semibold">Shareable insight</h2>
          <ShareableInsightCard claim={c02} headline="Cycling Accessibility Gain" />
        </section>
      )}

      <section className="pt-6 border-t border-o3-card">
        <p className="text-o3-text-secondary/70 text-[10px] uppercase tracking-wider mb-2">About</p>
        <p className="text-o3-text-secondary/70 text-xs max-w-2xl">
          A spatial intelligence project by{" "}
          <a
            href="https://www.linkedin.com/company/o3sustainability/"
            target="_blank"
            rel="noopener noreferrer"
            className="underline decoration-dotted underline-offset-2 hover:text-o3-text-primary transition-colors"
          >
            O3 Sustainability
          </a>
          . Developed by{" "}
          <a
            href="https://www.linkedin.com/in/onursenturky/"
            target="_blank"
            rel="noopener noreferrer"
            className="underline decoration-dotted underline-offset-2 hover:text-o3-text-primary transition-colors"
          >
            Onur Şentürk
          </a>
          .
        </p>
      </section>
    </div>
  );
}
