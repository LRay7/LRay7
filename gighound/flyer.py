"""Flyer inbox — the answer for venues that only announce gigs on social media.

You (or Dad) screenshot an Instagram/Facebook gig flyer; Claude vision reads it
and files the event. No scraping, no ToS problems, one Haiku-tier call per
flyer on your subscription.

Usage: gighound add-flyer photo.jpg [photo2.jpg ...] [--venue "North Park Lounge"]
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from . import db, pipeline
from .extract import _strip_fences, run_claude_cli, schema_instruction
from .models import ExtractionResult, Source

FLYER_PROMPT = """You are reading a photo or screenshot of a live-music gig
flyer or social media post (the image file path is given below — read it).

Extract every live music event announced in the image. Rules:
- Dates must be YYYY-MM-DD; infer the year from the reference date (flyers
  advertise upcoming shows).
- The venue is often in small print or implied by the account name; use the
  hint if one is provided.
- Copy prices/times as written; null for anything not shown.
- Set is_live_music=false for non-music events (trivia, comedy, DJ nights).
"""

# The pseudo-source flyer events are attributed to.
FLYER_SOURCE = Source(
    id="flyer",
    name="Flyer inbox",
    url="manual://flyer",
    kind="manual",
    strategy="manual",
    region="pittsburgh",
    verified=True,
)


def parse_flyer(
    image_path: str | Path, venue_hint: str | None = None, today: date | None = None
) -> ExtractionResult:
    path = Path(image_path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    ref = (today or date.today()).isoformat()
    prompt = (
        f"{FLYER_PROMPT}\n"
        f"Reference date: {ref}\n"
        + (f"Venue hint: {venue_hint}\n" if venue_hint else "")
        + f"\nRead the image at this path and extract the events: {path}\n\n"
        f"{schema_instruction()}"
    )
    # --allowedTools Read lets headless claude open the image without prompting.
    result_text = run_claude_cli(prompt, extra_args=["--allowedTools", "Read"])
    return ExtractionResult.model_validate_json(_strip_fences(result_text))


def add_flyer(image_path: str | Path, venue_hint: str | None = None) -> list[str]:
    """Parse one flyer image and store its events. Returns summary lines."""
    result = parse_flyer(image_path, venue_hint)
    lines = []
    if not result.events:
        return [f"{image_path}: no events found in image"]
    for ev in result.events:
        # Without a venue the event can't be geocoded (and would fall out of
        # radius queries) — the hint fills that gap for account-name flyers.
        if not ev.venue_name and venue_hint:
            ev.venue_name = venue_hint
    conn = db.connect()
    found, new, _ = pipeline._store(conn, FLYER_SOURCE, result.events, "flyer")
    conn.close()
    for ev in result.events:
        marker = "music" if ev.is_live_music else "skipped (not live music)"
        lines.append(
            f"  {ev.date} {ev.start_time or '':5} {ev.artist or ev.title} "
            f"@ {ev.venue_name or venue_hint or '?'} [{marker}]"
        )
    lines.append(f"{image_path}: stored {found} event(s), {new} new")
    return lines
