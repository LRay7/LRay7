# GigHound 🐕

**Every live show near you — even the ones the big apps miss.**

Bandsintown and Ticketmaster only know about shows that flow through their
pipes. The jazz trio at the wine bar, the bluegrass night at the brewery, the
free summer concert in the township park — those live on venue websites,
Facebook pages, and the city paper's listings. GigHound crawls those sources
directly, extracts events with an LLM, and serves one radius-filtered list.

Current scope: **the Pittsburgh metro**, with the deepest coverage in the
Cranberry Township / North Hills corridor.

## How it works

```
sources/*.yaml          the source registry — one entry per venue site,
     │                  calendar, city-paper page, or API
     ▼
gighound crawl          fetch each source (politely), then run it down
     │                  the extraction ladder → geocode → dedupe
     ▼                  (same show via 3 sources = 1 row) → SQLite
data/gighound.db
     │
     ▼
gighound serve          FastAPI + one-page UI: "what's within N miles
                        of me tonight / this weekend?"
```

### The extraction ladder (designed to cost $0)

Each source is tried against progressively smarter — and only at the very end
non-free — extractors:

1. **Ticketmaster Discovery API** — free key; the arena/theater tier as JSON.
2. **schema.org JSON-LD** — most venue sites embed their calendar as
   machine-readable Event markup for SEO. Free, exact, no AI.
3. **iCal feeds** — WordPress event calendars expose these. Free.
4. **LLM fallback** — only for pages the parsers can't handle, and only when
   the page's content hash changed since the last extraction. Runs through
   `claude -p` (Claude Code headless) on your **existing Claude subscription**
   — no API key — using Haiku, so it barely touches usage limits. Hard-capped
   at `GIGHOUND_MAX_LLM_CALLS` per crawl (default 8).

Knobs:

| Env var | Default | Meaning |
|---|---|---|
| `GIGHOUND_EXTRACTOR` | `claude-cli` | `claude-cli` \| `api` \| `none` (structured-only, LLM fully off) |
| `GIGHOUND_CLI_MODEL` | `haiku` | Model for the `claude -p` fallback |
| `GIGHOUND_MAX_LLM_CALLS` | `8` | Hard cap on LLM calls per crawl run |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# no API key needed — the LLM fallback uses the `claude` CLI you already have.
# optional: cp .env.example .env for a TICKETMASTER_API_KEY (free tier)
```

## Usage

```bash
gighound sources list        # show the registry (38 sources and counting)
gighound sources check       # ping every source URL — fix broken seeds first!
gighound crawl               # run everything down the extraction ladder
gighound crawl --source jergels   # or just one
gighound events              # list upcoming shows near Cranberry Twp
gighound events --radius 30 --days 3
gighound add-flyer shot.png --venue "North Park Lounge"   # parse a gig flyer
gighound serve               # web UI at http://localhost:8000
```

Run the tests with `pytest`.

## Adding a source

Append an entry to a YAML file under `sources/pittsburgh/` (or add a new file):

```yaml
- id: my-venue
  name: My Venue
  url: https://myvenue.com/events
  kind: venue          # venue | aggregator | calendar | api
  strategy: html       # html | ics | api:ticketmaster
  lat: 40.685
  lon: -80.107
  notes: why this source matters
```

That's the whole integration — the crawler and extractor handle the rest.
Scope is just the length of this list.

## Roadmap

- [ ] Verify/fix all seed source URLs (`gighound sources check`)
- [ ] Scheduled crawls (cron / GitHub Actions)
- [x] **Flyer inbox** (CLI) — `gighound add-flyer shot.png` parses a
      screenshot of an Instagram/Facebook gig flyer via Claude vision
      (`claude -p`, subscription, no API key). Untested against the live CLI —
      exercise it on first run. Web-UI drag-and-drop still to come.
- [ ] RSS-Bridge experiment for public Facebook pages (flaky but free)
- [ ] Genre filters in the UI; "notify me" for favorite venues/artists
- [ ] JS-rendered calendars (Playwright fallback for sites that need it)

## Social-media-only venues

Some bars announce gigs only on Facebook/Instagram (e.g. North Park Lounge).
There is no public Meta events API, and page scraping is login-walled and
ToS-hostile — that's *the* reason no existing app covers these well. GigHound's
strategy, in order: (1) the venue's own website usually mirrors the FB posts;
(2) aggregators (City Paper, WYEP) catch cross-posted gigs; (3) RSS-Bridge for
public pages; (4) the flyer inbox — a human screenshots the post, the app does
the rest.

## Known limitations

- Seed URLs are best-effort and unverified — run `sources check` first.
- Sites that render their calendar entirely client-side will come back empty
  until the Playwright fallback exists.
- Meta killed the public Facebook Events API years ago; that data is only
  reachable indirectly. This is *the* reason no app does this well — and the
  venue-website route covers most of the same events.
