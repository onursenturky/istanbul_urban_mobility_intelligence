import type { ClaimRecord } from "@/types/data";

/**
 * Default (no cell selected) state of the desktop side panel (Phase 13.1 Section 18/104):
 * rather than leaving the panel empty, it carries the page's question framing and headline
 * figures, so the map-dominant layout never wastes the panel's space.
 */
export function PanelOverview({
  question,
  description,
  kpis,
  hint = "Click any cell on the map to see its details.",
}: {
  question: string;
  description: string;
  kpis: { label: string; claim: ClaimRecord }[];
  hint?: string;
}) {
  return (
    <div className="w-full h-full flex flex-col bg-o3-bg-primary overflow-y-auto o3-scrollbar px-5 py-5 gap-5">
      <div>
        <h2 className="text-o3-text-primary text-lg font-semibold leading-snug">{question}</h2>
        <p className="text-o3-text-secondary text-sm mt-1.5 leading-relaxed">{description}</p>
      </div>
      <div className="flex flex-col gap-3">
        {kpis.map(({ label, claim }) => (
          <div key={claim.claim_id} className="rounded-xl border border-o3-card bg-o3-card p-4">
            <span className="text-[10px] uppercase tracking-wider text-o3-text-secondary font-medium">{label}</span>
            <div className="text-2xl font-semibold text-o3-text-primary leading-none mt-1">
              {claim.unit === "people"
                ? claim.exact_value >= 1_000_000
                  ? `${(claim.exact_value / 1_000_000).toFixed(2)}M`
                  : `${(claim.exact_value / 1000).toFixed(0)}K`
                : `${claim.exact_value}%`}
            </div>
            <p className="text-o3-text-secondary text-xs mt-1.5 leading-snug">{claim.claim_text}</p>
          </div>
        ))}
      </div>
      <p className="text-o3-text-secondary text-xs mt-auto pt-3 border-t border-o3-card">{hint}</p>
    </div>
  );
}
