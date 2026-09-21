"use client";

import { useEffect, useRef, useState, useCallback } from "react";
// MapLibre 6.x ships ESM-only with NAMED exports (no default export) -- named imports
// throughout, not `import maplibregl from ...` (Phase 14 dependency upgrade, 4.5.0 -> 6.10.0
// to resolve a critical XSS advisory, see qa/security_dependency_audit.md).
import { Map as MLMap, NavigationControl, LngLatBounds, setWorkerUrl, type MapLayerMouseEvent, type GeoJSONSource } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { buildMatchExpression, UNCERTAIN_FALLBACK } from "@/lib/mapColors";
import { fetchBaseGeometry, fetchLayerLookup, type GridFeatureCollection } from "@/lib/mapDataCache";

// ROOT CAUSE of the "map never finishes loading, tiles stuck at state:'loading' forever" bug
// (found via source-level inspection of node_modules/maplibre-gl/dist/maplibre-gl.mjs, and
// confirmed by a real, non-automated browser also getting stuck -- this is a genuine bug, not a
// test-tool artifact): MapLibre 6.x's tile parsing runs in a separate Worker, whose script URL
// it computes at runtime as `new URL('./maplibre-gl-worker.mjs', import.meta.url)`. Once Next's
// webpack bundles maplibre-gl.mjs into an app chunk, `import.meta.url` no longer points at the
// real npm package location -- it resolves relative to the bundled chunk's own URL, and
// webpack's static Worker-asset analysis (which needs a literal, directly-inlined
// `new URL(...)` expression to detect and emit a worker file) can't see through the small
// helper function MapLibre wraps this computation in, so `maplibre-gl-worker.mjs` is never
// copied into `.next/static/` at all. The resulting Worker is constructed against a URL that
// simply doesn't exist: the Worker object itself never throws, but no script ever executes
// inside it, so every tile-load message posted to it (`postMessage`) is dispatched into the
// void and never answered -- exactly the observed symptom (dispatcher actor created, tasks
// posted, zero responses, no error event). Fix: `setWorkerUrl()` is MapLibre's own public,
// documented API for exactly this bundler scenario -- point it at a copy of the worker file
// served from a STABLE, non-webpack-processed location (public/maplibre-gl-worker.mjs, copied
// from node_modules/maplibre-gl/dist/ -- re-copy after any maplibre-gl version bump). Must be
// called before the first `new MLMap(...)`.
if (typeof window !== "undefined") {
  setWorkerUrl("/maplibre-gl-worker.mjs");
}

// Free, no-API-key vector basemap (CARTO Dark Matter). Attribution required and shown via the
// MapLibre attribution control (kept enabled below). https://carto.com/basemaps
const BASEMAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const ISTANBUL_BOUNDS: [[number, number], [number, number]] = [
  [28.35, 40.75],
  [29.75, 41.35],
];

export interface MapViewProps {
  activeField: string;
  colorMap: Record<string, string>;
  selectedGridId?: string | null;
  onSelectGrid?: (gridId: string | null) => void;
  onHoverGrid?: (gridId: string | null) => void;
  fitToDistrict?: string | null; // district name, or null/undefined for full city
  districtField?: string; // property name holding the district on each feature
  resetToken?: number; // bump to force a reset-view
}

