from __future__ import annotations

import re
import time

import httpx

from . import config

_script_re = re.compile(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", re.S | re.I)
_tag_re = re.compile(r"<[^>]+>")
_ws_re = re.compile(r"[ \t]+")
_blank_re = re.compile(r"\n{3,}")

_last_request_at = 0.0
MIN_DELAY_SECONDS = 2.0  # politeness delay between requests to anyone


def _throttle() -> None:
    global _last_request_at
    wait = MIN_DELAY_SECONDS - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def fetch_url(url: str, timeout: float = 20.0) -> httpx.Response:
    _throttle()
    with httpx.Client(
        headers={"User-Agent": config.USER_AGENT},
        follow_redirects=True,
        timeout=timeout,
    ) as client:
        return client.get(url)


def html_to_text(html: str) -> str:
    """Crude HTML -> text good enough for LLM extraction.

    Keeps hrefs inline so the extractor can pull event/ticket URLs.
    """
    html = _script_re.sub(" ", html)
    # keep link targets: <a href="X">Y</a> -> Y (X)
    html = re.sub(
        r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        lambda m: f"{m.group(2)} ({m.group(1)}) ",
        html,
        flags=re.S | re.I,
    )
    html = re.sub(r"</(p|div|li|tr|h[1-6]|br)>", "\n", html, flags=re.I)
    text = _tag_re.sub(" ", html)
    text = text.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#039;", "'")
    text = _ws_re.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = _blank_re.sub("\n\n", text)
    return text.strip()


def fetch_source_text(url: str, strategy: str = "html") -> str:
    """Fetch a source and return text ready for the extractor.

    Every strategy funnels into plain text — the LLM extractor handles HTML
    dumps, ICS feeds, and JSON alike. Dedicated parsers can replace the LLM
    per-strategy later if cost becomes a concern.
    """
    resp = fetch_url(url)
    resp.raise_for_status()
    body = resp.text
    if strategy == "html":
        body = html_to_text(body)
    return body[: config.MAX_PAGE_CHARS]
