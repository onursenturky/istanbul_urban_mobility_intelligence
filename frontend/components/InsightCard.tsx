/**
 * Editorial narrative block (Overview page's numbered story section). Deliberately no
 * card/border-box/fill treatment -- a top rule plus generous spacing establishes separation
 * between entries, and a max line-length keeps the prose readable, rather than boxing each
 * point like a marketing feature grid.
 */
export function InsightCard({ eyebrow, title, children }: { eyebrow?: string; title: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-o3-card pt-6 md:pt-8 max-w-2xl">
      {eyebrow && <span className="text-xs uppercase tracking-wider font-semibold text-o3-green">{eyebrow}</span>}
      <h3 className="text-xl md:text-2xl font-semibold mt-1 mb-2 text-o3-text-primary">{title}</h3>
      <div className="text-sm md:text-base leading-relaxed text-o3-text-secondary">{children}</div>
    </div>
  );
}
