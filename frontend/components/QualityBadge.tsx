import { confidenceClass } from "@/lib/labels";

export function QualityBadge({
  walkingQuality,
  cyclingQuality,
  transitDataQuality,
}: {
  walkingQuality: string;
  cyclingQuality: string;
  transitDataQuality: string;
}) {
  const c = confidenceClass(walkingQuality, cyclingQuality, transitDataQuality);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium"
      style={{ background: `${c.color}22`, color: c.color, border: `1px solid ${c.color}55` }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: c.color }} aria-hidden />
      {c.label}
    </span>
  );
}
