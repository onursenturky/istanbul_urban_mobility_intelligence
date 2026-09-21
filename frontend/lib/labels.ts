/**
 * Human-readable label translation for every analytical enum surfaced in
 * the UI. Raw enum values are kept internally (for filtering, color
 * mapping, and linking back to the claims/methodology registries) but are
 * never shown to the user as primary text -- per Phase 13 Section 13.
 */
import { semanticColors } from "./theme";

export const activeMobilityInterventionLabel: Record<string, string> = {
  WALKING_SUFFICIENT: "Walking access already complete",
  CYCLING_CLOSES_EVERYDAY_GAP: "Cycling closes the gap",
  CYCLING_CLOSES_TRANSIT_GAP: "Cycling closes a transit-access gap",
  CYCLING_CLOSES_BOTH: "Cycling closes both gaps",
  CYCLING_PARTIAL_GAIN: "Cycling partially closes the gap",
  CYCLING_DOES_NOT_CLOSE_GAP: "Gap remains",
  QUALITY_UNCERTAIN: "Evidence uncertain",
};

export const cyclingGapClosureLabel: Record<string, string> = {
  NOT_APPLICABLE_NO_GAP: "No walking gap to close",
  FULLY_CLOSED_BY_CYCLING: "Cycling fully closes the gap",
  PARTIALLY_CLOSED_BY_CYCLING: "Cycling partially closes the gap",
  UNCHANGED_BY_CYCLING: "Cycling does not close the gap",
  CYCLING_RESULT_UNCERTAIN: "Evidence uncertain",
};

export const everydayGapTypeLabel: Record<string, string> = {
  NO_REQUIRED_GAP: "No mapped gap",
  FOOD_GAP: "Food access gap",
  HEALTHCARE_GAP: "Healthcare access gap",
  EDUCATION_GAP: "Education access gap",
  FOOD_HEALTHCARE_GAP: "Food + Healthcare gap",
  FOOD_EDUCATION_GAP: "Food + Education gap",
  HEALTHCARE_EDUCATION_GAP: "Healthcare + Education gap",
  ALL_REQUIRED_GAP: "Multiple-need gap (all three)",
  UNKNOWN_OR_QUALITY_LIMITED: "Evidence uncertain",
};

export const transitGapTypeLabel: Record<string, string> = {
  NO_TRANSIT_ACCESS_GAP: "No mapped transit-access gap",
  GENERAL_ACCESS_GAP: "General transit access gap",
  FIXED_GUIDEWAY_ACCESS_GAP: "Fixed-guideway access gap",
  BOTH_TRANSIT_ACCESS_GAPS: "General + fixed-guideway gap",
  TRANSIT_DATA_UNCERTAIN: "Data insufficient for transit interpretation",
  NETWORK_QUALITY_UNCERTAIN: "Network evidence uncertain",
};

export const multiDomainPatternLabel: Record<string, string> = {
  A_BROAD_ACCESS: "Broad access (walking + transit)",
  B_EVERYDAY_NEEDS_GAP_ONLY: "Everyday-needs gap only",
  C_TRANSIT_ACCESS_GAP_ONLY: "Transit-access gap only",
  D_BOTH_ACCESS_GAPS: "Both everyday-needs and transit gaps",
  E_DATA_OR_NETWORK_UNCERTAIN: "Evidence uncertain",
};

export const qualityFlagLabel: Record<string, string> = {
  RELIABLE: "Reliable evidence",
  RELIABLE_SEPARATE_COMPONENT: "Reliable evidence (separate network area)",
  QUESTIONABLE_ANCHOR: "Network limitation",
  SMALL_COMPONENT_CAUTION: "Network limitation",
  KNOWN_NETWORK_LIMITATION_ADALAR: "Known special case (Adalar)",
};

export const transitDataQualityLabel: Record<string, string> = {
  GOOD_COVERAGE: "Good transit-feed coverage",
  USABLE_WITH_LIMITATION: "Usable with limitation",
  SUSPECT_FEED_COVERAGE: "Data insufficient for transit interpretation",
  NO_FEED_COVERAGE: "Data insufficient for transit interpretation",
};

/** Combined data-confidence classification used by the Data Confidence layer (Section 22). */
export function confidenceClass(walkingQuality: string, cyclingQuality: string, transitDataQuality: string): {
  key: "RELIABLE" | "NETWORK_LIMITATION" | "TRANSIT_DATA_LIMITATION" | "MULTIPLE_LIMITATIONS" | "KNOWN_SPECIAL_CASE";
  label: string;
  color: string;
} {
  const isAdalar = walkingQuality === "KNOWN_NETWORK_LIMITATION_ADALAR" || cyclingQuality === "KNOWN_NETWORK_LIMITATION_ADALAR";
  const networkLimited = !["RELIABLE", "RELIABLE_SEPARATE_COMPONENT"].includes(walkingQuality) ||
    !["RELIABLE", "RELIABLE_SEPARATE_COMPONENT"].includes(cyclingQuality);
  const transitLimited = !["GOOD_COVERAGE"].includes(transitDataQuality);

  if (isAdalar) return { key: "KNOWN_SPECIAL_CASE", label: "Known special case (Adalar)", color: semanticColors.knownLimit };
  if (networkLimited && transitLimited) return { key: "MULTIPLE_LIMITATIONS", label: "Multiple limitations", color: semanticColors.uncertain };
  if (networkLimited) return { key: "NETWORK_LIMITATION", label: "Network limitation", color: semanticColors.uncertain };
  if (transitLimited) return { key: "TRANSIT_DATA_LIMITATION", label: "Data insufficient for transit interpretation", color: semanticColors.transitLimit };
  return { key: "RELIABLE", label: "Reliable evidence", color: semanticColors.positive };
}

export function formatMinutes(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "Not reachable within 15 min";
  return `${value.toFixed(1)} min`;
}

export function formatPopulation(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return Math.round(value).toString();
}
