"""Phase 3B data acquisition: fetch and cache the two official GTFS feeds.

Downloads the main İBB GTFS (metro/tram/rail/ferry) and the İETT GTFS
(bus/metrobüs) once, caching every resource file untouched under
data/raw/transit/. Re-running loads the cache; delete a feed's directory to
force a re-fetch.

Run from the project root:
    .venv/bin/python -m src.data.fetch_transit_data
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

from src.features import transit_tag_config as tcfg
from src.utils import config as cfg


def _fetch_feed(feed_key: str, feed_cfg: dict) -> Path:
    feed_dir = cfg.DATA_RAW_TRANSIT / feed_key
    meta_path = feed_dir / "_meta.json"
    if meta_path.exists():
        print(f"[cache] {feed_key} already cached at {feed_dir}")
        return feed_dir

    feed_dir.mkdir(parents=True, exist_ok=True)
    print(f"[fetch] downloading {feed_cfg['dataset_name']} ({feed_key})...")
    for resource_name, rel_path in feed_cfg["resources"].items():
        url = tcfg.BASE_URL + rel_path
        out_path = feed_dir / f"{resource_name}.csv"
        resp = requests.get(url, timeout=90, headers={"User-Agent": "istanbul-mobility-research/0.1"})
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        print(f"  {resource_name}.csv <- {url} ({len(resp.content)/1024:.0f} KB)")

    meta = {
        "provider": feed_cfg["provider"],
        "dataset_name": feed_cfg["dataset_name"],
        "dataset_url": feed_cfg["dataset_url"],
        "license": feed_cfg["license"],
        "modes_covered": feed_cfg["modes_covered"],
        "retrieval_date": cfg.TRANSIT_RETRIEVAL_DATE,
        "resource_last_modified": feed_cfg["resource_last_modified"],
        "encoding": feed_cfg["encoding"],
        "delimiter": feed_cfg["delimiter"],
        "source_crs": "EPSG:4326 (stop_lat/stop_lon, GTFS spec)",
        "reliability_note": feed_cfg["reliability_note"],
        "transformations_applied": "none — files stored exactly as downloaded",
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[cache] wrote metadata -> {meta_path}")
    return feed_dir


def fetch_main_gtfs() -> Path:
    return _fetch_feed("main_gtfs", tcfg.MAIN_GTFS)


def fetch_iett_gtfs() -> Path:
    return _fetch_feed("iett_gtfs", tcfg.IETT_GTFS)


def main() -> None:
    print("=" * 72)
    print("Istanbul Urban Mobility Intelligence — Phase 3B: Transit data acquisition")
    print("=" * 72)
    fetch_main_gtfs()
    fetch_iett_gtfs()
    print("\nAll raw transit feeds cached under", cfg.DATA_RAW_TRANSIT)


if __name__ == "__main__":
    main()
