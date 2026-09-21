"""Human-readable metadata for every column in population_features.*.

Exported as data/processed/features/population_feature_dictionary.csv.
"""

from src.features import population_source_config as pcfg
from src.utils import config as cfg

_SRC = f"{pcfg.WORLDPOP['dataset_name']} ({pcfg.WORLDPOP['provider']})"
_METHOD = (
    "Area-weighted allocation: each ~100m source pixel's footprint is intersected with the "
    "cell polygon; the pixel contributes population * (intersection_area / pixel_area) to the "
    "cell, so a pixel split across cells is divided proportionally rather than duplicated."
)

FEATURE_DICTIONARY = [
    {
        "feature_name": "population",
        "description": "Estimated 2020 residential population allocated to the cell (NOT employment, tourism, or daytime population)",
        "unit": "people (count)",
        "source": _SRC,
        "reference_year": pcfg.WORLDPOP["reference_year"],
        "processing_method": _METHOD,
    },
    {
        "feature_name": "population_density_km2",
        "description": "Residential population per km^2 of the cell's actual land area (not the nominal 0.25 km^2)",
        "unit": "people / km^2",
        "source": "derived",
        "reference_year": pcfg.WORLDPOP["reference_year"],
        "processing_method": "population / (land_area_m2 / 1e6), using the cell's true clipped land area from Phase 2.",
    },
]

FEATURE_DICTIONARY_COLUMNS = [
    "feature_name", "description", "unit", "source", "reference_year", "processing_method", "retrieval_date",
]


def as_dataframe():
    import pandas as pd

    rows = [dict(row, retrieval_date=cfg.POPULATION_RETRIEVAL_DATE) for row in FEATURE_DICTIONARY]
    return pd.DataFrame(rows, columns=FEATURE_DICTIONARY_COLUMNS)
