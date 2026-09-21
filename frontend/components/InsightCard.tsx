export function InsightCard({
  eyebrow,
  title,
  children,
  highlight = false,
}: {
  eyebrow?: string;
  title: string;
  children: React.ReactNode;
  highlight?: boolean;
}) {
  if (highlight) {
    return (
      <div className="rounded-2xl p-6 md:p-8" style={{ background: "#F1FFE0", color: "#113306" }}>
        {eyebrow && <span className="text-xs uppercase tracking-wider font-semibold opacity-70">{eyebrow}</span>}
        <h3 className="text-xl md:text-2xl font-semibold mt-1 mb-2">{title}</h3>
        <div className="text-sm md:text-base leading-relaxed opacity-90">{children}</div>
      </div>
    );
  }
  return (
    <div className="rounded-2xl border border-o3-card bg-o3-card p-6 md:p-8">
      {eyebrow && <span className="text-xs uppercase tracking-wider font-semibold text-o3-green">{eyebrow}</span>}
      <h3 className="text-xl md:text-2xl font-semibold mt-1 mb-2 text-o3-text-primary">{title}</h3>
      <div className="text-sm md:text-base leading-relaxed text-o3-text-secondary">{children}</div>
    </div>
  );
}
