import type { GridAttributes } from "@/types/data";

/**
 * Phase 14 data-delivery layer: replaces the old single-fetch grid_map.geojson (22.6MB, every
 * analytical field, for every page) and grid_attributes.json (27MB, fetched in full on first
 * cell click) with three small, independently-cacheable pieces -- see
 * docs/map_delivery_decision.md and docs/production_architecture.md:
 *   1. base geometry (grid_id + district + geometry only) -- one fetch per session, shared by
 *      every exploration page via the module-level cache below.
 *   2. per-field layer lookups ({grid_id: value}) -- fetched only for fields a page actually
 *      colors by, cached per field so switching back to an already-seen layer is instant.
 *   3. per-district detail chunks -- fetched only for the ONE district containing the selected
 *      cell, cached per district.
 * No analytical value is recomputed here; every value is looked up verbatim from the frozen
 * source files prepared by data/prepare_frontend_data.py.
 */

export interface GridFeatureProperties {
  grid_id: string;
  district: string;
  [field: string]: string | number | boolean | null;
}

export type GridFeatureCollection = GeoJSON.FeatureCollection<GeoJSON.Geometry, GridFeatureProperties>;

let baseGeometryCache: GridFeatureCollection | null = null;
let baseGeometryInflight: Promise<GridFeatureCollection> | null = null;

/** Fetched once per session; every exploration page shares this same cached copy. */
export async function fetchBaseGeometry(): Promise<GridFeatureCollection> {
  if (baseGeometryCache) return baseGeometryCache;
  if (!baseGeometryInflight) {
    baseGeometryInflight = fetch("/data/base/grid_geometry.json")
      .then((r) => r.json())
      .then((data: GridFeatureCollection) => {
        baseGeometryCache = data;
        return data;
      });
  }
  return baseGeometryInflight;
}

type LayerLookup = Record<string, string | number | boolean | null>;

const layerCache = new Map<string, LayerLookup>();
const layerInflight = new Map<string, Promise<LayerLookup>>();

/** Fetched once per field, ever; a page with 2-3 layer options only pays for the ones it colors by. */
export async function fetchLayerLookup(field: string): Promise<LayerLookup> {
  const cached = layerCache.get(field);
  if (cached) return cached;
  let inflight = layerInflight.get(field);
  if (!inflight) {
    inflight = fetch(`/data/layers/${field}.json`)
      .then((r) => r.json())
      .then((data: LayerLookup) => {
        layerCache.set(field, data);
        return data;
      });
    layerInflight.set(field, inflight);
  }
  return inflight;
}

let districtIndexCache: Record<string, string> | null = null;
let districtIndexInflight: Promise<Record<string, string>> | null = null;

/** Tiny grid_id -> district map, so a shared `?grid=` URL can resolve which detail chunk to
 * fetch even without a matching `?district=` (or if the two ever disagree). */
export async function fetchGridDistrictIndex(): Promise<Record<string, string>> {
  if (districtIndexCache) return districtIndexCache;
  if (!districtIndexInflight) {
    districtIndexInflight = fetch("/data/details/_grid_district_index.json")
      .then((r) => r.json())
      .then((data: Record<string, string>) => {
        districtIndexCache = data;
        return data;
      });
  }
  return districtIndexInflight;
}

export type GridDetailRecord = Omit<GridAttributes, "district">;
export type GridDetailLookup = Record<string, GridDetailRecord>;

const districtDetailCache = new Map<string, GridDetailLookup>();
const districtDetailInflight = new Map<string, Promise<GridDetailLookup>>();

/** Fetched once per district; the Grid Intelligence Card calls this on demand when a cell in
 * that district is selected, instead of the old 27MB bulk grid_attributes.json fetch. */
export async function fetchDistrictDetails(district: string): Promise<GridDetailLookup> {
  const cached = districtDetailCache.get(district);
  if (cached) return cached;
  let inflight = districtDetailInflight.get(district);
  if (!inflight) {
    inflight = fetch(`/data/details/${encodeURIComponent(district)}.json`)
      .then((r) => r.json())
      .then((data: GridDetailLookup) => {
        districtDetailCache.set(district, data);
        return data;
      });
    districtDetailInflight.set(district, inflight);
  }
  return inflight;
}
