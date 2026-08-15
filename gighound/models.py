from __future__ import annotations

import re
import unicodedata
from typing import Optional

from pydantic import BaseModel, Field


class Source(BaseModel):
    """One entry in the source registry (a YAML file under sources/)."""

    id: str
    name: str
    url: str
    kind: str = "venue"  # venue | aggregator | calendar | api
    strategy: str = "html"  # html | ics | api:ticketmaster
    lat: Optional[float] = None
    lon: Optional[float] = None
    address: Optional[str] = None
    region: str = "pittsburgh"
    verified: bool = False  # set true once `gighound sources check` confirms the URL
    notes: Optional[str] = None
    enabled: bool = True


class ExtractedEvent(BaseModel):
    """One live-music event as extracted by the LLM from a page."""

    title: str = Field(description="Event or show title as listed")
    artist: Optional[str] = Field(
        default=None, description="Performer/band name if distinct from the title"
    )
    date: str = Field(description="Event date in YYYY-MM-DD format")
    start_time: Optional[str] = Field(
        default=None, description="Start time in 24h HH:MM format if listed"
    )
    venue_name: Optional[str] = Field(
        default=None,
        description="Venue name if the page lists events at multiple venues; "
        "null if everything is at the source venue itself",
    )
    venue_address: Optional[str] = Field(
        default=None, description="Street address or town if shown"
    )
    price: Optional[str] = Field(
        default=None, description="Ticket price or cover charge as listed, e.g. '$10' or 'Free'"
    )
    genre: Optional[str] = Field(
        default=None, description="Musical genre if evident, e.g. 'jazz', 'bluegrass'"
    )
    url: Optional[str] = Field(
        default=None, description="Event detail or ticket URL if present"
    )
    is_live_music: bool = Field(
        description="True only if this is a live music performance (not trivia, "
        "comedy, DJ-only, sports, or non-music events)"
    )


class ExtractionResult(BaseModel):
    """Structured-output schema returned by the extractor for one page."""

    events: list[ExtractedEvent]
    page_has_event_listings: bool = Field(
        description="False if the page contains no event calendar/listings at all"
    )


_norm_re = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """Lowercase, strip accents and punctuation — used to build dedupe keys."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _norm_re.sub("", text.lower())


def dedupe_key(title: str, artist: str | None, venue: str | None, date: str) -> str:
    """Stable key so the same show found via multiple sources collapses to one row.

    Uses artist when present (titles vary across listings more than artist names),
    otherwise the title.
    """
    who = normalize(artist or title)
    where = normalize(venue or "")
    return f"{who}|{where}|{date}"
