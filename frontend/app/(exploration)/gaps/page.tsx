import { getDistrictSummary, getClaim } from "@/lib/data";
import { PageMapExplorer, type MapLayerConfig } from "@/components/PageMapExplorer";
import { fieldColorMaps } from "@/lib/mapColors";
import { everydayGapTypeLabel, cyclingGapClosureLabel } from "@/lib/labels";
import { pageCopy } from "@/lib/terminology";

const layers: MapLayerConfig[] = [
  {
    value: "everyday", label: "What's missing", field: "everyday_gap_type",
    colorMap: fieldColorMaps.everyday_gap_type, labelMap: everydayGapTypeLabel,
    legendOrder: ["NO_REQUIRED_GAP", "FOOD_GAP", "HEALTHCARE_GAP", "EDUCATION_GAP", "FOOD_HEALTHCARE_GAP", "FOOD_EDUCATION_GAP", "HEALTHCARE_EDUCATION_GAP", "ALL_REQUIRED_GAP", "UNKNOWN_OR_QUALITY_LIMITED"],
    legendTitle: "Everyday essentials still out of reach (walking)",
  },
  {
    value: "closure", label: "Cycling's effect", field: "cycling_gap_closure",
    colorMap: fieldColorMaps.cycling_gap_closure, labelMap: cyclingGapClosureLabel,
    legendOrder: ["NOT_APPLICABLE_NO_GAP", "FULLY_CLOSED_BY_CYCLING", "PARTIALLY_CLOSED_BY_CYCLING", "UNCHANGED_BY_CYCLING", "CYCLING_RESULT_UNCERTAIN"],
    legendTitle: "Does cycling close the gap?",
  },
];

export default async function GapsPage({ searchParams }: { searchParams: Promise<{ grid?: string; district?: string }> }) {
  const { grid, district } = await searchParams;
  const [districts, c06] = await Promise.all([getDistrictSummary(), getClaim("C06")]);
  const districtNames = districts.map((d) => d.district);
  const copy = pageCopy.gaps;

  return (
    <PageMapExplorer
      title={copy.title}
      question={copy.question}
      infoTooltip={
        <>
          This describes measured, modeled accessibility gaps -- never terms like &ldquo;service desert,&rdquo; &ldquo;mobility poverty,&rdquo;
          or &ldquo;underserved community.&rdquo; Those need evidence this framework does not collect (income, service quality, lived experience).
        </>
      }
      layers={layers}
      districts={districtNames}
      initialGrid={grid}
      initialDistrict={district}
      panelDescription={copy.description}
      panelKpis={c06 ? [{ label: "Remains out of reach even with cycling", claim: c06 }] : []}
    />
  );
}
