"use client";

export interface LayerOption {
  value: string;
  label: string;
}

export function LayerSelector({
  options,
  value,
  onChange,
}: {
  options: LayerOption[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Map layer">
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.value)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              active
                ? "bg-o3-accent border-o3-accent font-medium"
                : "bg-transparent border-o3-card-strong text-o3-text-secondary hover:text-o3-text-primary hover:bg-o3-card"
            }`}
            style={active ? { color: "#113306" } : undefined}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
