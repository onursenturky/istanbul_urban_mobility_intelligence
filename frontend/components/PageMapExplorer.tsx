"use client";

import { useState, useMemo } from "react";
import { MapView } from "@/components/MapView";
import { MapLegend } from "@/components/MapLegend";
import { LayerSelector, type LayerOption } from "@/components/LayerSelector";
import { DistrictSelector } from "@/components/DistrictSelector";
import { GridIntelligenceCard } from "@/components/GridIntelligenceCard";
import { PanelOverview } from "@/components/PanelOverview";
import { InfoTooltip } from "@/components/InfoTooltip";
import type { ClaimRecord } from "@/types/data";

export interface MapLayerConfig extends LayerOption {
  field: string;
  colorMap: Record<string, string>;
  labelMap: Record<string, string>;
  legendOrder?: string[];
  legendTitle: string;
}

/**
 * Map-first EXPLORATION page composition (Phase 13.1 desktop-first correction).
 *
 * Desktop: compact header (title + one-line question, ~24-32px title per spec, not a hero) +
 * a map that fills essentially the entire remaining space, with layer/district controls and
 * the legend as small overlays ON the map (never a separate row stealing vertical space from
 * it) + a persistent 360px right-hand panel (Grid Intelligence Card when a cell is selected,
 * otherwise the page's own question + headline KPIs via PanelOverview -- the panel is never
 * empty/wasted space).
 *
 * Mobile (<768px, unchanged from Phase 13): the panel becomes a fixed bottom sheet that only
 * appears once a cell is selected; there is no permanently-reserved panel column.
 */
export function PageMapExplorer({
  title,
  question,
  infoTooltip,
  layers,
  districts,
  initialGrid,
  initialDistrict,
  panelKpis,
  panelDescription,
  headerAction,
}: {
  title: string;
  question: string;
  infoTooltip?: React.ReactNode;
  layers: MapLayerConfig[];
  districts: string[];
  initialGrid?: string | null;
  initialDistrict?: string | null;
  panelKpis?: { label: string; claim: ClaimRecord }[];
  panelDescription?: string;
  headerAction?: React.ReactNode;
}) {
  const [activeLayerValue, setActiveLayerValue] = useState(layers[0].value);
  const [district, setDistrict] = useState<string | null>(initialDistrict ?? null);
  const [selectedGrid, setSelectedGrid] = useState<string | null>(initialGrid ?? null);

  const activeLayer = useMemo(() => layers.find((l) => l.value === activeLayerValue) ?? layers[0], [layers, activeLayerValue]);

  return (
    <div className="absolute inset-0 flex flex-col">
      <header className="shrink-0 px-5 md:px-6 py-3 md:py-4 border-b border-o3-card flex items-baseline justify-between gap-3 flex-wrap">
        <div className="flex items-baseline gap-2 flex-wrap">
          <h1 className="text-xl md:text-2xl font-semibold text-o3-text-primary">{title}</h1>
          <p className="text-xs md:text-sm text-o3-text-secondary">
            {question}
            {infoTooltip && <InfoTooltip>{infoTooltip}</InfoTooltip>}
          </p>
        </div>
        {headerAction}
      </header>

      <div className="flex-1 min-h-0 flex flex-col md:flex-row">
        <div className="flex-1 min-w-0 min-h-0 relative">
          <MapView
            activeField={activeLayer.field}
            colorMap={activeLayer.colorMap}
            selectedGridId={selectedGrid}
            onSelectGrid={setSelectedGrid}
            fitToDistrict={district}
          />
          <div className="absolute top-3 left-3 z-10 max-w-[calc(100%-2rem)]">
            <LayerSelector options={layers} value={activeLayerValue} onChange={setActiveLayerValue} />
          </div>
          <div className="absolute top-3 right-3 z-10">
            <DistrictSelector districts={districts} value={district} onChange={setDistrict} />
          </div>
          <div className="absolute bottom-3 left-3 z-10">
            <MapLegend title={activeLayer.legendTitle} colorMap={activeLayer.colorMap} labelMap={activeLayer.labelMap} order={activeLayer.legendOrder} />
          </div>
        </div>

        {/* Desktop: persistent side panel (320-400px), map stays visible beside it. */}
        <aside className="hidden md:block md:w-[360px] md:shrink-0 border-l border-o3-card">
          {selectedGrid ? (
            <GridIntelligenceCard gridId={selectedGrid} onClose={() => setSelectedGrid(null)} />
          ) : (
            <PanelOverview question={question} description={panelDescription ?? ""} kpis={panelKpis ?? []} />
          )}
        </aside>
      </div>

      {/* Mobile: fixed bottom sheet, only when a cell is selected. */}
      {selectedGrid && (
        <div className="md:hidden fixed inset-x-0 bottom-0 z-30 max-h-[70vh] rounded-t-2xl border border-o3-card shadow-2xl overflow-hidden">
          <GridIntelligenceCard gridId={selectedGrid} onClose={() => setSelectedGrid(null)} />
        </div>
      )}
    </div>
  );
}
