from __future__ import annotations

import hashlib
import sqlite3
import traceback

import httpx

from . import config, db, extract, extract_structured, fetch, geocode, ticketmaster
from .models import ExtractedEvent, Source, dedupe_key


class CrawlError(RuntimeError):
    pass


class CrawlRun:
    """Per-run state: counts the LLM calls so the hard cap holds across sources."""

    def __init__(self) -> None:
        self.llm_calls = 0

    def llm_allowed(self) -> bool:
        return (
            config.EXTRACTOR_BACKEND != "none"
            and self.llm_calls < config.MAX_LLM_CALLS_PER_CRAWL
        )


def crawl_source(
    conn: sqlite3.Connection, source: Source, run: CrawlRun | None = None
) -> tuple[int, int, str]:
    """Fetch one source and run it down the extraction ladder:

        1. Ticketmaster API        (free, structured)   strategy api:ticketmaster
        2. schema.org JSON-LD      (free, in the HTML)
        3. iCal feed               (free)               strategy ics or auto-detected
        4. LLM fallback            (only if enabled, under the per-run cap,
                                    and the page content changed)

    Returns (events_found, events_new, method_used).
    """
    run = run or CrawlRun()

    if source.strategy == "api:ticketmaster":
        try:
            events = ticketmaster.fetch_events()
        except Exception as e:
            db.log_crawl(conn, source.id, ok=False, error=f"ticketmaster: {e}")
            conn.commit()
            raise CrawlError(f"{source.id}: ticketmaster: {e}") from e
        return _store(conn, source, events, "ticketmaster")

    try:
        resp = fetch.fetch_url(source.url)
        resp.raise_for_status()
        raw = resp.text
    except httpx.HTTPStatusError as e:
        db.log_crawl(conn, source.id, ok=False, http_status=e.response.status_code, error=str(e))
        conn.commit()
        raise CrawlError(f"{source.id}: HTTP {e.response.status_code}") from e
    except httpx.HTTPError as e:
        db.log_crawl(conn, source.id, ok=False, error=str(e))
        conn.commit()
        raise CrawlError(f"{source.id}: {e}") from e

    # Rung 2/3: free structured parsers.
    if source.strategy == "ics" or extract_structured.looks_like_ics(raw):
        events = extract_structured.from_ics(raw)
        if events:
            return _store(conn, source, events, "ics")
    else:
        events = extract_structured.from_jsonld(raw)
        if events:
            return _store(conn, source, events, "jsonld")

    # Rung 4: LLM fallback — gated three ways (backend, per-run cap, page hash).
    text = fetch.html_to_text(raw)[: config.MAX_PAGE_CHARS]
    content_hash = hashlib.sha256(text.encode()).hexdigest()

    if not run.llm_allowed():
        db.log_crawl(conn, source.id, ok=True, http_status=resp.status_code,
                     events_found=0, error="llm skipped: disabled or per-run cap")
        conn.commit()
        return 0, 0, "skipped(no-llm)"
    if not db.page_changed(conn, source.id, content_hash):
        db.log_crawl(conn, source.id, ok=True, http_status=resp.status_code,
                     events_found=0, error="llm skipped: page unchanged")
        conn.commit()
        return 0, 0, "skipped(unchanged)"

    run.llm_calls += 1
    try:
        result = extract.extract_events(text, source)
    except Exception as e:
        db.log_crawl(conn, source.id, ok=False, error=f"extract: {e}")
        conn.commit()
        raise CrawlError(f"{source.id}: extraction failed: {e}") from e
    db.mark_page_extracted(conn, source.id, content_hash)
    return _store(conn, source, result.events, "llm")


def _store(
    conn: sqlite3.Connection,
    source: Source,
    events: list[ExtractedEvent],
    method: str,
) -> tuple[int, int, str]:
    found = new = 0
    for ev in events:
        if not ev.is_live_music:
            continue
        found += 1
        venue = ev.venue_name or source.name
        lat, lon = ev.lat, ev.lon
        if lat is None:
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
    return found, new, method


def crawl_all(sources: list[Source], limit: int | None = None) -> list[str]:
    """Crawl every enabled source; returns a human-readable summary."""
    conn = db.connect()
    run = CrawlRun()
    lines = []
    todo = [s for s in sources if s.enabled]
    if limit:
        todo = todo[:limit]
    for source in todo:
        try:
            found, new, method = crawl_source(conn, source, run)
            lines.append(f"ok    {source.id}: {found} events ({new} new) via {method}")
        except CrawlError as e:
            lines.append(f"FAIL  {e}")
        except Exception:
            lines.append(f"FAIL  {source.id}: unexpected error\n{traceback.format_exc()}")
    lines.append(
        f"-- llm calls this run: {run.llm_calls}/{config.MAX_LLM_CALLS_PER_CRAWL} "
        f"(backend: {config.EXTRACTOR_BACKEND})"
    )
    conn.close()
    return lines
