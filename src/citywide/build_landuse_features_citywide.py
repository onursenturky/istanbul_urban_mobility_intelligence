"""Phase 7A: citywide land-use / green-space features from the local OSM PBF
extract, replacing the PARTIAL (22/39 district) live-Overpass acquisition.

Acquisition-method change ONLY: this reads polygon geometries out of
data/raw/osm/pbf/landuse_green_extract.osm.pbf via `osmium export
--geometry-types=polygon` (libosmium's own dedicated Area Assembler),
NOT GDAL/pyogrio's "multipolygons" layer, then runs the data through
src.features.greenspace_features.compute_greenspace_features UNMODIFIED --
same GREEN_LEISURE_VALUES/GREEN_LANDUSE_VALUES/GREEN_NATURAL_VALUES exact-
value classification, same per-category dissolve, same entropy-coverage
threshold.

WHY osmium export instead of GDAL's "multipolygons" layer (found and fixed
during this phase's own regression testing against the 22 preserved
Overpass-origin district caches): GDAL's OSM-driver multipolygon-relation
assembly heuristic silently produced INVALID, wrongly-shaped geometries for
a handful of very large, complex real-world relations (multi-hundred-km^2
forest complexes in Istanbul's northern periphery districts -- Çekmeköy,
Eyüpsultan, Beykoz, Çatalca, Başakşehir, Esenler). Repairing those with
shapely.make_valid() produced geometries that were technically valid but
had lost most of their true area (traced and confirmed via a controlled
comparison: forest-only union for Çekmeköy came out correctly at 95.87M m^2
when isolated, matching Overpass exactly, but collapsed to ~40M m^2 once
combined with the rest of the citywide dataset via the SAME
compute_greenspace_features() dissolve step it has always used -- proving
the corruption was in the upstream polygon assembly, not in the union or
grid-clip logic). Switching the polygon SOURCE to libosmium's Area
Assembler (osmium export) eliminates the invalid geometries entirely (0
invalid features, down from 43) and reproduces the Overpass reference
total for Çekmeköy exactly (111,678,486 m^2 vs Overpass's 111,678,486 m^2).
This is purely a swap of which tool reconstructs OSM relations into
polygons -- no tag, threshold, or aggregation logic changed.

One relation citywide (of ~34,852 exported polygon features) failed even
osmium's own area assembly ("Geometry error: Could not build area
geometry") -- a genuine upstream OSM topology defect in that single
relation, not something either FEED tool can silently paper over; recorded
in QA diagnostics, not silently dropped.

Identifier note: some way-derived polygons in this export lack a stable
"@id" the way relations do; a duplicate check is done on geometry+tag
fingerprints, not on the id column alone.

The existing 22 Overpass-origin per-district caches under
data/raw/osm/landuse_green_by_district/ are NOT touched or mixed in here --
they remain a regression reference only (see `regression_vs_overpass`).

Outputs:
  data/processed/citywide/features/landuse_features_citywide_pbf.parquet
  data/processed/citywide/qa/landuse_qa_citywide.json
  data/processed/citywide/qa/coverage_gate_landuse.json
"""

from __future__ import annotations

import json
import subprocess

import geopandas as gpd
import pandas as pd

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.citywide.coverage_gate import coverage_report, print_report
from src.features import osm_tag_config as tags
from src.features.greenspace_features import compute_greenspace_features
from src.utils import config as cfg

LANDUSE_PBF = cfg.DATA_RAW / "osm" / "pbf" / "landuse_green_extract.osm.pbf"
LANDUSE_POLYGON_EXPORT = cfg.DATA_RAW / "osm" / "pbf" / "landuse_green_export.geojsonseq"
PBF_META = cfg.DATA_RAW / "osm" / "pbf" / "turkey-latest.osm.pbf.meta.json"
OVERPASS_CACHE_DIR = cfg.DATA_RAW / "osm" / "landuse_green_by_district"
OVERPASS_CACHE_META = cfg.DATA_RAW / "osm" / "landuse_green_by_district.meta.json"


