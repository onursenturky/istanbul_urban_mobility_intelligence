import { getDistrictSummary, getClaim } from "@/lib/data";
import { PageMapExplorer, type MapLayerConfig } from "@/components/PageMapExplorer";
import { fieldColorMaps } from "@/lib/mapColors";
import { pageCopy, conceptCopy } from "@/lib/terminology";

const robustnessLabelMap: Record<string, string> = {
  ROBUST_HIGH: "Robustly high",
  FREQUENT_HIGH: "Frequently high",
  CONDITIONAL_HIGH: "Conditionally high",
  RARE_HIGH: "Rarely high",
  NEVER_HIGH: "Never high",
};

const convergenceLabelMap: Record<string, string> = {
  BOTH_SIGNALS: "Both signals",
  ACCESSIBILITY_GAIN_ONLY: "Accessibility gain only",
  HIGH_EBIKE_READINESS_ONLY: "High suitability only",
  NEITHER: "Neither",
};

const layers: MapLayerConfig[] = [
  {
    value: "readiness", label: conceptCopy.ebikeReadiness.uiTitle, field: "ebike_readiness_robustness",
    colorMap: fieldColorMaps.ebike_readiness_robustness, labelMap: robustnessLabelMap,
    legendOrder: ["ROBUST_HIGH", "FREQUENT_HIGH", "CONDITIONAL_HIGH", "RARE_HIGH", "NEVER_HIGH"],
    legendTitle: conceptCopy.ebikeReadiness.uiTitle,
  },
  {
    value: "opportunity", label: conceptCopy.ebikeOpportunity.uiTitle, field: "ebike_opportunity_robustness",
    colorMap: fieldColorMaps.ebike_opportunity_robustness, labelMap: robustnessLabelMap,
    legendOrder: ["ROBUST_HIGH", "FREQUENT_HIGH", "CONDITIONAL_HIGH", "RARE_HIGH", "NEVER_HIGH"],
    legendTitle: conceptCopy.ebikeOpportunity.uiTitle,
  },
  {
    value: "convergence", label: conceptCopy.crossApplicationConvergence.uiTitle, field: "cross_app_convergence",
    colorMap: fieldColorMaps.cross_app_convergence, labelMap: convergenceLabelMap,
    legendOrder: ["BOTH_SIGNALS", "ACCESSIBILITY_GAIN_ONLY", "HIGH_EBIKE_READINESS_ONLY", "NEITHER"],
    legendTitle: conceptCopy.crossApplicationConvergence.uiTitle,
  },
];

export default async function EbikePage({ searchParams }: { searchParams: Promise<{ grid?: string; district?: string }> }) {
  const { grid, district } = await searchParams;
  const [districts, c08] = await Promise.all([getDistrictSummary(), getClaim("C08")]);
  const districtNames = districts.map((d) => d.district);
  const copy = pageCopy.ebike;

  return (
    <PageMapExplorer
      title={copy.title}
      question={copy.question}
      infoTooltip={conceptCopy.crossApplicationConvergence.tooltip}
      layers={layers}
      districts={districtNames}
      initialGrid={grid}
      initialDistrict={district}
      panelDescription={copy.description}
      panelKpis={c08 ? [{ label: conceptCopy.crossApplicationConvergence.uiTitle, claim: c08 }] : []}
    />
  );
}
