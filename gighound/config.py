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

# Extraction model. Claude Opus 5 with structured outputs; effort kept low —
# pulling events out of a page is not deep-reasoning work.
EXTRACTION_MODEL = "claude-opus-5"
EXTRACTION_EFFORT = "low"
MAX_PAGE_CHARS = 40_000  # cap on page text sent to the extractor
