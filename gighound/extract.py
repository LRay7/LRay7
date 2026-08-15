from __future__ import annotations

from datetime import date

import anthropic

from . import config
from .models import ExtractionResult, Source

SYSTEM = """You extract live-music event listings from web page text.

The text is a cleaned dump of a venue website, event calendar, ICS feed, or
city-paper listings page. Extract every upcoming live music performance you can
find. Rules:

- Only include live music: bands, solo musicians, open mics with live music,
  orchestra/choir performances. Set is_live_music=false for trivia nights,
  comedy, DJ sets, karaoke, bingo, sports, and non-music events you're unsure
  about — include them in the list with the flag false rather than guessing.
- Dates must be YYYY-MM-DD. The page may show dates without a year: infer the
  year from the reference date you're given (events are upcoming, so a month
  earlier than the reference date means next year).
- Skip events in the past relative to the reference date.
- Copy prices and times as listed; don't invent values. Use null for anything
  not shown.
- URLs: prefer per-event links found in the text (shown in parentheses after
  link text); make relative URLs absolute using the source URL's domain."""


def extract_events(
    text: str, source: Source, today: date | None = None
) -> ExtractionResult:
    """Run one page of text through Claude and get structured events back."""
    client = anthropic.Anthropic()
    ref = (today or date.today()).isoformat()
    response = client.messages.parse(
        model=config.EXTRACTION_MODEL,
        max_tokens=16000,
        output_config={"effort": config.EXTRACTION_EFFORT},
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Reference date: {ref}\n"
                    f"Source: {source.name} ({source.url})\n"
                    f"Source kind: {source.kind}\n\n"
                    f"Page text:\n\n{text}"
                ),
            }
        ],
        output_format=ExtractionResult,
    )
    result = response.parsed_output
    if result is None:
        raise RuntimeError(
            f"extraction returned no parseable output (stop_reason={response.stop_reason})"
        )
    return result