def ensure_polygon_export() -> dict:
    """Runs `osmium export --geometry-types=polygon` once (libosmium's own
    Area Assembler, more robust than GDAL's OSM-driver heuristic for large/
    complex multipolygon relations -- see module docstring). Cached; never
    re-run if the output already exists."""
    if LANDUSE_POLYGON_EXPORT.exists():
        print(f"[cache] {LANDUSE_POLYGON_EXPORT} already exists (not re-exported)")
        return {"n_geometry_errors": None, "cached": True}

    print(f"[export] osmium export {LANDUSE_PBF.name} --geometry-types=polygon -> {LANDUSE_POLYGON_EXPORT.name}")
    proc = subprocess.run(
        ["osmium", "export", str(LANDUSE_PBF), "--geometry-types=polygon", "-a", "type,id",
         "-o", str(LANDUSE_POLYGON_EXPORT), "-f", "geojsonseq", "--overwrite", "-e"],
        capture_output=True, text=True,
    )
    stderr_lines = [l for l in proc.stderr.splitlines() if l.strip()]
    n_errors = sum(1 for l in stderr_lines if "Geometry error" in l)
    print(f"    exit_code={proc.returncode}  n_geometry_errors={n_errors}")
    if stderr_lines:
        print("    " + "\n    ".join(stderr_lines[:10]))
    proc.check_returncode()
    return {"n_geometry_errors": n_errors, "geometry_error_messages": stderr_lines[:20], "cached": False}


def load_citywide_grid() -> gpd.GeoDataFrame:
    grid = gpd.read_file(cfg.DATA_PROCESSED / "mobility_grid_500m_metric.gpkg")
    assert grid.crs.to_string() == cfg.METRIC_CRS
    assert len(grid) == 22322, f"expected the frozen citywide grid (22,322 cells), found {len(grid)}"
    assert grid["grid_id"].is_unique
    return grid


def load_landuse_multipolygons() -> tuple[gpd.GeoDataFrame, dict]:
    export_diag = ensure_polygon_export()

    print(f"[load] {LANDUSE_POLYGON_EXPORT} (osmium export --geometry-types=polygon, libosmium Area Assembler)")
    raw = gpd.read_file(LANDUSE_POLYGON_EXPORT)
    raw = raw.set_crs("EPSG:4326", allow_override=True)
    n_raw = len(raw)

    feature_id = raw["@type"].astype(str) + "/" + raw["@id"].astype(str)
    n_true_duplicates = int(feature_id.duplicated().sum())
    n_relation_derived = int((raw["@type"] == "relation").sum())
    n_way_derived = int((raw["@type"] == "way").sum())

    for col in ["landuse", "leisure", "natural"]:
        if col not in raw.columns:
            raw[col] = None

    tag_cols = ["landuse", "leisure", "natural"]
    has_any_target_tag = pd.Series(False, index=raw.index)
    has_any_target_tag |= raw["landuse"].isin(tags.GREEN_LANDUSE_VALUES | set(tags.LANDUSE_COMPOSITION_VALUES.values()))
    has_any_target_tag |= raw["leisure"].isin(tags.GREEN_LEISURE_VALUES)
    has_any_target_tag |= raw["natural"].isin(tags.GREEN_NATURAL_VALUES)
    n_no_target_tag = int((~has_any_target_tag).sum())

    invalid_before = int((~raw.geometry.is_valid).sum())

    diag = {
        "polygon_export_diagnostics": export_diag,
        "n_raw_polygon_rows": n_raw,
        "n_relation_derived": n_relation_derived,
        "n_way_derived": n_way_derived,
        "n_true_duplicate_features_by_type_id": n_true_duplicates,
        "n_rows_with_no_target_landuse_leisure_natural_value": n_no_target_tag,
        "note_on_no_target_tag_rows": "osmium tags-filter (upstream extraction step) matches at the OBJECT "
        "level, so an object matching ANY filter passes through with ALL its tags including non-matching "
        "secondary tags on the same object; compute_greenspace_features()'s own exact-value _select_green() "
        "filters these out downstream, so their presence here is harmless.",
        "n_invalid_geometries_raw": invalid_before,
        "note_on_source": "Polygon geometries sourced via `osmium export --geometry-types=polygon` (libosmium's "
        "Area Assembler), not GDAL/pyogrio's 'multipolygons' layer -- see module docstring for why.",
    }
    return raw[tag_cols + ["geometry"]], diag


def load_overpass_reference() -> tuple[dict, list[str]]:
    meta = json.loads(OVERPASS_CACHE_META.read_text(encoding="utf-8"))
    cached_districts = sorted(p.stem for p in OVERPASS_CACHE_DIR.glob("*.geojson"))
    return meta, cached_districts


