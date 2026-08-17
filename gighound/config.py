import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = REPO_ROOT / "sources"
DATA_DIR = Path(os.environ.get("GIGHOUND_DATA_DIR", REPO_ROOT / "data"))
DB_PATH = Path(os.environ.get("GIGHOUND_DB_PATH", DATA_DIR / "gighound.db"))

USER_AGENT = (
    "GigHoundBot/0.1 (+https://github.com/LRay7/LRay7; personal live-music finder)"
)

# Default "home" for the app when the browser can't geolocate: Cranberry Township, PA
DEFAULT_LAT = 40.685
DEFAULT_LON = -80.107
DEFAULT_RADIUS_MILES = 25

# --- Extraction ladder -------------------------------------------------------
# Free structured parsers (JSON-LD, iCal, Ticketmaster API) run first and cost
# nothing. Only pages they can't handle reach the LLM fallback, and only when
# the page content has changed since the last LLM extraction.
#
# EXTRACTOR_BACKEND:
#   claude-cli  (default) shell out to `claude -p` — runs on your Claude
#               subscription, no API key needed
#   api         Anthropic API via ANTHROPIC_API_KEY (pay per token)
#   none        structured parsers only; the LLM path is fully disabled
EXTRACTOR_BACKEND = os.environ.get("GIGHOUND_EXTRACTOR", "claude-cli")

# Model for the `claude -p` fallback. Haiku is deliberate: extraction is easy,
# and Haiku calls barely register against subscription usage limits. Never set
# this to an Opus/Fable-tier model for routine crawling.
CLAUDE_CLI_MODEL = os.environ.get("GIGHOUND_CLI_MODEL", "haiku")

# Model for the `api` backend (only used if you opt into API billing).
EXTRACTION_MODEL = "claude-opus-5"
EXTRACTION_EFFORT = "low"

# Hard cap on LLM fallback calls in a single crawl run, regardless of backend.
MAX_LLM_CALLS_PER_CRAWL = int(os.environ.get("GIGHOUND_MAX_LLM_CALLS", "8"))

MAX_PAGE_CHARS = 40_000  # cap on page text sent to the extractor
