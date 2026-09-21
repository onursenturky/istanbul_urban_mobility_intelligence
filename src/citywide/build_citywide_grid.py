"""Citywide Sections 1+2: expand the study area to all 39 Istanbul districts
and rebuild the 500m grid using EXACTLY the pilot methodology
(src.data.build_study_grid) — no grid definition, clipping logic, or
threshold changes. Only the district list and output location differ (via
the config_citywide overlay).

Run from the project root:
    .venv/bin/python -m src.citywide.build_citywide_grid
"""

from src.citywide import _activate  # noqa: F401 -- must be first import

from src.data import build_study_grid  # noqa: E402


def main() -> None:
    build_study_grid.main(raw_boundary_filename="osm_district_boundaries_raw_citywide39.geojson")


if __name__ == "__main__":
    main()
