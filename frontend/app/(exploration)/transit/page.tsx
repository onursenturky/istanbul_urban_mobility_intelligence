import { getDistrictSummary, getClaim } from "@/lib/data";
import { PageMapExplorer, type MapLayerConfig } from "@/components/PageMapExplorer";
import { fieldColorMaps } from "@/lib/mapColors";
import { transitGapTypeLabel } from "@/lib/labels";
import { semanticColors } from "@/lib/theme";
import { pageCopy, conceptCopy } from "@/lib/terminology";

const gainColorMap: Record<string, string> = { true: semanticColors.gain, false: semanticColors.uncertain };
const gainLabelMap: Record<string, string> = { true: "Cycling brings transit closer", false: "No added reach by cycling" };

const layers: MapLayerConfig[] = [
  {
    value: "gap", label: "Access gap", field: "transit_gap_type",
    colorMap: fieldColorMaps.transit_gap_type, labelMap: transitGapTypeLabel,
    legendOrder: ["NO_TRANSIT_ACCESS_GAP", "GENERAL_ACCESS_GAP", "FIXED_GUIDEWAY_ACCESS_GAP", "BOTH_TRANSIT_ACCESS_GAPS", "TRANSIT_DATA_UNCERTAIN", "NETWORK_QUALITY_UNCERTAIN"],
    legendTitle: `Transit access gap (general + ${conceptCopy.fixedGuidewayAccess.uiTitle.toLowerCase()})`,
  },
  {
    value: "gain", label: "Cycling gain", field: "cycle_only_transit_gain",
    colorMap: gainColorMap, labelMap: gainLabelMap, legendOrder: ["true", "false"],
    legendTitle: "Reachable by cycling, not by walking (10 min)",
  },
];

export default async function TransitPage({ searchParams }: { searchParams: Promise<{ grid?: string; district?: string }> }) {
  const { grid, district } = await searchParams;
  const [districts, c07] = await Promise.all([getDistrictSummary(), getClaim("C07")]);
  const districtNames = districts.map((d) => d.district);
  const copy = pageCopy.transit;

  return (
    <PageMapExplorer
      title={copy.title}
      question={copy.question}
      infoTooltip={
        <>
          Some districts (e.g. Silivri and Çatalca) have zero mapped stops in the underlying transit feeds. This is shown as{" "}
          <strong>&ldquo;Data insufficient for transit interpretation&rdquo;</strong> -- never as &ldquo;no transit access.&rdquo; A missing
          feed is a data-coverage limitation, not evidence that no service exists.
        </>
      }
      layers={layers}
      districts={districtNames}
      initialGrid={grid}
      initialDistrict={district}
      panelDescription={copy.description}
      panelKpis={c07 ? [{ label: "Cycling closes a transit gap (reliable evidence only)", claim: c07 }] : []}
    />
  );
}
