# Istanbul Urban Mobility Intelligence -- Framework Evidence Narrative

## A. Istanbul is spatially heterogeneous
The V2 eight-family typology (k=5, evidence-based selection) shows Istanbul is not one
city but several recurring urban regimes -- dense transit-rich cores, dense peripheral
residential areas, and sparse/rural-edge districts -- each with a materially different
accessibility profile (see `typology_accessibility_gap_summary.csv`).

## B. Accessibility is concentrated
14.6% of grid cells hold 82.5% of the calibrated population's complete-walking-access
outcome (C01). This is not a modeling artifact: Phase 8.1's population-concentration
analysis confirmed the top 10% densest cells hold ~80% of population, and ~92% of that
population already has complete access. Land-area coverage and population coverage are
different lenses and must never be conflated.

## C. Cycling changes the accessibility geography
Cycling raises complete everyday-needs access from 82.5% to 95.6% of the population
(C01 vs C03), and 2.10 million people gain complete access specifically by switching the
modeled mode from walking to cycling (C02). This is Phase 9's central finding.

## D. Cycling also expands transit catchments
Cycling's largest quantified transit contribution is fixed-guideway access: RAW figures
suggest ~4.80 million people gain modeled 15-minute cycling access to metro/tram/rail/
metrobus that they lack by walking (C05) -- but this RAW figure swings by +30.83
percentage points when non-GOOD_COVERAGE districts are excluded (Phase 10 feed-gap
sensitivity test). The quality-aware, defensible figure for a *combined* everyday+transit
cycling closure is far smaller: 341,370 people (C07).

## E. Not all accessibility gaps are solved by cycling
352,939 people remain in cells where cycling's modeled network does not close any missing
required category (C06) -- these are areas of genuine destination sparsity, not network
or routing limitations. No active-mobility intervention can create a destination that does
not exist.

## F. Independent applications show cross-application convergence
Cells where cycling closes an everyday-needs gap are strongly over-represented in the
independently-derived e-bike Readiness top quartile (74.67% vs a 25% citywide baseline,
C08). The two applications were built from different frozen sources with no shared
computation -- this convergence is a meaningful cross-check, though explicitly not a
validation of either application.

## G. Uncertainty is part of the product
Only 27.29% of cells (73.84% of population) qualify as STRICT_SYNTHESIS_RELIABLE --
reliable enough for a joint everyday-needs-and-transit claim. Transit-feed coverage,
not network quality, is the dominant constraint: Silivri and Catalca have zero mapped
transit stops (NO_FEED_COVERAGE, re-confirmed by direct re-audit), and 16 further
districts show sparse or suspect coverage. Adalar carries a standing, explicitly flagged
network limitation across every phase (small isolated walking component; zero real
cycling nodes, with cycling figures reflecting cross-water snapping). None of this
uncertainty is hidden inside a combined score -- it is reported as its own dimension
throughout (`walking_quality`, `cycling_quality`, `transit_data_quality`,
`synthesis_reliable`).

*No causal claims are made anywhere in this framework. All figures describe modeled
network accessibility of a calibrated 2020 population surface against a 2026 network/
destination/transit-feed snapshot.*
