"""LLM fallback extraction — the last rung of the ladder.

Only pages the free structured parsers couldn't handle reach this module, and
the pipeline only calls it when the page content changed since last time.

Backends (config.EXTRACTOR_BACKEND):
  claude-cli  shell out to `claude -p` (Claude Code headless) — runs on your
              Claude subscription with no API key. Defaults to Haiku, which
              barely registers against usage limits.
  api         Anthropic API (needs ANTHROPIC_API_KEY; pay per token).
  none        handled upstream; this module is never called.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import date

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
  link text); make relative URLs absolute using the source URL's domain.
- Leave lat/lon null unless literal coordinates appear in the text."""


def extract_events(
    text: str, source: Source, today: date | None = None
) -> ExtractionResult:
    ref = (today or date.today()).isoformat()
    user_content = (
        f"Reference date: {ref}\n"
        f"Source: {source.name} ({source.url})\n"
        f"Source kind: {source.kind}\n\n"
        f"Page text:\n\n{text}"
    )
    backend = config.EXTRACTOR_BACKEND
    if backend == "claude-cli":
        return _extract_via_claude_cli(user_content)
    if backend == "api":
        return _extract_via_api(user_content)
    raise RuntimeError(f"LLM extraction called with backend={backend!r}")


# --- claude-cli backend (subscription, no API key) ---------------------------

def _extract_via_claude_cli(user_content: str) -> ExtractionResult:
    schema = json.dumps(ExtractionResult.model_json_schema())
    prompt = (
        f"{SYSTEM}\n\n"
        f"Respond with ONLY a JSON object matching this JSON Schema — no prose, "
        f"no code fences:\n{schema}\n\n{user_content}"
    )
    proc = subprocess.run(
        [
            "claude",
            "-p",
            "--model",
            config.CLAUDE_CLI_MODEL,
            "--output-format",
            "json",
        ],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude CLI failed (rc={proc.returncode}): {proc.stderr.strip()[:300]}"
        )
    envelope = json.loads(proc.stdout)
    result_text = envelope.get("result", "")
    return ExtractionResult.model_validate_json(_strip_fences(result_text))


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    return m.group(1) if m else text


def claude_cli_available() -> bool:
    try:
        subprocess.run(
            ["claude", "--version"], capture_output=True, timeout=15, check=True
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


# --- API backend (pay per token) ---------------------------------------------

def _extract_via_api(user_content: str) -> ExtractionResult:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=config.EXTRACTION_MODEL,
        max_tokens=16000,
        output_config={"effort": config.EXTRACTION_EFFORT},
        system=SYSTEM,
        messages=[{"role": "user", "content": user_content}],
        output_format=ExtractionResult,
    )
    result = response.parsed_output
    if result is None:
        raise RuntimeError(
            f"extraction returned no parseable output (stop_reason={response.stop_reason})"
        )
    return result
