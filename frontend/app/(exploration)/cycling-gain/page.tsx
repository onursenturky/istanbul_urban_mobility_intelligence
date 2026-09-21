import { getDistrictSummary, getClaim } from "@/lib/data";
import { PageMapExplorer, type MapLayerConfig } from "@/components/PageMapExplorer";
import { fieldColorMaps } from "@/lib/mapColors";
import { activeMobilityInterventionLabel } from "@/lib/labels";
import { pageCopy } from "@/lib/terminology";

const layers: MapLayerConfig[] = [
  {
    value: "intervention",
    label: "Accessibility change",
    field: "active_mobility_intervention",
    colorMap: fieldColorMaps.active_mobility_intervention,
    labelMap: activeMobilityInterventionLabel,
    legendOrder: [
      "WALKING_SUFFICIENT",
      "CYCLING_CLOSES_EVERYDAY_GAP",
      "CYCLING_PARTIAL_GAIN",
      "CYCLING_DOES_NOT_CLOSE_GAP",
      "QUALITY_UNCERTAIN",
    ],
    legendTitle: "Walking → cycling accessibility change",
  },
];

export default async function CyclingGainPage({ searchParams }: { searchParams: Promise<{ grid?: string; district?: string }> }) {
  const { grid, district } = await searchParams;
  const [districts, c02, c03] = await Promise.all([getDistrictSummary(), getClaim("C02"), getClaim("C03")]);
  const districtNames = districts.map((d) => d.district);
  const copy = pageCopy.cyclingGain;

  return (
    <PageMapExplorer
      title={copy.title}
      question={copy.question}
      infoTooltip="A descriptive network measurement of modeled potential accessibility -- not a validated mode-choice prediction or a claim about how people will actually travel."
      layers={layers}
      districts={districtNames}
      initialGrid={grid}
      initialDistrict={district}
      panelDescription={copy.description}
      panelKpis={[
        ...(c03 ? [{ label: "Complete cycling access", claim: c03 }] : []),
        ...(c02 ? [{ label: "Cycling accessibility gain", claim: c02 }] : []),
      ]}
    />
  );
}