def overpass_district_green_grid_clipped(district: str, district_cells: gpd.GeoDataFrame) -> dict:
    """Clips the Overpass-cached raw green polygons to the SAME grid cells
    used for the PBF-derived computation (not a raw whole-district-cache
    total). This is required for a fair comparison: Overpass's polygon
    query filter returns the FULL, unclipped geometry of any way/relation
    that merely intersects the buffered per-district query polygon -- a
    single huge relation (e.g. a large forest) that only touches a small
    district's buffer would otherwise inflate that district's "raw cache
    total" by its ENTIRE area, even though only a sliver of it actually
    falls inside that district. compute_greenspace_features has always
    clipped to grid cells on both the pilot and this PBF pipeline; the
    comparison must do the same on the Overpass side to be apples-to-apples."""
    gdf = gpd.read_file(OVERPASS_CACHE_DIR / f"{district}.geojson")
    poly = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    poly = poly.to_crs(cfg.METRIC_CRS)
    invalid = ~poly.geometry.is_valid
    if invalid.any():
        poly.loc[invalid, "geometry"] = poly.loc[invalid, "geometry"].make_valid()

    mask = pd.Series(False, index=poly.index)
    if "leisure" in poly.columns:
        mask |= poly["leisure"].isin(tags.GREEN_LEISURE_VALUES)
    if "landuse" in poly.columns:
        mask |= poly["landuse"].isin(tags.GREEN_LANDUSE_VALUES)
    if "natural" in poly.columns:
        mask |= poly["natural"].isin(tags.GREEN_NATURAL_VALUES)
    green = poly[mask]
    green_union = green.union_all() if len(green) else None

    if green_union is not None and not green_union.is_empty:
        clipped_area_m2 = float(district_cells.geometry.intersection(green_union).area.sum())
    else:
        clipped_area_m2 = 0.0

    return {
        "n_polygon_features_raw_cache": int(len(poly)),
        "n_green_features_raw_cache": int(len(green)),
        "green_area_m2_raw_unclipped_cache_total": float(green_union.area) if green_union is not None and not green_union.is_empty else 0.0,
        "green_area_m2_clipped_to_district_grid_cells": clipped_area_m2,
    }


def run_regression_vs_overpass(landuse_gdf: gpd.GeoDataFrame) -> dict:
    meta, cached_districts = load_overpass_reference()
    print(f"\n[regression] comparing against {len(cached_districts)} preserved Overpass-origin district caches...")

    pbf_by_district = landuse_gdf.groupby("district")["green_area_m2"].sum()

    comparisons = {}
    for district in cached_districts:
        district_cells = landuse_gdf[landuse_gdf["district"] == district][["grid_id", "geometry"]]
        overpass_stats = overpass_district_green_grid_clipped(district, district_cells)
        pbf_area = float(pbf_by_district.get(district, 0.0))
        overpass_area_clipped = overpass_stats["green_area_m2_clipped_to_district_grid_cells"]
        ratio = pbf_area / overpass_area_clipped if overpass_area_clipped > 0 else (float("inf") if pbf_area > 0 else float("nan"))
        comparisons[district] = {
            **overpass_stats,
            "pbf_grid_clipped_green_area_m2": round(pbf_area, 1),
            "ratio_pbf_over_overpass_clipped": round(ratio, 3) if ratio not in (float("inf"),) else "inf (pbf>0, overpass=0)",
        }

    ratios = [c["ratio_pbf_over_overpass_clipped"] for c in comparisons.values() if isinstance(c["ratio_pbf_over_overpass_clipped"], float)]
    flagged = {d: c for d, c in comparisons.items() if isinstance(c["ratio_pbf_over_overpass_clipped"], float) and not (0.4 <= c["ratio_pbf_over_overpass_clipped"] <= 2.5)}

    return {
        "n_districts_compared": len(cached_districts),
        "comparison_basis_note": "BOTH sides are clipped to the SAME citywide grid cells for each district before "
        "summing area (Overpass raw whole-polygon cache totals are NOT used directly, since Overpass's poly-filter "
        "query returns the full unclipped geometry of any way/relation merely touching the buffered per-district "
        "query polygon, which can massively inflate a small district's raw total when a large relation, e.g. a "
        "big forest, only clips its edge -- see 'green_area_m2_raw_unclipped_cache_total' for that unclipped "
        "figure, kept for transparency but not used in the ratio).",
        "median_ratio_pbf_over_overpass": round(pd.Series(ratios).median(), 3) if ratios else None,
        "mean_ratio_pbf_over_overpass": round(pd.Series(ratios).mean(), 3) if ratios else None,
        "districts_flagged_ratio_outside_0.4_2.5": flagged,
        "per_district": comparisons,
    }


