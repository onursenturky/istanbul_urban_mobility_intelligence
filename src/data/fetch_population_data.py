"""Phase 3C data acquisition: fetch and cache the WorldPop population raster.

Downloads the WorldPop constrained, UN-adjusted, 100m Turkey population
raster once and caches it untouched under data/raw/population/. Re-running
loads the cache; delete the file to force a re-fetch.

Run from the project root:
    .venv/bin/python -m src.data.fetch_population_data
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

from src.features import population_source_config as pcfg
from src.utils import config as cfg

RASTER_FILENAME = "tur_ppp_2020_UNadj_constrained.tif"


def fetch_worldpop_raster() -> Path:
    out_dir = cfg.DATA_RAW_POPULATION
    out_path = out_dir / RASTER_FILENAME
    meta_path = out_dir / f"{RASTER_FILENAME}.meta.json"

    if out_path.exists():
        print(f"[cache] population raster already cached at {out_path}")
        return out_path

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[fetch] downloading {pcfg.WORLDPOP['download_url']}...")
    resp = requests.get(
        pcfg.WORLDPOP["download_url"], timeout=180, headers={"User-Agent": "istanbul-mobility-research/0.1"}
    )
    resp.raise_for_status()
    out_path.write_bytes(resp.content)

    meta = {**pcfg.WORLDPOP, "retrieval_date": cfg.POPULATION_RETRIEVAL_DATE, "file_size_bytes": len(resp.content)}
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[cache] wrote raster ({len(resp.content) / 1e6:.1f} MB) -> {out_path}")
    return out_path


def main() -> None:
    print("=" * 72)
    print("Istanbul Urban Mobility Intelligence — Phase 3C: Population data acquisition")
    print("=" * 72)
    fetch_worldpop_raster()


if __name__ == "__main__":
    main()
