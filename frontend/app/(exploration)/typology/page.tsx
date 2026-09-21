import { getDistrictSummary, getClaim } from "@/lib/data";
import { PageMapExplorer, type MapLayerConfig } from "@/components/PageMapExplorer";
import { fieldColorMaps, fieldLabelMaps } from "@/lib/mapColors";
import { pageCopy } from "@/lib/terminology";

const layers: MapLayerConfig[] = [
  {
    value: "typology",
    label: "Urban typology",
    field: "typology_cluster",
    colorMap: fieldColorMaps.typology_cluster,
    labelMap: fieldLabelMaps.typology_cluster,
    legendOrder: ["0", "1", "2", "3", "4"],
    legendTitle: "Urban mobility typology",
  },
];

export default async function TypologyPage({ searchParams }: { searchParams: Promise<{ grid?: string; district?: string }> }) {
  const { grid, district } = await searchParams;
  const [districts, c01] = await Promise.all([getDistrictSummary(), getClaim("C01")]);
  const districtNames = districts.map((d) => d.district);
  const copy = pageCopy.typology;

  return (
    <PageMapExplorer
      title={copy.title}
      question={copy.question}
      infoTooltip="Five frozen clusters, built from ~94 spatial indicators, describe recurring urban regimes. Clusters are descriptive, not ranked, and never entered any routing or accessibility computation."
      layers={layers}
      districts={districtNames}
      initialGrid={grid}
      initialDistrict={district}
      panelDescription={copy.description}
      panelKpis={c01 ? [{ label: "Walking access to everyday essentials", claim: c01 }] : []}
    />
  );
}