export function MapView({
  activeField,
  colorMap,
  selectedGridId,
  onSelectGrid,
  onHoverGrid,
  fitToDistrict,
  districtField = "district",
  resetToken,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MLMap | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const [loaded, setLoaded] = useState(false);
  const hoveredIdRef = useRef<string | number | null>(null);
  // Working copy of the base geometry + whichever layer fields have been merged in so far
  // (Phase 14 geometry/layers split -- see lib/mapDataCache.ts). Mutated in place and pushed to
  // the map via source.setData() rather than re-fetched/re-added, so switching between a page's
  // 1-3 layer options after the first is instant once each field has been fetched once.
  const geojsonRef = useRef<GridFeatureCollection | null>(null);
  const mergedFieldsRef = useRef<Set<string>>(new Set());

  // Initialize map once.
  //
  // ROOT CAUSE of the "map sometimes doesn't render until resize/click" bug (Phase 13.1):
  // MapLibre's constructor reads its container's clientWidth/clientHeight exactly ONCE, at
  // construction time, to size the internal canvas. On a fresh client-side route transition
  // (a full remount of this component -- Next.js App Router unmounts/remounts the whole page
  // tree between distinct routes) the container's final layout is not always settled the
  // instant this effect runs: Outfit's `display: "swap"` can still reflow text above the map
  // a frame later, and the flex/absolute-inset-0 parent chain can report a transient 0x0 or
  // stale size on the very first paint. When that race loses, MapLibre bakes in a wrong/zero
  // canvas size and never recovers on its own -- exactly the "resize the window and it
  // suddenly appears" symptom. A ResizeObserver on the container, kept alive for the map's
  // entire lifetime (not a one-shot timeout), is the standard, deterministic fix: it fires
  // once immediately with the current size and again on every subsequent layout change, so
  // `map.resize()` is called whenever the container's real size becomes known -- no polling,
  // no arbitrary delay.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new MLMap({
      container: containerRef.current,
      style: BASEMAP_STYLE,
      bounds: ISTANBUL_BOUNDS,
      attributionControl: { compact: true },
    });
    // bottom-right, not top-right: the page's own DistrictSelector overlay occupies top-right.
    map.addControl(new NavigationControl({ showCompass: false }), "bottom-right");
    mapRef.current = map;
    // Dev-only debug hook (never runs in production) -- used to diagnose the Phase 13.1
    // rendering bugs via live DOM/style inspection; kept for future troubleshooting.
    if (process.env.NODE_ENV !== "production") (window as unknown as { __debugMap?: unknown }).__debugMap = map;

    const resizeObserver = new ResizeObserver(() => {
      map.resize();
    });
    resizeObserver.observe(containerRef.current);
    resizeObserverRef.current = resizeObserver;

    // Surfaces a genuine basemap/style load failure (bad network, blocked tile host) instead of
    // leaving the loading overlay spinning forever with no diagnosable trace (Phase 14 Section 29).
    map.on("error", (e) => {
      // eslint-disable-next-line no-console
      console.error("Map failed to load a resource:", e?.error ?? e);
    });

    map.on("load", async () => {
      map.resize(); // safety net in case the observer's first callback fired before the style loaded
      // Fetch the small base geometry (grid_id + district + geometry only) plus the ONE layer
      // lookup this page needs to render its initial color, and merge the two client-side --
      // never the old 22.6MB grid_map.geojson that carried every page's fields at once (Phase
      // 14 Section 5-6, see docs/map_delivery_decision.md).
      const [base, lookup] = await Promise.all([fetchBaseGeometry(), fetchLayerLookup(activeField)]);
      const geojson: GridFeatureCollection = {
        type: "FeatureCollection",
        features: base.features.map((f) => ({
          ...f,
          properties: { ...f.properties, [activeField]: lookup[f.properties.grid_id] ?? null },
        })),
      };
      geojsonRef.current = geojson;
      mergedFieldsRef.current = new Set([activeField]);

      map.addSource("grid", {
        type: "geojson",
        data: geojson,
        promoteId: "grid_id",
      });

      map.addLayer({
        id: "grid-fill",
        type: "fill",
        source: "grid",
        paint: {
          "fill-color": UNCERTAIN_FALLBACK,
          "fill-opacity": [
            "case",
            ["boolean", ["feature-state", "hover"], false],
            0.92,
            ["boolean", ["feature-state", "selected"], false],
            0.95,
            0.72,
          ],
        },
      });

      map.addLayer({
        id: "grid-outline",
        type: "line",
        source: "grid",
        paint: {
          "line-color": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            "#B2F093",
            "rgba(17,51,6,0.35)",
          ],
          "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 2.5, 0.4],
        },
      });

      setLoaded(true);
    });

    return () => {
      resizeObserverRef.current?.disconnect();
      resizeObserverRef.current = null;
      // map.remove() must run SYNCHRONOUSLY (not deferred until 'load') so that at most one
      // live MapLibre instance is ever attached to `containerRef.current` -- React 18
      // StrictMode invokes this effect twice against the SAME container DOM node in dev
      // (mount -> cleanup -> mount again, no re-render in between), and an earlier version of
      // this cleanup deferred removal until the style finished loading, which let a second
      // instance be constructed into the container while the first was still alive: two
      // instances briefly shared one container, and the "recolor" effect's setPaintProperty
      // calls landed on whichever instance `mapRef.current` happened to point to, which was
      // not reliably the one whose canvas ended up visible -- the map rendered at the right
      // size but its analytical color layer silently never applied.
      //
      // Synchronous removal fixes that, but exposes a SECOND, compounding bug: MapLibre's own
      // map.remove() can itself throw a benign upstream AbortError synchronously when called
      // while the style is still mid-load (an AbortController signal.reason quirk inside
      // MapLibre). Because that throw happened INSIDE this cleanup, `mapRef.current = null`
      // (previously written just after the remove() call) never executed on that path -- so
      // the NEXT mount's effect saw a stale non-null mapRef and bailed out via its own
      // `if (mapRef.current) return;` guard, silently skipping map creation entirely. That is
      // the "map sometimes just never appears at all" failure mode. Fix: our own ref/observer
      // bookkeeping must be exception-safe regardless of what MapLibre throws, via try/finally.
      try {
        map.remove();
      } finally {
        mapRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load (once per field, ever) and merge in whichever layer is now active, then recolor.
  // A page toggling between its own 1-3 layer options only pays the fetch cost the first time
  // it visits each one; every subsequent toggle re-merges from the in-memory cache in
  // lib/mapDataCache.ts and repaints instantly.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    let cancelled = false;
    (async () => {
      const geojson = geojsonRef.current;
      if (geojson && !mergedFieldsRef.current.has(activeField)) {
        const lookup = await fetchLayerLookup(activeField);
        if (cancelled) return;
        for (const feature of geojson.features) {
          feature.properties[activeField] = lookup[feature.properties.grid_id] ?? null;
        }
        mergedFieldsRef.current.add(activeField);
        const source = map.getSource("grid") as GeoJSONSource | undefined;
        source?.setData(geojson);
      }
      if (cancelled) return;
      const expr = buildMatchExpression(activeField, colorMap);
      if (map.getLayer("grid-fill")) {
        map.setPaintProperty("grid-fill", "fill-color", expr as never);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeField, colorMap, loaded]);

  // Hover + click interaction.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;

    const setHover = (id: string | number | null) => {
      if (hoveredIdRef.current !== null) {
        map.setFeatureState({ source: "grid", id: hoveredIdRef.current }, { hover: false });
      }
      hoveredIdRef.current = id;
      if (id !== null) map.setFeatureState({ source: "grid", id }, { hover: true });
    };

    const onMouseMove = (e: MapLayerMouseEvent) => {
      const f = e.features?.[0];
      if (f) {
        map.getCanvas().style.cursor = "pointer";
        setHover(f.id as string);
        onHoverGrid?.(f.properties?.grid_id ?? null);
      }
    };
    const onMouseLeave = () => {
      map.getCanvas().style.cursor = "";
      setHover(null);
      onHoverGrid?.(null);
    };
    const onClick = (e: MapLayerMouseEvent) => {
      const f = e.features?.[0];
      onSelectGrid?.(f ? (f.properties?.grid_id ?? null) : null);
    };

    map.on("mousemove", "grid-fill", onMouseMove);
    map.on("mouseleave", "grid-fill", onMouseLeave);
    map.on("click", "grid-fill", onClick);
    return () => {
      map.off("mousemove", "grid-fill", onMouseMove);
      map.off("mouseleave", "grid-fill", onMouseLeave);
      map.off("click", "grid-fill", onClick);
    };
  }, [loaded, onHoverGrid, onSelectGrid]);

  // Selected-state highlight.
  const prevSelectedRef = useRef<string | null>(null);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    if (prevSelectedRef.current) {
      map.setFeatureState({ source: "grid", id: prevSelectedRef.current }, { selected: false });
    }
    if (selectedGridId) {
      map.setFeatureState({ source: "grid", id: selectedGridId }, { selected: true });
    }
    prevSelectedRef.current = selectedGridId ?? null;
  }, [selectedGridId, loaded]);

  // District fit-bounds.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    if (!fitToDistrict) {
      map.fitBounds(ISTANBUL_BOUNDS, { padding: 24, duration: 600 });
      return;
    }
    const src = map.getSource("grid");
    if (!src) return;
    const features = map.querySourceFeatures("grid", { filter: ["==", ["get", districtField], fitToDistrict] });
    if (!features.length) return;
    const bounds = new LngLatBounds();
    for (const f of features) {
      const geom = f.geometry;
      if (geom.type === "Polygon") {
        for (const ring of geom.coordinates) for (const c of ring) bounds.extend(c as [number, number]);
      } else if (geom.type === "MultiPolygon") {
        for (const poly of geom.coordinates) for (const ring of poly) for (const c of ring) bounds.extend(c as [number, number]);
      }
    }
    if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 40, duration: 600 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitToDistrict, loaded]);

  // Reset view.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded || resetToken === undefined) return;
    map.fitBounds(ISTANBUL_BOUNDS, { padding: 24, duration: 600 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetToken]);

  const resetView = useCallback(() => {
    mapRef.current?.fitBounds(ISTANBUL_BOUNDS, { padding: 24, duration: 600 });
  }, []);

  return (
    <div className="absolute inset-0">
      {/*
        Positioned via an INLINE style, not Tailwind's `absolute inset-0` utility classes.
        Root cause (found via live DOM/computed-style inspection): MapLibre appends its own
        `maplibregl-map` class to this exact element after construction, and MapLibre's own
        stylesheet (maplibre-gl.css, imported above) declares `.maplibregl-map { position:
        relative }`. That class-selector rule has the SAME specificity as Tailwind's
        `.absolute { position: absolute }` utility, so whichever stylesheet happens to be
        injected into the page later in the cascade silently wins -- and when MapLibre's CSS
        wins, `position: relative` turns `inset-0` from "stretch to fill the parent" into a
        no-op offset on a box with no intrinsic height, collapsing this container to 0px tall
        (while its own parent and children report correct, non-zero sizes -- confirmed by
        walking the DOM chain). An inline style always wins over any class-based rule
        regardless of stylesheet order, which is why this is used here instead of className.
      */}
      <div
        ref={containerRef}
        style={{ position: "absolute", inset: 0 }}
        className="rounded-2xl overflow-hidden"
        role="application"
        aria-label="Istanbul accessibility map"
      />
      <button
        onClick={resetView}
        className="absolute bottom-16 right-3 text-xs bg-o3-bg-primary/90 border border-o3-card-strong text-o3-text-primary rounded-full px-3 py-1.5 hover:bg-o3-card-hover transition-colors z-10"
      >
        Reset view
      </button>
      {!loaded && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-o3-bg-deep/85 rounded-2xl backdrop-blur-sm">
          <span className="w-8 h-8 rounded-full border-2 border-o3-card-strong border-t-o3-accent animate-spin" aria-hidden />
          <div className="text-center">
            <p className="text-o3-text-primary text-sm font-medium">Loading the Istanbul accessibility map</p>
            <p className="text-o3-text-secondary text-xs mt-1">Preparing 22,322 spatial cells…</p>
          </div>
        </div>
      )}
    </div>
  );
}
