import type { ClaimRecord } from "@/types/data";
import { O3BrandMark } from "@/components/O3BrandMark";

const ASPECT_CLASS: Record<"1:1" | "4:5" | "16:9", string> = {
  "1:1": "aspect-square",
  "4:5": "aspect-[4/5]",
  "16:9": "aspect-video",
};

/**
 * Reusable shareable-content component (Phase 13 Section 25): KPI + short
 * explanation + methodology note + O3 identity, in a fixed social aspect
 * ratio. No automated posting -- this only renders the visual card.
 */
export function ShareableInsightCard({
  claim,
  headline,
  aspect = "4:5",
}: {
  claim: ClaimRecord;
  headline: string;
  aspect?: "1:1" | "4:5" | "16:9";
}) {
  return (
    <div
      className={`relative ${ASPECT_CLASS[aspect]} w-full max-w-md rounded-3xl overflow-hidden flex flex-col justify-between p-8`}
      style={{ background: "linear-gradient(160deg, #194B0A 0%, #113306 100%)" }}
    >
      <div className="absolute inset-0 opacity-[0.06]" style={{ backgroundImage: "radial-gradient(circle at 20% 20%, #B2F093 0, transparent 45%)" }} aria-hidden />
      <div className="relative">
        <span className="text-o3-text-secondary text-[11px] uppercase tracking-wider font-medium">{headline}</span>
        <div className="text-o3-accent text-5xl font-semibold mt-3 leading-none">
          {claim.unit === "people"
            ? claim.exact_value >= 1_000_000
              ? `${(claim.exact_value / 1_000_000).toFixed(2)}M`
              : `${(claim.exact_value / 1000).toFixed(0)}K`
            : `${claim.exact_value}%`}
        </div>
      </div>
      <div className="relative flex flex-col gap-3">
        <p className="text-o3-text-primary text-sm leading-snug">{claim.claim_text}</p>
        <p className="text-o3-text-secondary text-[11px] leading-snug">{claim.quality_status}</p>
        <div className="flex items-center justify-between pt-3 border-t border-white/10">
          <O3BrandMark compact />
          <span className="text-o3-text-secondary text-[10px]">Istanbul Urban Mobility Intelligence</span>
        </div>
      </div>
    </div>
  );
}
