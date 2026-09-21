"use client";

import { useEffect, useState } from "react";
import { fetchDistrictDetails, fetchGridDistrictIndex, type GridDetailRecord } from "@/lib/mapDataCache";

/**
 * Client-side, per-district on-demand loader for a single cell's detail record (Phase 14 --
 * replaces the Phase 13 27MB bulk grid_attributes.json fetch). Resolves the cell's district via
 * the small grid-to-district index (works even if the caller doesn't already know the
 * district), then fetches -- and caches -- only that one district's detail chunk.
 */
export function useGridAttributes(gridId: string | null | undefined) {
  const [data, setData] = useState<GridDetailRecord | null>(null);
  const [district, setDistrict] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!gridId);

  useEffect(() => {
    if (!gridId) {
      setData(null);
      setDistrict(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    (async () => {
      const index = await fetchGridDistrictIndex();
      if (cancelled) return;
      const gridDistrict = index[gridId];
      if (!gridDistrict) {
        setData(null);
        setDistrict(null);
        setLoading(false);
        return;
      }
      const chunk = await fetchDistrictDetails(gridDistrict);
      if (cancelled) return;
      setData(chunk[gridId] ?? null);
      setDistrict(gridDistrict);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [gridId]);

  return { data, district, loading };
}
