import { getDistrictSummary, getMethodologyRegistry } from "@/lib/data";
import { PageMapExplorer, type MapLayerConfig } from "@/components/PageMapExplorer";
import { fieldColorMaps } from "@/lib/mapColors";
import { MethodologyDrawer, type MethodologyRow } from "@/components/MethodologyDrawer";
import { pageCopy, conceptCopy } from "@/lib/terminology";

const confidenceLabelMap: Record<string, string> = {
  RELIABLE: "Reliable evidence",
  NETWORK_LIMITATION: "Network limitation",
  TRANSIT_DATA_LIMITATION: "Data insufficient for transit interpretation",
  MULTIPLE_LIMITATIONS: "Multiple limitations",
  KNOWN_SPECIAL_CASE: "Known special case (Adalar)",
};

const layers: MapLayerConfig[] = [
  {
    value: "confidence", label: "Reliability", field: "data_confidence",
    colorMap: fieldColorMaps.data_confidence, labelMap: confidenceLabelMap,
    legendOrder: ["RELIABLE", "NETWORK_LIMITATION", "TRANSIT_DATA_LIMITATION", "MULTIPLE_LIMITATIONS", "KNOWN_SPECIAL_CASE"],
    legendTitle: conceptCopy.dataConfidence.uiTitle,
  },
];

export default async function MethodsPage({ searchParams }: { searchParams: Promise<{ grid?: string; district?: string }> }) {
  const { grid, district } = await searchParams;
  const [districts, methodology] = await Promise.all([getDistrictSummary(), getMethodologyRegistry()]);
  const districtNames = districts.map((d) => d.district);
  const rows = methodology as unknown as MethodologyRow[];
  const copy = pageCopy.methods;

  return (
    <PageMapExplorer
      title={copy.title}
      question={conceptCopy.dataConfidence.uiTitle}
      infoTooltip="This framework combines frozen datasets of different vintages: population reflects a calibrated 2020 distribution; roads/buildings/land-use/POIs reflect an exact OpenStreetMap snapshot; cycling infrastructure reflects an exact İBB snapshot. Never read this as a live 2026 estimate."
      layers={layers}
      districts={districtNames}
      initialGrid={grid}
      initialDistrict={district}
      panelDescription={copy.description}
      headerAction={<MethodologyDrawer rows={rows} triggerLabel="View full methodology" />}
    />
  );
}
