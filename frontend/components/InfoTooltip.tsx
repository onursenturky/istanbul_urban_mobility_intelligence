"use client";

import { useState, useRef, useEffect } from "react";

/**
 * The "ⓘ How this works" pattern (Phase 13.1 Section 23): keeps precise/technical
 * explanations available on demand without them dominating the primary UI copy.
 */
export function InfoTooltip({ label = "How this works", children }: { label?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <span className="relative inline-block" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center justify-center w-4 h-4 rounded-full text-[11px] text-o3-text-secondary border border-o3-card-strong hover:text-o3-text-primary hover:border-o3-accent transition-colors align-middle ml-1"
        aria-label={label}
        aria-expanded={open}
      >
        i
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute z-40 top-6 left-1/2 -translate-x-1/2 w-64 text-xs leading-relaxed text-o3-text-primary bg-o3-bg-primary border border-o3-card-strong rounded-xl p-3 shadow-xl"
        >
          {children}
        </span>
      )}
    </span>
  );
}
