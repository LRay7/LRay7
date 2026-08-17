"""Free extraction paths: schema.org JSON-LD and iCal feeds.

These run before any LLM is considered. Most venue websites embed their event
calendar as JSON-LD for SEO, and WordPress event plugins expose iCal feeds —
both are machine-readable for $0.
"""

from __future__ import annotations

import json
import re
from datetime import date

from .models import ExtractedEvent

_jsonld_re = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I,
)

# Generic "Event" entries that are clearly not live music.
_NOT_MUSIC = re.compile(
    r"\b(trivia|bingo|quiz|karaoke|comedy|open mic comedy|paint|yoga|market|drag brunch)\b",
    re.I,
)

MUSIC_TYPES = {"MusicEvent", "Festival"}
GENERIC_TYPES = {"Event", "TheaterEvent", "SocialEvent"}


def from_jsonld(html: str, today: date | None = None) -> list[ExtractedEvent]:
    """Pull schema.org Event objects out of a page's JSON-LD blocks."""
    ref = (today or date.today()).isoformat()
    events: list[ExtractedEvent] = []
    for match in _jsonld_re.finditer(html):
        try:
            data = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue
        for node in _walk_nodes(data):
            ev = _node_to_event(node)
            if ev and ev.date >= ref:
                events.append(ev)
    return events


def _walk_nodes(data):
    """Yield every dict in a JSON-LD document (handles lists and @graph)."""
    if isinstance(data, list):
        for item in data:
            yield from _walk_nodes(item)
    elif isinstance(data, dict):
        yield data
        for key in ("@graph", "itemListElement", "item", "subEvent"):
            if key in data:
                yield from _walk_nodes(data[key])


def _types_of(node: dict) -> set[str]:
    t = node.get("@type", [])
    return {t} if isinstance(t, str) else set(t)


def _node_to_event(node: dict) -> ExtractedEvent | None:
    types = _types_of(node)
    is_music_type = bool(types & MUSIC_TYPES)
    if not is_music_type and not (types & GENERIC_TYPES):
        return None

    name = node.get("name")
    start = node.get("startDate")
    if not name or not start or not isinstance(start, str):
        return None
    ev_date, ev_time = _split_iso(start)
    if not ev_date:
        return None

    location = node.get("location") or {}
    if isinstance(location, list):
        location = location[0] if location else {}
    venue_name = location.get("name") if isinstance(location, dict) else None
    address = _address_of(location) if isinstance(location, dict) else None

    performer = node.get("performer") or {}
    if isinstance(performer, list):
        performer = performer[0] if performer else {}
    artist = performer.get("name") if isinstance(performer, dict) else None

    offers = node.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = None
    if isinstance(offers, dict) and offers.get("price") not in (None, ""):
        price = str(offers["price"])
        if price in ("0", "0.0", "0.00"):
            price = "Free"

    url = node.get("url") or (offers.get("url") if isinstance(offers, dict) else None)

    return ExtractedEvent(
        title=name,
        artist=artist,
        date=ev_date,
        start_time=ev_time,
        venue_name=venue_name,
        venue_address=address,
        price=price,
        genre=node.get("genre") if isinstance(node.get("genre"), str) else None,
        url=url if isinstance(url, str) else None,
        is_live_music=is_music_type or not _NOT_MUSIC.search(name),
    )


def _address_of(location: dict) -> str | None:
    addr = location.get("address")
    if isinstance(addr, str):
        return addr
    if isinstance(addr, dict):
        parts = [
            addr.get("streetAddress"),
            addr.get("addressLocality"),
            addr.get("addressRegion"),
        ]
        joined = ", ".join(p for p in parts if p)
        return joined or None
    return None


def _split_iso(value: str) -> tuple[str | None, str | None]:
    """'2026-08-21T20:00:00-04:00' -> ('2026-08-21', '20:00'); dates pass through."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}))?", value)
    if not m:
        return None, None
    return m.group(1), m.group(2)


# --- iCal ---------------------------------------------------------------------

def looks_like_ics(body: str) -> bool:
    return body.lstrip().startswith("BEGIN:VCALENDAR")


def from_ics(body: str, today: date | None = None) -> list[ExtractedEvent]:
    """Minimal VEVENT parser: SUMMARY, DTSTART, LOCATION, URL."""
    ref = (today or date.today()).isoformat()
    # Unfold continuation lines (RFC 5545: lines starting with space/tab)
    body = re.sub(r"\r?\n[ \t]", "", body)
    events: list[ExtractedEvent] = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", body, re.S):
        fields: dict[str, str] = {}
        for line in block.strip().splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.split(";")[0].upper()] = value.strip()
        summary = fields.get("SUMMARY")
        dtstart = fields.get("DTSTART", "")
        m = re.match(r"(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2}))?", dtstart)
        if not summary or not m:
            continue
        ev_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        if ev_date < ref:
            continue
        ev_time = f"{m.group(4)}:{m.group(5)}" if m.group(4) else None
        events.append(
            ExtractedEvent(
                title=summary,
                date=ev_date,
                start_time=ev_time,
                venue_name=fields.get("LOCATION") or None,
                url=fields.get("URL") or None,
                is_live_music=not _NOT_MUSIC.search(summary),
            )
        )
    return events
