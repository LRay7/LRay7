from __future__ import annotations

import sqlite3
import traceback

import httpx

from . import db, extract, fetch, geocode
from .models import Source, dedupe_key


def crawl_source(conn: sqlite3.Connection, source: Source) -> tuple[int, int]:
    """Fetch one source, extract events, geocode, and store.

    Returns (events_found, events_new). Errors are logged to crawl_log and
    re-raised as CrawlError for the CLI to summarize.
    """
    try:
        text = fetch.fetch_source_text(source.url, source.strategy)
    except httpx.HTTPStatusError as e:
        db.log_crawl(conn, source.id, ok=False, http_status=e.response.status_code, error=str(e))
        conn.commit()
        raise CrawlError(f"{source.id}: HTTP {e.response.status_code}") from e
    except httpx.HTTPError as e:
        db.log_crawl(conn, source.id, ok=False, error=str(e))
        conn.commit()
        raise CrawlError(f"{source.id}: {e}") from e

    try:
        result = extract.extract_events(text, source)
    except Exception as e:
        db.log_crawl(conn, source.id, ok=False, error=f"extract: {e}")
        conn.commit()
        raise CrawlError(f"{source.id}: extraction failed: {e}") from e

    found = new = 0
    for ev in result.events:
        if not ev.is_live_music:
            continue
        found += 1
        venue = ev.venue_name or source.name
        lat, lon = source.lat, source.lon
        # Aggregator pages list many venues; resolve each venue's location.
        if ev.venue_name and ev.venue_name != source.name:
            place = ev.venue_address or f"{ev.venue_name}, {source.region.title()}, PA"
            coords = geocode.geocode(conn, place)
            if coords:
                lat, lon = coords
        key = dedupe_key(ev.title, ev.artist, venue, ev.date)
        row = ev.model_dump()
        row.update(venue_name=venue, lat=lat, lon=lon, source_id=source.id)
        if db.upsert_event(conn, key, row):
            new += 1

    db.log_crawl(conn, source.id, ok=True, http_status=200, events_found=found)
    conn.commit()
    return found, new


def crawl_all(sources: list[Source], limit: int | None = None) -> list[str]:
    """Crawl every enabled source; returns a human-readable summary."""
    conn = db.connect()
    lines = []
    todo = [s for s in sources if s.enabled]
    if limit:
        todo = todo[:limit]
    for source in todo:
        try:
            found, new = crawl_source(conn, source)
            lines.append(f"ok    {source.id}: {found} events ({new} new)")
        except CrawlError as e:
            lines.append(f"FAIL  {e}")
        except Exception:
            lines.append(f"FAIL  {source.id}: unexpected error\n{traceback.format_exc()}")
    conn.close()
    return lines


class CrawlError(RuntimeError):
    pass
