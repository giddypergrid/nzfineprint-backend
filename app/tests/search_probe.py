"""Regression probe for the keyword search route — run it against a live API.

    python app/tests/search_probe.py                          # localhost
    python app/tests/search_probe.py https://api.nzfineprint.com

Every case here is a real query that broke, or nearly broke, the self-lookup promise. The MISS cases
matter most: they are companies that do NOT exist in the record, and the old AND-based full-text
search answered all of them with confident, wrong, scary results. A search that invents a match for
someone checking their own name is worse than one that finds nothing.
"""
import json
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://localhost:8000"

# Server allows 10 requests/minute per IP, so pace the suite rather than tripping our own limiter.
SECONDS_BETWEEN_REQUESTS = 6.5

# (query, expect_hit, substring the top result must contain when expect_hit)
CASES = [
    ("Du Val", True, "Du Val"),
    ("Sacred Hill", True, "Sacred Hill"),
    ("liquidation", True, ""),

    # Genuinely listed inside a 41-company bulk removal notice — the names live in the body, not the
    # title, so these prove phrase matching still reaches into fulltext and finds you when it counts.
    ("Bay Radiators Limited", True, ""),
    ("Boston Finance Limited", True, ""),
    ("Skippy NZ Limited", True, ""),

    # None of these exist. Each previously matched a bulk list by borrowing words from several
    # different companies ("BAY RADIATORS" + "…PLUMBING SERVICES" + 39x "LIMITED").
    ("Bay Plumbing Limited", False, ""),
    ("Sunrise Cafe Limited", False, ""),
    ("Kaikoura Plumbing Limited", False, ""),
    ("Tarquin Plumbing Limited", False, ""),
    ("Blakeley Cafe Limited", False, ""),
    ("Vandermeer Electrical Limited", False, ""),
]


def post_search(base_url: str, query: str, limit: int = 3) -> dict:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/search",
        data=json.dumps({"q": query, "limit": limit}).encode(),
        # Cloudflare 403s the default Python-urllib agent, so identify as an ordinary client.
        headers={"Content-Type": "application/json", "User-Agent": "fineprint-search-probe/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def check_case(base_url: str, query: str, expect_hit: bool, must_contain: str) -> tuple[bool, str]:
    """Run one case. Returns (passed, one-line detail for the report)."""
    try:
        payload = post_search(base_url, query)
    except urllib.error.HTTPError as error:
        return False, f"HTTP {error.code}"

    count = payload.get("count", 0)
    results = payload.get("results", [])
    top = (results[0].get("headline") or results[0].get("title") or "") if results else ""

    if expect_hit and count == 0:
        return False, "expected a match, got none"
    if not expect_hit and count > 0:
        return False, f"expected none, got {count}: {top[:60]}"
    if expect_hit and must_contain.lower() not in top.lower():
        return False, f"top result missing '{must_contain}': {top[:60]}"

    return True, (top[:60] if expect_hit else "no match, as expected")


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    print(f"Probing {base_url} - {len(CASES)} cases\n")

    failures = 0
    for index, (query, expect_hit, must_contain) in enumerate(CASES):
        passed, detail = check_case(base_url, query, expect_hit, must_contain)
        failures += not passed
        print(f"  {'PASS' if passed else 'FAIL'}  {'hit ' if expect_hit else 'miss'}  "
              f"{query:<30} {detail}")
        if index < len(CASES) - 1:
            time.sleep(SECONDS_BETWEEN_REQUESTS)

    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
