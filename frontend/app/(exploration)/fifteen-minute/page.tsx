import { getDistrictSummary, getClaim } from "@/lib/data";
import { PageMapExplorer, type MapLayerConfig } from "@/components/PageMapExplorer";
import { semanticColors } from "@/lib/theme";
import { pageCopy } from "@/lib/terminology";

const requiredNeedsColorMap: Record<string, string> = {
  "0": "#9A3B2A",
  "1": semanticColors.gap,
  "2": semanticColors.partial,
  "3": semanticColors.positive,
};
const requiredNeedsLabelMap: Record<string, string> = {
  "0": "0 / 3 everyday essentials",
  "1": "1 / 3 everyday essentials",
  "2": "2 / 3 everyday essentials",
  "3": "3 / 3 everyday essentials (complete)",
};

const layers: MapLayerConfig[] = [
  {
    value: "walk", label: "Walking", field: "required_categories_walk_15",
    colorMap: requiredNeedsColorMap, labelMap: requiredNeedsLabelMap, legendOrder: ["3", "2", "1", "0"],
    legendTitle: "Everyday essentials reachable, walking (15 min)",
  },
  {
    value: "cycle", label: "Cycling", field: "required_categories_cycle_15",
    colorMap: requiredNeedsColorMap, labelMap: requiredNeedsLabelMap, legendOrder: ["3", "2", "1", "0"],
    legendTitle: "Everyday essentials reachable, cycling (15 min)",
  },
];

export default async function FifteenMinutePage({ searchParams }: { searchParams: Promise<{ grid?: string; district?: string }> }) {
  const { grid, district } = await searchParams;
  const [districts, c01] = await Promise.all([getDistrictSummary(), getClaim("C01")]);
  const districtNames = districts.map((d) => d.district);
  const copy = pageCopy.fifteenMinute;

  return (
    <PageMapExplorer
      title={copy.title}
      question={copy.question}
      infoTooltip={'Shows modeled walking (and cycling) access to Food, Healthcare and Education -- not a claim that any area is a complete "15-minute city."'}
      layers={layers}
      districts={districtNames}
      initialGrid={grid}
      initialDistrict={district}
      panelDescription={copy.description}
      panelKpis={c01 ? [{ label: "Complete walking access", claim: c01 }] : []}
    />
  );
}
