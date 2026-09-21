export function MapLegend({
  title,
  colorMap,
  labelMap,
  order,
}: {
  title: string;
  colorMap: Record<string, string>;
  labelMap?: Record<string, string>;
  order?: string[];
}) {
  const keys = order ?? Object.keys(colorMap);
  return (
    <div className="rounded-xl border border-o3-card bg-o3-bg-primary/90 backdrop-blur px-4 py-3 text-xs max-w-[240px]">
      <div className="text-o3-text-secondary uppercase tracking-wider text-[10px] font-medium mb-2">{title}</div>
      <ul className="flex flex-col gap-1.5">
        {keys.map((key) => (
          <li key={key} className="flex items-center gap-2 text-o3-text-primary">
            <span className="w-3 h-3 rounded-sm shrink-0" style={{ background: colorMap[key] }} aria-hidden />
            <span>{labelMap?.[key] ?? key}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
