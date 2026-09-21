import type { ClaimRecord } from "@/types/data";

function formatValue(claim: ClaimRecord): string {
  if (claim.unit?.toLowerCase().includes("pct")) return `${claim.exact_value}%`;
  if (claim.unit === "people") {
    const v = claim.exact_value;
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
    if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
    return `${v}`;
  }
  return `${claim.exact_value}`;
}

/** Renders a headline KPI using ONLY claims_registry wording -- the claim-safety contract (Section 26). */
export function KpiCard({ label, claim }: { label: string; claim: ClaimRecord }) {
  return (
    <div className="rounded-2xl border border-o3-card p-5 bg-o3-card flex flex-col gap-2 min-w-[240px]">
      <span className="text-[11px] uppercase tracking-wider text-o3-text-secondary font-medium">{label}</span>
      <span className="text-4xl font-semibold text-o3-text-primary leading-none">{formatValue(claim)}</span>
      <p className="text-sm text-o3-text-secondary leading-snug">{claim.allowed_language ? claim.claim_text : claim.claim_text}</p>
      <details className="mt-1 text-xs text-o3-text-secondary/80">
        <summary className="cursor-pointer select-none text-o3-green hover:text-o3-accent transition-colors">methodology</summary>
        <p className="mt-1">
          Universe: {claim.analysis_universe} <br />
          Denominator: {claim.denominator} <br />
          Quality: {claim.quality_status}
        </p>
      </details>
    </div>
  );
}
