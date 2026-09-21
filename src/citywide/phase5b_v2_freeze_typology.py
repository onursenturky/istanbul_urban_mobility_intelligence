"""Phase 5B-V2: freeze CITYWIDE_V2_EIGHT_FAMILY_TYPOLOGY -- consolidated
methodology/decision report and manifest over the already-produced step
1-4 artifacts. Read-only; performs no new computation other than hashing.
"""

from __future__ import annotations

import hashlib
import json

from src.citywide import _activate  # noqa: F401 -- must be first import
from src.utils import config as cfg

V2EF_DIR = cfg.PROJECT_ROOT / "analysis" / "clustering_v2_eight_family"
VERSION_TAG = "CITYWIDE_V2_EIGHT_FAMILY_TYPOLOGY"


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    return json.loads((V2EF_DIR / path).read_text(encoding="utf-8"))


def main() -> None:
    summary = load("phase5b_v2_summary.json")
    v1v2 = load("v1_v2_comparison.json")
    spatial_change = load("spatial_change_analysis.json")
    ablations = load("controlled_ablations.json")
    limitations = load("limitation_ablations.json")
    robustness = load("algorithm_robustness.json")

    manifest = {
        "version": VERSION_TAG,
        "generated_at_utc": "2026-09-19T21:00:00Z",
        "selected_k": summary["selected_k"],
        "selection_rationale": (
            "k=5 is the silhouette AND Davies-Bouldin peak of the full k=3..10 sweep (silhouette 0.2076, "
            "DB 1.5266), with near-perfect seed stability (min pairwise ARI 0.9988). The split that PRODUCES "
            "k=5 from k=4 (parent cluster covering 38.7% of cells -> 27.4%/14.1% children) is a CLEAN_SPLIT "
            "(no dispersal, no tiny fragment), distinguished by mean_absolute_road_grade_pct (percentile gap "
            "35.2), road_density_km_per_km2 (33.1) and distance_to_nearest_transit_m (32.2) -- i.e. it is "
            "powered by genuinely NEW Phase 7A information, not incidental relabeling. k=6 is a local silhouette "
            "DIP relative to both k=5 and k=7 (0.1994 vs 0.2076/0.2058), and its k=5->k=6 transition shows two "
            "parents partially merging into an overlapping child cluster -- a messier restructuring than a clean "
            "split. k=7's own k=6->k=7 transition includes one DISPERSED parent and one CLEAN_SPLIT that creates "
            "a tiny (2.6%) cluster with NO feature showing a >=15-percentile distinguishing gap -- i.e. an "
            "uninterpretable fragment, not a meaningful regime. k=8-10 seed stability collapses (min pairwise "
            "ARI 0.78 / 0.71 / 0.63) -- not reproducible, ruled out on stability alone. k=5 is therefore "
            "preferred over BOTH immediate neighbors on independent grounds, not because V1 also used k=5.",
        ),
        "cluster_sizes": summary["cluster_sizes"],
        "v1_v2_comparison": {"ari": summary["v1_v2_ari"], "nmi": summary["v1_v2_nmi"],
                              "pct_cells_changed": summary["pct_cells_changed"]},
        "attribution_finding": (
            "The controlled ablation 'v2_minus_roads_landuse_and_roadgrade_true_v1_lineage' (dropping exactly "
            "the 11 features new to V2: 5 road, 4 land-use, 2 road-grade) reproduces the frozen V1 typology "
            "EXACTLY (ARI=1.0000) when refit at k=5. This is direct, clean evidence that ALL of the 20.25% of "
            "cells whose regime changes between V1 and V2 are attributable to the newly recovered road-network "
            "and land-use information -- not to any incidental preprocessing or KMeans relabeling artifact."
        ),
        "family_importance_finding": (
            "The main_gtfs_transit_only limitation ablation (dropping 13 transit features) collapses ARI to "
            "0.4269 vs the full V2.056-feature-matrix, the single biggest sensitivity of any ablation tested -- "
            "larger than dropping roads+land-use+road-grade together (ARI 0.6614 vs frozen V1). Transit "
            "accessibility remains the dominant structural driver of the typology in V2, consistent with its "
            "33.9% family BSS share (17 retained predictors) and NOT a dominance pathology (well distributed "
            "across many predictors, no single feature over 16% individual BSS)."
        ),
        "algorithm_sensitivity_note": (
            "KMeans-vs-GMM ARI is low (0.176) -- reported as a diagnostic per instruction (GMM agreement not "
            "required for acceptance). Indicates the k=5 partition's boundaries are less crisp under an "
            "elliptical-covariance model than KMeans's spherical assumption suggests; does not by itself argue "
            "against k=5, since KMeans stability, silhouette/DB peak, and spatial coherence are all independently strong."
        ),
        "spatial_change_summary": {
            "citywide_pct_changed": spatial_change["citywide_pct_changed"],
            "top_5_districts_by_pct_changed": spatial_change["by_district_pct_changed"][:5],
            "northern_periphery_pct_changed": spatial_change["northern_periphery_pct_changed"],
            "note": "Change concentrates in DENSE HISTORIC URBAN CORE districts (Fatih 80.8%, Zeytinburnu 72.0%, "
                    "Bağcılar 59.3%, Kadıköy 56.8%), not in the northern forest-periphery districts where "
                    "land-use recovery was largest in absolute area terms (16.98% changed there vs 20.25% "
                    "citywide) -- the new ROAD-GRADE/fine-grained road-network signal is what reshuffles dense, "
                    "topographically varied historic cores, while the periphery's typology was already well "
                    "explained by transit/population/POI sparsity even without land-use/road data.",
        },
        "controlled_ablations": ablations,
        "limitation_ablations": limitations,
        "algorithm_robustness": robustness,
        "output_artifacts": {
            "cluster_assignments": str(V2EF_DIR / "cluster_assignments_v2ef.parquet"),
            "k_diagnostic_table": str(V2EF_DIR / "candidate_k_diagnostics_v2ef.csv"),
            "split_transition_analysis": str(V2EF_DIR / "split_transition_analysis_v2ef.json"),
            "candidate_k_full_profiles": str(V2EF_DIR / "candidate_k_full_profiles_v2ef.json"),
            "v1_v2_comparison": str(V2EF_DIR / "v1_v2_comparison.json"),
            "spatial_change_analysis": str(V2EF_DIR / "spatial_change_analysis.json"),
            "controlled_ablations": str(V2EF_DIR / "controlled_ablations.json"),
            "limitation_ablations": str(V2EF_DIR / "limitation_ablations.json"),
            "algorithm_robustness": str(V2EF_DIR / "algorithm_robustness.json"),
            "spatial_coherence": str(V2EF_DIR / "spatial_coherence_v2ef.json"),
        },
        "cluster_assignments_sha256": sha256_of(V2EF_DIR / "cluster_assignments_v2ef.parquet"),
        "stop_condition": "MCDA architecture, readiness/opportunity scoring, scenarios, consensus classes, and "
                          "the final communication layer were NOT modified or rerun under this version.",
        "recommendation": "V2 typology should SUPERSEDE V1 for downstream interpretation once MCDA is updated: "
                          "it is built on a strictly more complete feature set (8 vs 6 families), the additional "
                          "structure it reveals is demonstrably attributable to genuine new information (not "
                          "noise), it remains highly stable (seed ARI>0.998) and spatially coherent (significant "
                          "positive Moran's I in every cluster), and V1 remains fully preserved and available as "
                          "an audit trail / regression reference, never overwritten.",
    }

    out_path = V2EF_DIR / "v2_typology_manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[save] {out_path}")
    print(f"\nVersion: {VERSION_TAG}  Selected k: {summary['selected_k']}  V1-V2 ARI: {summary['v1_v2_ari']}")


if __name__ == "__main__":
    main()
