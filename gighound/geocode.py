from __future__ import annotations

import sqlite3
import time

import httpx

from . import config, db

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_last_geocode_at = 0.0


def geocode(conn: sqlite3.Connection, query: str) -> tuple[float, float] | None:
    """Resolve an address/place string to (lat, lon) via Nominatim, with a
    permanent on-disk cache. Respects Nominatim's 1 req/sec policy."""
    global _last_geocode_at
    query = query.strip()
    if not query:
        return None

    cached = conn.execute(
        "SELECT lat, lon FROM geocode_cache WHERE query = ?", (query,)
    ).fetchone()
    if cached:
        if cached["lat"] is None:
            return None
        return cached["lat"], cached["lon"]

    wait = 1.1 - (time.monotonic() - _last_geocode_at)
    if wait > 0:
        time.sleep(wait)
    _last_geocode_at = time.monotonic()

    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": config.USER_AGENT},
            timeout=15.0,
        )
        resp.raise_for_status()
        results = resp.json()
    except httpx.HTTPError:
        return None  # transient failure: don't cache, retry next crawl

    lat = lon = None
    if results:
        lat, lon = float(results[0]["lat"]), float(results[0]["lon"])
    conn.execute(
        "INSERT OR REPLACE INTO geocode_cache (query, lat, lon, resolved_at) "
        "VALUES (?, ?, ?, datetime('now'))",
        (query, lat, lon),
    )
    if lat is None:
        return None
    return lat, lon
