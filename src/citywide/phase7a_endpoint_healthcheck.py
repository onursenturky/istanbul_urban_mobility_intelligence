"""Phase 7A step 2: lightweight Overpass endpoint health check ONLY.

Tests the default endpoint (overpass-api.de, used throughout this project)
plus the 3 previously-tested alternative candidates (all found unusable at
that time: kumi.systems rate-limited, openstreetmap.fr requires
whitelisting, openstreetmap.ru unreachable). Each gets ONLY a /status
check and a single-node query -- no district-scale query is attempted
here, regardless of result.
"""

from __future__ import annotations

import json
import time

import requests

CANDIDATES = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.openstreetmap.fr/api",
    "https://overpass.openstreetmap.ru/api",
]


def check_status(endpoint: str) -> dict:
    try:
        t0 = time.time()
        r = requests.get(f"{endpoint}/status", timeout=15, headers={"User-Agent": "istanbul-mobility-research/0.1"})
        elapsed = time.time() - t0
        return {"reachable": True, "http_status": r.status_code, "latency_s": round(elapsed, 2), "body_snippet": r.text[:200].replace("\n", " | ")}
    except requests.exceptions.ConnectionError as exc:
        return {"reachable": False, "error": f"ConnectionError: {exc}"}
    except requests.exceptions.Timeout as exc:
        return {"reachable": False, "error": f"Timeout: {exc}"}


def check_tiny_query(endpoint: str) -> dict:
    try:
        t0 = time.time()
        r = requests.post(f"{endpoint}/interpreter", data={"data": "[out:json];node(1);out;"}, timeout=20,
                           headers={"User-Agent": "istanbul-mobility-research/0.1"})
        elapsed = time.time() - t0
        return {"success": r.status_code == 200, "http_status": r.status_code, "latency_s": round(elapsed, 2)}
    except requests.exceptions.ConnectionError as exc:
        return {"success": False, "error": f"ConnectionError: {exc}"}
    except requests.exceptions.Timeout as exc:
        return {"success": False, "error": f"Timeout: {exc}"}


def main() -> None:
    results = {}
    for i, endpoint in enumerate(CANDIDATES):
        print(f"\n=== {endpoint} ===")
        status = check_status(endpoint)
        print(f"  status: {status}")
        time.sleep(2)
        tiny = check_tiny_query(endpoint)
        print(f"  tiny query: {tiny}")

        suitable = status.get("reachable", False) and tiny.get("success", False)
        results[endpoint] = {"status_check": status, "tiny_query": tiny, "appears_suitable_for_district_queries": suitable}
        print(f"  appears suitable for district-scale queries: {suitable}")

        if i < len(CANDIDATES) - 1:
            time.sleep(5)

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    for ep, r in results.items():
        print(f"{ep}: suitable={r['appears_suitable_for_district_queries']}")

    with open("/tmp/phase7a_endpoint_healthcheck.json", "w") as f:
        json.dump(results, f, indent=2, default=str)


if __name__ == "__main__":
    main()