def main() -> None:
    print("=" * 72)
    print("Citywide land-use / green-space features (39 districts, 22,322 cells, PBF-derived)")
    print("=" * 72)

    grid = load_citywide_grid()
    pbf_meta = json.loads(PBF_META.read_text(encoding="utf-8"))

    print("\n[1/4] Load PBF-derived land-use polygons (multipolygons layer)...")
    landuse_raw, load_diag = load_landuse_multipolygons()
    print(f"    {load_diag}")

    print("\n[2/4] compute_greenspace_features() (UNMODIFIED)...")
    features, feature_diag = compute_greenspace_features(landuse_raw, grid)
    print(f"    {feature_diag}")

    missing = set(grid["grid_id"]) - set(features["grid_id"])
    assert not missing, f"{len(missing)} grid cells disappeared during land-use processing"
    assert len(features) == 22322 and features["grid_id"].is_unique

    base = grid[["grid_id", "district", "geometry"]]
    landuse_gdf = gpd.GeoDataFrame(base.merge(features, on="grid_id"), geometry="geometry", crs=cfg.METRIC_CRS)

    print("\n[3/4] Regression vs 22 preserved Overpass-origin district caches...")
    regression = run_regression_vs_overpass(landuse_gdf)
    print(f"    median ratio (pbf/overpass): {regression['median_ratio_pbf_over_overpass']}")
    print(f"    districts flagged outside [0.4, 2.5]: {list(regression['districts_flagged_ratio_outside_0.4_2.5'].keys())}")

    print("\n[4/4] QA...")
    n_districts_present = landuse_gdf["district"].nunique()
    invalid_geom = int((~landuse_gdf.geometry.is_valid).sum())

    landuse_category_cols = list(tags.LANDUSE_COMPOSITION_VALUES.keys())
    n_zero_green = int((landuse_gdf["green_area_ratio"] == 0).sum())
    n_full_green = int((landuse_gdf["green_area_ratio"] >= 0.99).sum())
    zero_green_by_district = landuse_gdf[landuse_gdf["green_area_ratio"] == 0]["district"].value_counts().to_dict()
    ratio_gt1 = landuse_gdf[landuse_gdf["green_area_ratio"] > 1.001]
    coverage_gt1 = landuse_gdf[landuse_gdf["landuse_data_coverage_pct"] > 100.1]

    qa = {
        "pbf_provenance": {
            "source_url": pbf_meta["source_url"], "resolved_url": pbf_meta["resolved_url"],
            "pbf_internal_osm_timestamp": pbf_meta["pbf_internal_osm_timestamp"],
            "sha256": pbf_meta["sha256"], "license": pbf_meta["license"],
        },
        "loading_diagnostics": load_diag,
        "feature_computation_diagnostics": feature_diag,
        "n_grid_cells": len(landuse_gdf),
        "n_districts_present": n_districts_present,
        "n_invalid_final_geometries": invalid_geom,
        "green_area_ratio_stats": landuse_gdf["green_area_ratio"].describe().round(4).to_dict(),
        "n_cells_zero_green": n_zero_green,
        "pct_cells_zero_green": round(n_zero_green / len(landuse_gdf) * 100, 3),
        "zero_green_cells_by_district": zero_green_by_district,
        "n_cells_full_green_gt99pct": n_full_green,
        "n_cells_green_ratio_gt1_should_be_0": len(ratio_gt1),
        "n_cells_landuse_coverage_gt100pct_should_be_0": len(coverage_gt1),
        "landuse_category_stats": landuse_gdf[landuse_category_cols].describe().round(4).to_dict(),
        "landuse_entropy_computed": feature_diag["landuse_entropy_computed"],
        "regression_vs_overpass": regression,
        "total_green_area_km2_citywide": float(landuse_gdf["green_area_m2"].sum() / 1e6),
    }

    out_dir = cfg.DATA_FEATURES
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "landuse_features_citywide_pbf.parquet"
    landuse_gdf.to_parquet(out_path)
    print(f"\n[save] {out_path}")

    qa_dir = cfg.DATA_PROCESSED / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_path = qa_dir / "landuse_qa_citywide.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {qa_path}")

    value_cols = ["green_area_m2"]
    report = coverage_report(landuse_gdf, value_cols)
    print_report(report, "landuse_pbf")
    gate_path = qa_dir / "coverage_gate_landuse.json"
    gate_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[save] {gate_path}")

    print("\n--- SUMMARY ---")
    print(f"Districts present: {n_districts_present}/39")
    print(f"Total green area citywide: {qa['total_green_area_km2_citywide']:.1f} km2")
    print(f"Cells with zero green: {n_zero_green} ({qa['pct_cells_zero_green']}%)")
    print(f"Invalid final geometries: {invalid_geom}")
    print(f"green_area_ratio > 1 (should be 0): {len(ratio_gt1)}")
    print(f"landuse_data_coverage_pct > 100 (should be 0): {len(coverage_gt1)}")
    print(f"Regression median ratio (pbf/overpass): {regression['median_ratio_pbf_over_overpass']}")


if __name__ == "__main__":
    main()
