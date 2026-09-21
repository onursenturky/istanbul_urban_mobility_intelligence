"use client";

export function TimeThresholdControl({
  value,
  onChange,
  options = [5, 10, 15],
}: {
  value: number;
  onChange: (v: number) => void;
  options?: number[];
}) {
  return (
    <div className="inline-flex rounded-full border border-o3-card-strong p-0.5 bg-o3-card text-xs">
      {options.map((opt) => {
        const active = opt === value;
        return (
          <button
            key={opt}
            onClick={() => onChange(opt)}
            className={`px-3 py-1.5 rounded-full transition-colors ${active ? "bg-o3-accent font-medium" : "text-o3-text-secondary hover:text-o3-text-primary"}`}
            style={active ? { color: "#113306" } : undefined}
            aria-pressed={active}
          >
            {opt} min
          </button>
        );
      })}
    </div>
  );
}
