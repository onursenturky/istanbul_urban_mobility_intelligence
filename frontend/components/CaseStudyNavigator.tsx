"use client";

import { useRouter } from "next/navigation";
import type { CaseStudy } from "@/types/data";

const CASE_PAGE: Record<string, string> = {
  CASE_1_DENSE_CORE_STRONG_WALKING: "/fifteen-minute",
  CASE_2_DENSE_CYCLING_ADDS_LITTLE: "/cycling-gain",
  CASE_3_CYCLING_FULLY_CLOSES_GAP: "/cycling-gain",
  CASE_4_CYCLING_PARTIALLY_CLOSES_GAP: "/cycling-gain",
  CASE_5_CYCLING_CANNOT_OVERCOME_SPARSITY: "/gaps",
  CASE_6_CYCLING_EXPANDS_FIXED_GUIDEWAY_ACCESS: "/transit",
  CASE_7_EBIKE_ACCESSIBILITY_CONVERGENCE: "/ebike",
  CASE_8_INSUFFICIENT_TRANSIT_DATA: "/transit",
  CASE_9_ADALAR_KNOWN_NETWORK_LIMITATION: "/methods",
};

function humanizeCaseLabel(label: string): string {
  return label
    .replace(/^CASE_\d+_/, "")
    .split("_")
    .map((w) => w[0] + w.slice(1).toLowerCase())
    .join(" ");
}

export function CaseStudyNavigator({ cases }: { cases: CaseStudy[] }) {
  const router = useRouter();
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {cases.map((c) => {
        const page = CASE_PAGE[c.case_label] ?? "/cycling-gain";
        return (
          <button
            key={c.case_label}
            onClick={() => router.push(`${page}?grid=${c.grid_id}&district=${encodeURIComponent(c.district)}`)}
            className="text-left rounded-xl border border-o3-card bg-o3-card hover:bg-o3-card-hover transition-colors p-4 flex flex-col gap-1.5"
          >
            <span className="text-o3-accent text-[11px] uppercase tracking-wider font-medium">{humanizeCaseLabel(c.case_label)}</span>
            <span className="text-o3-text-primary text-sm font-medium">
              {c.district} &middot; {c.grid_id}
            </span>
            <span className="text-o3-text-secondary text-xs line-clamp-3">{c.why_this_case_matters}</span>
          </button>
        );
      })}
    </div>
  );
}
