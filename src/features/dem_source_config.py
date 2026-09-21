"""Phase 3D DEM source definition and provenance.

Source investigation, in the project's stated priority order:

1. Copernicus DEM GLO-30 — SELECTED. TanDEM-X X-band SAR interferometry
   (acquired 2011-2015; a dedicated single-purpose global elevation
   mission), released/maintained by ESA/Copernicus. Documented absolute
   accuracy: <6m CE90 horizontal, <4m LE90 vertical. Freely downloadable
   without any login via the AWS Open Data Program (public S3 bucket,
   verified reachable at acquisition time). Vertical reference: EGM2008
   geoid (EPSG:3855) — heights are orthometric, not WGS84-ellipsoidal.

2. NASA SRTM — NOT selected. Older single-mission source (Shuttle Radar
   Topography Mission, February 2000), documented near-global absolute
   vertical accuracy ~16m LE90 — roughly 4x worse than Copernicus DEM —
   and known void issues in the original product (later void-filled
   versions exist but remain based on the same 2000 acquisition).

3. ALOS AW3D30 — NOT selected, though a reasonable alternative. JAXA
   PRISM stereo imagery (~2006-2011), ~5m RMSE vertical accuracy —
   comparable in resolution and roughly comparable in accuracy to
   Copernicus DEM. Copernicus DEM was preferred as the more current,
   single coherent SAR-interferometric acquisition (vs. optical stereo,
   more prone to cloud/shadow artifacts) and because it is itself one of
   the reference datasets used to infill ALOS/SRTM gaps in some regions —
   i.e. Copernicus DEM's own production already incorporates AW3D30 as a
   secondary source where needed, not the reverse.

Resolution was NOT the deciding factor: GLO-30 and AW3D30 are both
nominally 30m. Copernicus DEM was chosen for its more recent, purpose-built
acquisition, better documented vertical accuracy, and equally reproducible
access.
"""

COPERNICUS_DEM = {
    "provider": "ESA / Copernicus Programme, distributed via AWS Open Data",
    "dataset_name": "Copernicus DEM GLO-30 (Global 30m Digital Elevation Model)",
    "dataset_page": "https://registry.opendata.aws/copernicus-dem/",
    "s3_bucket": "copernicus-dem-30m (eu-central-1, public, no-sign-request)",
    "license": "Copernicus DEM open license (free for public use, attribution required) — see https://spacedata.copernicus.eu",
    "acquisition_mission": "TanDEM-X (TerraSAR-X add-on for Digital Elevation Measurements), X-band SAR interferometry",
    "acquisition_years": "2011-2015 (product release 2019-2021)",
    "native_resolution": "1 arc-second (~30m at the equator)",
    "horizontal_crs": "EPSG:4326 (WGS84)",
    "vertical_datum": "EGM2008 geoid (EPSG:3855) — orthometric heights, not WGS84-ellipsoidal",
    "horizontal_accuracy": "< 6 m (CE90)",
    "vertical_accuracy": "< 4 m (LE90)",
    "tiles_used": [
        "Copernicus_DSM_COG_10_N40_00_E029_00_DEM",
        "Copernicus_DSM_COG_10_N41_00_E029_00_DEM",
    ],
    "citation": (
        "European Space Agency, Sinergise (2021). Copernicus Global Digital Elevation Model. "
        "Distributed by OpenTopography / AWS Open Data Program. "
        "https://doi.org/10.5069/G9028PQB"
    ),
}
