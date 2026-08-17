"""Ticketmaster Discovery API strategy — free tier, structured JSON, no LLM.

Covers the arena/theater tier (Stage AE, PPG Paints Arena, Benedum, etc.)
wholesale. Get a free key at https://developer.ticketmaster.com and set
TICKETMASTER_API_KEY.
"""

from __future__ import annotations

import os

import httpx

from . import config
from .models import ExtractedEvent

API_URL = "https://app.ticketmaster.com/discovery/v2/events.json"


def fetch_events(
    city: str = "Pittsburgh", state: str = "PA", size: int = 100
) -> list[ExtractedEvent]:
    api_key = os.environ.get("TICKETMASTER_API_KEY")
    if not api_key:
        raise RuntimeError("TICKETMASTER_API_KEY not set")
    resp = httpx.get(
        API_URL,
        params={
            "classificationName": "music",
            "city": city,
            "stateCode": state,
            "size": size,
            "sort": "date,asc",
            "apikey": api_key,
        },
        headers={"User-Agent": config.USER_AGENT},
        timeout=20.0,
    )
    resp.raise_for_status()
    return parse_response(resp.json())


def parse_response(data: dict) -> list[ExtractedEvent]:
    events: list[ExtractedEvent] = []
    for item in (data.get("_embedded") or {}).get("events", []):
        start = item.get("dates", {}).get("start", {})
        ev_date = start.get("localDate")
        if not ev_date:
            continue
        venues = (item.get("_embedded") or {}).get("venues", [])
        venue = venues[0] if venues else {}
        genre = None
        for cls in item.get("classifications", []):
            g = (cls.get("genre") or {}).get("name")
            if g and g.lower() not in ("undefined", "other"):
                genre = g.lower()
                break
        price = None
        for pr in item.get("priceRanges", []):
            lo, hi = pr.get("min"), pr.get("max")
            if lo is not None:
                price = f"${lo:.0f}" + (f"–${hi:.0f}" if hi and hi != lo else "")
                break
        # Ticketmaster gives exact venue coordinates — carry them through.
        loc = venue.get("location") or {}
        events.append(
            ExtractedEvent(
                title=item.get("name", "Untitled"),
                artist=item.get("name"),
                date=ev_date,
                start_time=(start.get("localTime") or "")[:5] or None,
                venue_name=venue.get("name"),
                venue_address=(venue.get("address") or {}).get("line1"),
                price=price,
                genre=genre,
                url=item.get("url"),
                is_live_music=True,
                lat=float(loc["latitude"]) if loc.get("latitude") else None,
                lon=float(loc["longitude"]) if loc.get("longitude") else None,
            )
        )
    return events
