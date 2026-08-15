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
gighound crawl          fetch each source (politely) → strip to text →
     │                  Claude extracts structured events → geocode →
     ▼                  dedupe (same show via 3 sources = 1 row) → SQLite
data/gighound.db
     │
     ▼
gighound serve          FastAPI + one-page UI: "what's within N miles
                        of me tonight / this weekend?"
```

The LLM extraction step is what makes this tractable: every venue formats its
calendar differently, and one prompt replaces a hand-written scraper per site.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # add your ANTHROPIC_API_KEY
```

## Usage

```bash
gighound sources list        # show the registry
gighound sources check       # ping every source URL — fix broken seeds first!
gighound crawl               # crawl everything (LLM extraction; costs pennies)
gighound crawl --source jergels   # or just one
gighound events              # list upcoming shows near Cranberry Twp
gighound events --radius 30 --days 3
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
- [ ] Ticketmaster Discovery API strategy (arena/theater tier for free)
- [ ] Scheduled crawls (cron / GitHub Actions)
- [ ] Facebook/Instagram: no public events API — investigate per-venue
      workarounds (venue sites usually mirror FB events; some embed widgets)
- [ ] Genre filters in the UI; "notify me" for favorite venues/artists
- [ ] JS-rendered calendars (Playwright fallback for sites that need it)

## Known limitations

- Seed URLs are best-effort and unverified — run `sources check` first.
- Sites that render their calendar entirely client-side will come back empty
  until the Playwright fallback exists.
- Meta killed the public Facebook Events API years ago; that data is only
  reachable indirectly. This is *the* reason no app does this well — and the
  venue-website route covers most of the same events.
