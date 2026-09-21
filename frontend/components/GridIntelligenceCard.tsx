"use client";

import { useGridAttributes } from "@/lib/useGridAttributes";
import {
  activeMobilityInterventionLabel,
  cyclingGapClosureLabel,
  everydayGapTypeLabel,
  transitGapTypeLabel,
  formatMinutes,
  formatPopulation,
} from "@/lib/labels";
import { conceptCopy } from "@/lib/terminology";
import { QualityBadge } from "@/components/QualityBadge";
import { InfoTooltip } from "@/components/InfoTooltip";

function Row({ label, value }: { label: React.ReactNode; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between text-sm py-1">
      <span className="text-o3-text-secondary">{label}</span>
      <span className="text-o3-text-primary font-medium">{value}</span>
    </div>
  );
}

/** Progressive-disclosure section (Phase 13.1 Section 18): native <details>, so at most a
 * couple of sections are expanded at once by default rather than everything at full length. */
function Section({ title, defaultOpen = false, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  return (
    <details className="border-t border-o3-card first:border-t-0 py-2 group" open={defaultOpen}>
      <summary className="cursor-pointer select-none list-none flex items-center justify-between text-[11px] uppercase tracking-wider text-o3-green font-medium py-1">
        {title}
        <span className="text-o3-text-secondary group-open:rotate-90 transition-transform">›</span>
      </summary>
      <div className="pt-1 pb-1">{children}</div>
    </details>
  );
}

export function GridIntelligenceCard({ gridId, onClose }: { gridId: string; onClose: () => void }) {
  const { data: row, district, loading } = useGridAttributes(gridId);

  return (
    <div className="w-full h-full flex flex-col bg-o3-bg-primary overflow-hidden">
      <div className="flex items-start justify-between px-5 pt-4 pb-2 shrink-0">
        <div>
          <div className="text-o3-text-secondary text-xs uppercase tracking-wider">{district ?? "…"}</div>
          <div className="text-o3-text-primary font-semibold text-lg">{gridId}</div>
        </div>
        <button
          onClick={onClose}
          className="text-o3-text-secondary hover:text-o3-text-primary rounded-full w-8 h-8 flex items-center justify-center hover:bg-o3-card"
          aria-label="Close cell details"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto o3-scrollbar px-5 pb-6 min-h-0">
        {loading && <p className="text-o3-text-secondary text-sm">Loading…</p>}
        {!loading && !row && <p className="text-o3-text-secondary text-sm">No data available for this cell.</p>}
        {row && (
          <>
            <Section title="Overview" defaultOpen>
              <Row label="Population" value={formatPopulation(row.calibrated_population_2020)} />
              <Row label="Population density" value={`${Math.round(row.population_density_per_km2).toLocaleString()} / km²`} />
              <Row label="Urban typology" value={`Cluster ${row.typology_cluster}`} />
              <p className="text-sm text-o3-text-primary font-medium mt-2">
                {activeMobilityInterventionLabel[row.active_mobility_intervention] ?? row.active_mobility_intervention}
              </p>
            </Section>

            <Section title="Everyday Access" defaultOpen>
              <div className="grid grid-cols-2 gap-x-4 text-xs text-o3-text-secondary mb-1 mt-1">
                <span>Walking</span>
                <span>Cycling</span>
              </div>
              {(["Food", "Healthcare", "Education"] as const).map((label, i) => {
                const walkKeys = ["food_walk_min", "healthcare_walk_min", "education_walk_min"] as const;
                const cycleKeys = ["food_cycle_min", "healthcare_cycle_min", "education_cycle_min"] as const;
                return (
                  <div key={label} className="grid grid-cols-2 gap-x-4 text-sm py-1">
                    <span className="text-o3-text-primary">
                      {label}: {formatMinutes(row[walkKeys[i]])}
                    </span>
                    <span className="text-o3-text-primary">{formatMinutes(row[cycleKeys[i]])}</span>
                  </div>
                );
              })}
              <p className="text-xs text-o3-text-secondary mt-2">
                {everydayGapTypeLabel[row.everyday_gap_type] ?? row.everyday_gap_type} &middot;{" "}
                {cyclingGapClosureLabel[row.cycling_gap_closure] ?? row.cycling_gap_closure}
              </p>
            </Section>

            <Section title="Transit">
              <div className="text-xs text-o3-text-secondary mb-1">General transit</div>
              <Row label="Walking" value={formatMinutes(row.general_transit_walk_min)} />
              <Row label="Cycling" value={formatMinutes(row.general_transit_cycle_min)} />
              <div className="text-xs text-o3-text-secondary mt-2 mb-1 flex items-center">
                {conceptCopy.fixedGuidewayAccess.uiTitle}
                <InfoTooltip>{conceptCopy.fixedGuidewayAccess.tooltip}</InfoTooltip>
              </div>
              <Row label="Walking" value={formatMinutes(row.fixed_transit_walk_min)} />
              <Row label="Cycling" value={formatMinutes(row.fixed_transit_cycle_min)} />
              <p className="text-xs text-o3-text-secondary mt-2">{transitGapTypeLabel[row.transit_gap_type] ?? row.transit_gap_type}</p>
            </Section>

            <Section title="E-bike">
              <Row
                label={<span className="flex items-center">{conceptCopy.ebikeReadiness.uiTitle}<InfoTooltip>{conceptCopy.ebikeReadiness.tooltip}</InfoTooltip></span>}
                value={row.ebike_readiness.toFixed(2)}
              />
              <Row
                label={<span className="flex items-center">{conceptCopy.ebikeOpportunity.uiTitle}<InfoTooltip>{conceptCopy.ebikeOpportunity.tooltip}</InfoTooltip></span>}
                value={row.ebike_opportunity.toFixed(2)}
              />
            </Section>

            <Section title="Data Quality">
              <div className="flex flex-col gap-2 mt-1">
                <QualityBadge walkingQuality={row.walking_quality} cyclingQuality={row.cycling_quality} transitDataQuality={row.transit_data_quality} />
              </div>
            </Section>
          </>
        )}
      </div>
    </div>
  );
}
