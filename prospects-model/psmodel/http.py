"""Cached, throttled, content-asserted HTTP for first-party MLB sources.

Read-only, unauthenticated GETs to MLB-operated hosts. No credentials, no
cookies, no personal data in query strings.

The content assertions are the point of this module. Four endpoints in this
project returned HTTP 200 with data that was wrong or empty:
  - FanGraphs ZiPS `season=` silently ignored (identical rows for 2027/2028)
  - Savant `minors=true` a no-op (byte-identical output)
  - Savant `hfLevel=AAA` on the MLB path: 200, zero rows
  - `statcast-search-minors/csv`: 200, 4,215 rows, every team an MLB club
So: never trust a status code. Assert on what came back.
"""
import hashlib
import json
import os
import time
import urllib.request

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
USER_AGENT = "Mozilla/5.0 (OttoneuAI prospect model; personal research)"
MIN_INTERVAL_S = 1.0          # be a good citizen; never hammer
_last_request_at = [0.0]


class DataError(Exception):
    """Returned payload failed a content assertion."""


def cache_path(url: str, suffix: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    return os.path.join(CACHE_DIR, digest + suffix)


def cache_read(path: str):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    return None


def cache_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _throttle() -> None:
    wait = MIN_INTERVAL_S - (time.time() - _last_request_at[0])
    if wait > 0:
        time.sleep(wait)
    _last_request_at[0] = time.time()


def fetch_text(url: str, suffix: str = ".txt", attempts: int = 3) -> str:
    """GET with disk cache. Cached responses never re-hit the network."""
    path = cache_path(url, suffix)
    cached = cache_read(path)
    if cached is not None:
        return cached
    last = None
    for i in range(attempts):
        try:
            _throttle()
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                text = resp.read().decode("utf-8-sig", errors="replace")
            cache_write(path, text)
            return text
        except Exception as exc:       # noqa: BLE001 - retry any transport error
            last = exc
            time.sleep(1.5 * (i + 1))
    raise DataError(f"fetch failed after {attempts} attempts: {url} ({last})")


def fetch_json(url: str):
    return json.loads(fetch_text(url, ".json"))


def require_rows(rows, label: str):
    """A payload that parsed but holds nothing is a failure, not an empty result."""
    if not rows:
        raise DataError(f"{label}: zero rows returned (HTTP status is not evidence)")
    return rows


def require_keys(rows, keys, label: str):
    missing = [k for k in keys if k not in rows[0]]
    if missing:
        raise DataError(f"{label}: payload missing expected keys {missing}")
    return rows


def require_value(actual, expected, label: str):
    """Guards silently-ignored parameters: assert the response reflects the request."""
    if str(actual) != str(expected):
        raise DataError(f"{label}: expected {expected!r} in payload, got {actual!r} "
                        "- parameter may be silently ignored")
    return actual
