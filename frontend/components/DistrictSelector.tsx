"use client";

export function DistrictSelector({
  districts,
  value,
  onChange,
}: {
  districts: string[];
  value: string | null;
  onChange: (district: string | null) => void;
}) {
  const sorted = [...districts].sort((a, b) => a.localeCompare(b, "tr"));
  return (
    <label className="flex flex-col gap-1 text-xs text-o3-text-secondary">
      <span className="uppercase tracking-wider text-[10px] font-medium">District</span>
      <select
        className="bg-o3-card border border-o3-card-strong rounded-lg px-3 py-2 text-sm text-o3-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-o3-accent"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">All districts</option>
        {sorted.map((d) => (
          <option key={d} value={d}>
            {d}
          </option>
        ))}
      </select>
    </label>
  );
}
