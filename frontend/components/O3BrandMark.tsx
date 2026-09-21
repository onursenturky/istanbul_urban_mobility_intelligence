export function O3BrandMark({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <span className="text-o3-text-secondary text-xs tracking-wide">
        by <span className="text-o3-text-primary font-medium">O3 Sustainability</span>
      </span>
    );
  }
  return (
    <div className="flex flex-col leading-tight">
      <span className="text-o3-text-primary font-semibold text-sm">Istanbul</span>
      <span className="text-o3-text-secondary text-[11px] tracking-wide">Urban Mobility Intelligence</span>
    </div>
  );
}
