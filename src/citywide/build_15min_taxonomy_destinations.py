"""Phase 8, step 1: everyday-needs taxonomy + destination dataset + network
anchoring.

Reuses the ALREADY-FETCHED citywide raw POI cache
(data/raw/osm/osm_pois_raw_citywide.geojson, 107,002 features) and the
ALREADY-FETCHED citywide transit stops (main_gtfs + iett_gtfs, via
src.features.transit_infrastructure.load_all_transit_stops) -- no new data
acquisition. Reuses poi_features.py's exact within-category node/way dedup
logic (_dedup_within_category) so the SAME real-world POI mapped twice
(e.g. a building outline + a label node) is not treated as two
destinations.

Taxonomy design principle: every category is built from EXPLICIT,
documented raw OSM tag values (not the pre-aggregated 12-category MCDA
system, which was designed for density/entropy scoring, not for naming
individual destinations) -- but categories reuse the SAME tag values as the
frozen MCDA categories wherever they overlap (e.g. Healthcare = exactly
hospital_count + healthcare_count's definitions), so this is an alternative
VIEW of the same underlying data, not a competing classification.

Everyday-needs taxonomy (A-H) -- see poi_everyday_needs_taxonomy.csv /
poi_category_qa.json for full documentation of what is included/excluded
and why. "Daily Services" (D) is a genuinely NEW grouping built directly
from raw amenity/shop tag values that the existing 12-category MCDA system
does not capture at all (bank/atm/post_office/bureau_de_change/veterinary/
hairdresser/laundry/dry_cleaning) -- these were previously "uncategorized
and dropped by design" from the MCDA POI counts, but are genuine everyday
destinations for THIS accessibility application.

Categories NOT constructed (data cannot reliably support them, per
instruction -- not forced): a general "civic/government/emergency
services" category is deliberately excluded (police/fire/courthouse/
townhall/social_facility/place_of_worship exist in the raw data but do not
map to a routine, value-neutral "everyday need" without additional
judgment calls this phase avoids making).
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from scipy.spatial import cKDTree

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.data.fetch_transit_data import fetch_iett_gtfs, fetch_main_gtfs
from src.features import osm_tag_config as tags
from src.features.poi_features import _dedup_within_category
from src.features.transit_infrastructure import load_all_transit_stops
from src.network import network_anchor, network_builder
from src.utils import config as cfg

APP_DIR = cfg.PROJECT_ROOT / "analysis" / "applications" / "15min_city"
POI_RAW_PATH = cfg.DATA_RAW / "osm" / "osm_pois_raw_citywide.geojson"
POI_COLS = ["element", "id", "amenity", "shop", "leisure", "name", "geometry"]

# Daily-service raw tag values NOT captured by any of the frozen 12 MCDA
# POI categories (verified: pharmacy is already in healthcare_count, so
# excluded here to avoid double-counting across taxonomy categories).
DAILY_SERVICE_AMENITY = ["bank", "atm", "post_office", "bureau_de_change", "veterinary"]
DAILY_SERVICE_SHOP = ["hairdresser", "laundry", "dry_cleaning"]

SNAP_QUESTIONABLE_M = 1000.0


def classify_everyday_needs(gdf: gpd.GeoDataFrame) -> pd.Series:
    cat = pd.Series(pd.NA, index=gdf.index, dtype="object")
    unassigned = cat.isna()

    # A. Food/Groceries: grocery shopping + open-air food markets.
    m = unassigned & (gdf["shop"] == "supermarket")
    cat[m] = "A_food_groceries"; unassigned &= ~m
    m = unassigned & (gdf["amenity"] == "marketplace")
    cat[m] = "A_food_groceries"; unassigned &= ~m

    # B. Healthcare: identical definition to the frozen hospital_count + healthcare_count.
    m = unassigned & (gdf["amenity"] == "hospital")
    cat[m] = "B_healthcare"; unassigned &= ~m
    m = unassigned & (gdf["amenity"].isin(["clinic", "doctors", "dentist", "pharmacy"]))
    cat[m] = "B_healthcare"; unassigned &= ~m

    # C. Education: school/university (frozen definitions) + kindergarten + library (new, undercounted previously).
    m = unassigned & (gdf["amenity"].isin(["school", "university", "kindergarten", "library"]))
    cat[m] = "C_education"; unassigned &= ~m

    # D. Daily Services: NEW grouping, raw tags not in any frozen MCDA category.
    m = unassigned & (gdf["amenity"].isin(DAILY_SERVICE_AMENITY))
    cat[m] = "D_daily_services"; unassigned &= ~m
    m = unassigned & (gdf["shop"].isin(DAILY_SERVICE_SHOP))
    cat[m] = "D_daily_services"; unassigned &= ~m

    # E. Retail/Shopping: any other shop=* (frozen retail_count definition, supermarket/daily-service shops already claimed).
    m = unassigned & gdf["shop"].notna()
    cat[m] = "E_retail_shopping"; unassigned &= ~m

    # F. Leisure/Social: cafe/restaurant/bar (frozen cafe_count+restaurant_count+bar_pub_count) + non-green leisure.
    m = unassigned & (gdf["amenity"].isin(["cafe", "restaurant", "fast_food", "bar", "pub", "biergarten"]))
    cat[m] = "F_leisure_social"; unassigned &= ~m
    m = unassigned & gdf["leisure"].notna() & ~gdf["leisure"].isin(tags.GREEN_LEISURE_VALUES)
    cat[m] = "F_leisure_social"; unassigned &= ~m

    # G. Green/Recreation: leisure values that are genuinely green/recreational (POI-sourced only, NOT land-use polygons).
    m = unassigned & gdf["leisure"].isin(tags.GREEN_LEISURE_VALUES)
    cat[m] = "G_green_recreation"; unassigned &= ~m

    return cat


def load_poi_destinations() -> tuple[gpd.GeoDataFrame, dict]:
    print(f"[load] {POI_RAW_PATH} (columns={POI_COLS})")
    raw = pyogrio.read_dataframe(str(POI_RAW_PATH), columns=POI_COLS)
    raw = gpd.GeoDataFrame(raw, geometry="geometry", crs="EPSG:4326")
    n_raw = len(raw)

    invalid = ~raw.geometry.is_valid
    n_invalid = int(invalid.sum())
    if n_invalid:
        raw.loc[invalid, "geometry"] = raw.loc[invalid, "geometry"].make_valid()
    raw = raw[~raw.geometry.is_empty].copy()

    raw["poi_category"] = classify_everyday_needs(raw)
    n_uncategorized = int(raw["poi_category"].isna().sum())
    raw = raw[raw["poi_category"].notna()].copy()

    raw = raw.to_crs(cfg.METRIC_CRS)
    raw, n_dup = _dedup_within_category(raw)
    raw["geometry"] = raw.geometry.representative_point()
    raw["destination_id"] = [f"POI_{e}_{i}" for e, i in zip(raw["element"], raw["id"])]

    diag = {"n_raw": n_raw, "n_invalid_geometries_repaired": n_invalid, "n_uncategorized_dropped": n_uncategorized,
            "n_duplicate_pois_removed_within_category": n_dup, "n_pois_used": len(raw)}
    return raw[["destination_id", "poi_category", "name", "geometry"]], diag


def load_transit_destinations() -> tuple[gpd.GeoDataFrame, dict]:
    main_dir = fetch_main_gtfs()
    iett_dir = fetch_iett_gtfs()
    stops, diag = load_all_transit_stops(main_dir, iett_dir)
    stops = stops.copy()
    stops["poi_category"] = "H_public_transport_access"
    stops["destination_id"] = [f"TRANSIT_{i}" for i in range(len(stops))]
    name_col = "stop_name" if "stop_name" in stops.columns else ("name" if "name" in stops.columns else None)
    stops["name"] = stops[name_col] if name_col else None
    return stops[["destination_id", "poi_category", "name", "geometry"]], diag


def anchor_destinations_to_network(dest: gpd.GeoDataFrame, G_walk) -> gpd.GeoDataFrame:
    node_ids, xy = network_anchor._node_coords(G_walk)
    tree = cKDTree(xy)
    dxy = np.column_stack([dest.geometry.x.to_numpy(), dest.geometry.y.to_numpy()])
    dist, idx = tree.query(dxy, k=1)
    dest = dest.copy()
    dest["network_node"] = node_ids[idx]
    dest["snap_distance_m"] = np.round(dist, 2)
    dest["snap_status"] = np.where(dest["snap_distance_m"] > SNAP_QUESTIONABLE_M, "QUESTIONABLE", "OK")
    return dest


def main() -> None:
    print("=" * 72)
    print("Phase 8 step 1: everyday-needs taxonomy + destination anchoring")
    print("=" * 72)
    APP_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/4] Loading + classifying POI destinations...")
    poi_dest, poi_diag = load_poi_destinations()
    print(f"  {poi_diag}")
    print(poi_dest["poi_category"].value_counts().to_string())

    print("\n[2/4] Loading transit destinations (category H)...")
    transit_dest, transit_diag = load_transit_destinations()
    print(f"  n_transit_stops: {len(transit_dest)}  by_mode: {transit_diag['n_stops_by_mode_total_citywide']}")

    all_dest = pd.concat([poi_dest, transit_dest], ignore_index=True)
    all_dest = gpd.GeoDataFrame(all_dest, geometry="geometry", crs=cfg.METRIC_CRS)
    print(f"\n  total destinations across all categories: {len(all_dest)}")

    print("\n[3/4] Anchoring destinations to the walking network...")
    G_walk = network_builder.load_graph("walking_graph")
    anchored = anchor_destinations_to_network(all_dest, G_walk)
    anchored.to_parquet(APP_DIR / "poi_network_anchors.parquet")
    print(f"  saved poi_network_anchors.parquet")

    anchor_qa_by_cat = {}
    for cat, g in anchored.groupby("poi_category"):
        anchor_qa_by_cat[cat] = {
            "n_destinations": len(g),
            "snap_distance_median_m": round(float(g["snap_distance_m"].median()), 2),
            "snap_distance_p90_m": round(float(g["snap_distance_m"].quantile(0.9)), 2),
            "snap_distance_max_m": round(float(g["snap_distance_m"].max()), 2),
            "n_questionable": int((g["snap_status"] == "QUESTIONABLE").sum()),
            "pct_ok": round(float((g["snap_status"] == "OK").mean() * 100), 2),
        }
    print("\n  anchoring QA by category:")
    for cat, d in anchor_qa_by_cat.items():
        print(f"    {cat}: {d}")

    print("\n[4/4] Saving taxonomy documentation...")
    taxonomy_rows = [
        {"category_code": "A_food_groceries", "category_name": "Food / Groceries",
         "included_tags": "shop=supermarket; amenity=marketplace",
         "excluded": "restaurant/cafe/fast_food (classified as Leisure/Social -- dining out, not grocery shopping)",
         "reliability": "GOOD", "n_destinations": int((anchored["poi_category"] == "A_food_groceries").sum())},
        {"category_code": "B_healthcare", "category_name": "Healthcare",
         "included_tags": "amenity=hospital; amenity in [clinic,doctors,dentist,pharmacy]",
         "excluded": "veterinary (-> Daily Services, animal not human healthcare)",
         "reliability": "GOOD (identical to frozen hospital_count+healthcare_count)",
         "n_destinations": int((anchored["poi_category"] == "B_healthcare").sum())},
        {"category_code": "C_education", "category_name": "Education",
         "included_tags": "amenity in [school,university,kindergarten,library]",
         "excluded": "-", "reliability": "GOOD",
         "n_destinations": int((anchored["poi_category"] == "C_education").sum())},
        {"category_code": "D_daily_services", "category_name": "Daily Services",
         "included_tags": "amenity in [bank,atm,post_office,bureau_de_change,veterinary]; shop in [hairdresser,laundry,dry_cleaning]",
         "excluded": "police/fire_station/courthouse/townhall/social_facility/place_of_worship (civic/emergency/"
                     "religious -- not included, no defensible value-neutral 'everyday need' classification)",
         "reliability": "MODERATE (new grouping, not part of any frozen MCDA category; raw-tag coverage varies)",
         "n_destinations": int((anchored["poi_category"] == "D_daily_services").sum())},
        {"category_code": "E_retail_shopping", "category_name": "Retail / Shopping",
         "included_tags": "shop=* (any value not claimed by A or D)",
         "excluded": "supermarket (-> A), hairdresser/laundry/dry_cleaning (-> D)",
         "reliability": "GOOD (identical to frozen retail_count minus the 3 daily-service shop values)",
         "n_destinations": int((anchored["poi_category"] == "E_retail_shopping").sum())},
        {"category_code": "F_leisure_social", "category_name": "Leisure / Social",
         "included_tags": "amenity in [cafe,restaurant,fast_food,bar,pub,biergarten]; leisure=* EXCLUDING green values",
         "excluded": "tourism=* (visitor-oriented, not a resident everyday need)",
         "reliability": "GOOD", "n_destinations": int((anchored["poi_category"] == "F_leisure_social").sum())},
        {"category_code": "G_green_recreation", "category_name": "Green / Recreation",
         "included_tags": "leisure in [park,garden,nature_reserve,recreation_ground,golf_course] (POI nodes/ways ONLY)",
         "excluded": "Land-use GREEN polygons (data/raw/osm/pbf landuse extract) are NOT used as a destination "
                     "substitute, per instruction -- this materially UNDERCOUNTS true green-space access, since "
                     "most parks/forests are mapped as land-use polygons, not standalone POI nodes.",
         "reliability": "LIMITED -- likely undercounts true green/recreation access; interpret accordingly",
         "n_destinations": int((anchored["poi_category"] == "G_green_recreation").sum())},
        {"category_code": "H_public_transport_access", "category_name": "Public Transport Access",
         "included_tags": "All citywide transit stops (main_gtfs metro/tram/rail/ferry + iett_gtfs bus/metrobüs), "
                          "deduplicated (src.features.transit_infrastructure.load_all_transit_stops)",
         "excluded": "-", "reliability": "GOOD (same source as frozen V1/V2 transit criteria)",
         "n_destinations": int((anchored["poi_category"] == "H_public_transport_access").sum())},
    ]
    pd.DataFrame(taxonomy_rows).to_csv(APP_DIR / "poi_everyday_needs_taxonomy.csv", index=False)
    print(f"  saved poi_everyday_needs_taxonomy.csv")

    category_qa = {
        "poi_source_diagnostics": poi_diag,
        "transit_source_diagnostics": transit_diag,
        "total_destinations": len(anchored),
        "destinations_by_category": anchored["poi_category"].value_counts().to_dict(),
        "anchoring_qa_by_category": anchor_qa_by_cat,
        "excluded_categories_not_constructed": {
            "office_workplaces": "amenity/office=* -- workplaces are not resident-facing everyday-need destinations",
            "tourism": "tourism=* -- visitor-oriented, not an everyday need for residents",
            "civic_emergency_religious": "police/fire_station/courthouse/townhall/social_facility/place_of_worship "
                                          "-- exist in raw data but excluded, no defensible value-neutral grouping",
        },
        "double_counting_avoided": "Each raw POI is assigned to exactly ONE category via ordered, mutually "
            "exclusive rules (same design principle as the frozen 12-category MCDA system); within-category "
            "node/way duplicates of the same physical feature are removed via the same _dedup_within_category "
            "logic already used for frozen POI features.",
    }
    (APP_DIR / "poi_category_qa.json").write_text(json.dumps(category_qa, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  saved poi_category_qa.json")


if __name__ == "__main__":
    main()
