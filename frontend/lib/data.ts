import "server-only";
import { readFile } from "fs/promises";
import path from "path";
import type {
  DistrictSummaryRow,
  DistrictProfile,
  ClaimRecord,
  CaseStudy,
  KpiRegistryRow,
} from "@/types/data";

const DATA_DIR = path.join(process.cwd(), "public", "data");

async function loadJson<T>(filename: string): Promise<T> {
  const raw = await readFile(path.join(DATA_DIR, filename), "utf-8");
  return JSON.parse(raw) as T;
}

export const getDistrictSummary = () => loadJson<DistrictSummaryRow[]>("district_summary.json");
export const getDistrictProfiles = () => loadJson<DistrictProfile[]>("district_profiles.json");
export const getClaimsRegistry = () => loadJson<ClaimRecord[]>("claims_registry.json");
export const getCaseStudies = () => loadJson<{ cases: CaseStudy[]; selection_method: string }>("case_studies.json");
export const getKpiRegistry = () => loadJson<KpiRegistryRow[]>("kpi_registry.json");
export const getMapLayerRegistry = () => loadJson<Record<string, unknown>[]>("map_layer_registry.json");
export const getChartRegistry = () => loadJson<Record<string, unknown>[]>("chart_registry.json");
export const getMethodologyRegistry = () => loadJson<Record<string, unknown>[]>("methodology_registry.json");
export const getHeadlineKpis = () => loadJson<{ headline_findings: Record<string, unknown>[] }>("headline_kpis.json");
export const getFrameworkFindings = () => loadJson<Record<string, string>>("framework_findings.json");
export const getFrameworkArchitecture = () => loadJson<Record<string, unknown>>("framework_architecture.json");
export const getDashboardIA = () => loadJson<{ pages: Record<string, unknown>[] }>("dashboard_information_architecture.json");
export const getFilterSpec = () => loadJson<Record<string, unknown>>("dashboard_filter_spec.json");

/**
 * Claim-safety contract (Phase 13 Section 26): the ONLY sanctioned way to
 * surface a headline analytical statement in the UI. Never hand-write a
 * claim's wording elsewhere -- always resolve it through this function.
 */
export async function getClaim(claimId: string): Promise<ClaimRecord | undefined> {
  const claims = await getClaimsRegistry();
  return claims.find((c) => c.claim_id === claimId);
}
