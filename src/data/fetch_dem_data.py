"""Phase 3D data acquisition: fetch and cache Copernicus DEM GLO-30 tiles.

Downloads the two 1x1 degree tiles covering the pilot study area once,
caching each untouched under data/raw/dem/. Re-running loads the cache;
delete a tile file to force a re-fetch.

Run from the project root:
    .venv/bin/python -m src.data.fetch_dem_data
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

from src.features import dem_source_config as dcfg
from src.utils import config as cfg

BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"


def fetch_dem_tiles() -> list[Path]:
    out_dir = cfg.DATA_RAW_DEM
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for tile in dcfg.COPERNICUS_DEM["tiles_used"]:
        out_path = out_dir / f"{tile}.tif"
        meta_path = out_dir / f"{tile}.meta.json"
        if out_path.exists():
            print(f"[cache] {tile} already cached at {out_path}")
            paths.append(out_path)
            continue

        url = f"{BASE_URL}/{tile}/{tile}.tif"
        print(f"[fetch] downloading {url} ...")
        resp = requests.get(url, timeout=180, headers={"User-Agent": "istanbul-mobility-research/0.1"})
        resp.raise_for_status()
        out_path.write_bytes(resp.content)

        meta = {**dcfg.COPERNICUS_DEM, "tile": tile, "source_url": url, "retrieval_date": cfg.DEM_RETRIEVAL_DATE,
                "file_size_bytes": len(resp.content)}
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[cache] wrote {tile} ({len(resp.content) / 1e6:.1f} MB) -> {out_path}")
        paths.append(out_path)
    return paths


def main() -> None:
    print("=" * 72)
    print("Istanbul Urban Mobility Intelligence — Phase 3D: DEM data acquisition")
    print("=" * 72)
    fetch_dem_tiles()


if __name__ == "__main__":
    main()
