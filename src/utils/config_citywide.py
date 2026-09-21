"""Citywide (39-district) configuration overlay.

Imports every constant from the frozen pilot config (src.utils.config) and
overrides ONLY what must differ for a citywide run: the district list and
the output directories (data/processed/citywide/, outputs/maps/citywide/).
Every threshold, buffer distance, CRS, and methodological constant (e.g.
INTERSECTION_THRESHOLD, CYCLING_DEDUP_BUFFER_M, EBIKE slope penalty
constants imported transitively via suitability_config) is untouched —
the pilot methodology is frozen, not re-derived.

Raw data directories (DATA_RAW_*) are DELIBERATELY left pointing at the
same shared data/raw/ tree as the pilot: GTFS, the İBB cycling/population
sources, and the WorldPop raster are already citywide and must be reused,
not re-downloaded under a different path. Only per-feature raw CACHE FILES
that were fetched with a pilot-specific bounding polygon (OSM POI/building/
road/greenspace/cycling-way extracts, and additional DEM tiles) get new,
additively-named cache files alongside the pilot's — the pilot's own raw
files are never modified or overwritten.

Usage: any orchestrator script that must run against the citywide config
does `sys.modules["src.utils.config"] = config_citywide` BEFORE importing
any src.features/src.data module, so every `from src.utils import config as
cfg` inside those modules resolves to this overlay instead of the pilot
config. See src/citywide/_activate.py.
"""

from src.utils import config as _base

# Re-export everything from the pilot config as the starting point.
for _name in dir(_base):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_base, _name)

# --- Overrides ---

DISTRICTS = {
    "Adalar": 963209, "Arnavutköy": 1766093, "Ataşehir": 1276672, "Avcılar": 1766094,
    "Bağcılar": 1766098, "Bahçelievler": 1766095, "Bakırköy": 1766096, "Başakşehir": 1766099,
    "Bayrampaşa": 1766097, "Beşiktaş": 1765893, "Beykoz": 1276910, "Beylikdüzü": 1766100,
    "Beyoğlu": 1765892, "Büyükçekmece": 1275387, "Çatalca": 1275389, "Çekmeköy": 1276034,
    "Esenler": 1766101, "Esenyurt": 1766102, "Eyüpsultan": 1766103, "Fatih": 1766104,
    "Gaziosmanpaşa": 1766105, "Güngören": 1766106, "Kadıköy": 1276548, "Kâğıthane": 1765894,
    "Kartal": 1276013, "Küçükçekmece": 7786498, "Maltepe": 1276407, "Pendik": 1276011,
    "Sancaktepe": 1276014, "Sarıyer": 1765895, "Silivri": 1275379, "Sultanbeyli": 1276012,
    "Sultangazi": 1766108, "Şile": 1275310, "Şişli": 1765896, "Tuzla": 1276010,
    "Ümraniye": 1276890, "Üsküdar": 1276889, "Zeytinburnu": 1766109,
}
assert len(DISTRICTS) == 39, f"expected 39 Istanbul districts, got {len(DISTRICTS)}"

# Boundary provenance note (verified individually, 2026-09-19): Adalar
# lacks the `network=TR34-districts` tag the other 38 districts share (an
# OSM tagging inconsistency, not a semantic difference) — confirmed via a
# direct Overpass lookup of relation 963209 (admin_level=6,
# boundary=administrative, population tag present), not assumed.
DISTRICTS_BOUNDARY_RETRIEVAL_DATE = "2026-09-19"

DATA_PROCESSED = _base.PROJECT_ROOT / "data" / "processed" / "citywide"
DATA_FEATURES = DATA_PROCESSED / "features"
OUTPUTS_MAPS = _base.PROJECT_ROOT / "outputs" / "maps" / "citywide"

# Raw data trees are shared with the pilot (see module docstring) —
# DATA_RAW, DATA_RAW_OSM (via DATA_RAW / "osm"), DATA_RAW_TRANSIT,
# DATA_RAW_POPULATION, DATA_RAW_DEM, DATA_RAW_CYCLING, DATA_RAW_SHARED_MOBILITY
# all come through unchanged from the base config's re-export above.

CITYWIDE_RETRIEVAL_DATE = "2026-09-19"
