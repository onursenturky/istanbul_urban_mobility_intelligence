"use client";

import { useState } from "react";

export interface MethodologyRow {
  layer: string;
  data_source: string;
  snapshot_year: string;
  spatial_resolution: string;
  processing_method: string;
  known_limitations: string;
  appropriate_interpretation: string;
}

export function MethodologyDrawer({ rows, triggerLabel = "Methodology" }: { rows: MethodologyRow[]; triggerLabel?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="text-xs text-o3-green hover:text-o3-accent transition-colors underline underline-offset-2"
      >
        {triggerLabel}
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <div className="relative w-full max-w-md h-full bg-o3-bg-primary border-l border-o3-card-strong overflow-y-auto o3-scrollbar p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-o3-text-primary font-semibold text-lg">Methodology &amp; data provenance</h3>
              <button onClick={() => setOpen(false)} className="text-o3-text-secondary hover:text-o3-text-primary" aria-label="Close">
                ✕
              </button>
            </div>
            <div className="flex flex-col gap-5">
              {rows.map((r) => (
                <div key={r.layer} className="border-t border-o3-card pt-4 first:border-t-0 first:pt-0">
                  <div className="text-o3-accent text-sm font-medium">{r.layer}</div>
                  <div className="text-o3-text-primary text-sm mt-1">{r.data_source}</div>
                  <div className="text-o3-text-secondary text-xs mt-1">
                    Snapshot: {r.snapshot_year} &middot; Resolution: {r.spatial_resolution}
                  </div>
                  <p className="text-o3-text-secondary text-xs mt-2">{r.processing_method}</p>
                  <p className="text-o3-text-secondary text-xs mt-2">
                    <span className="text-o3-text-primary">Limitations: </span>
                    {r.known_limitations}
                  </p>
                  <p className="text-o3-text-secondary text-xs mt-2">
                    <span className="text-o3-text-primary">Interpretation: </span>
                    {r.appropriate_interpretation}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
