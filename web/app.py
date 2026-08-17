import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gighound import config, db, query

app = FastAPI(title="GigHound")
STATIC = Path(__file__).parent / "static"

MAX_FLYER_BYTES = 15 * 1024 * 1024
ALLOWED_FLYER_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


@app.get("/api/events")
def api_events(
    lat: float = Query(default=config.DEFAULT_LAT),
    lon: float = Query(default=config.DEFAULT_LON),
    radius: float = Query(default=config.DEFAULT_RADIUS_MILES, le=100),
    days: int = Query(default=7, le=60),
    genre: str | None = None,
):
    conn = db.connect()
    try:
        events = query.events_near(conn, lat, lon, radius, days, genre)
    finally:
        conn.close()
    return {"count": len(events), "events": events}


@app.post("/api/flyer")
async def api_flyer(file: UploadFile = File(...), venue: str | None = Form(None)):
    """Parse an uploaded gig-flyer image via Claude vision and store its events."""
    from gighound import flyer

    if file.content_type not in ALLOWED_FLYER_TYPES:
        return {"ok": False, "error": f"unsupported image type: {file.content_type}"}
    contents = await file.read()
    if len(contents) > MAX_FLYER_BYTES:
        return {"ok": False, "error": "image too large (15 MB max)"}
    suffix = Path(file.filename or "flyer.png").suffix or ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name
    try:
        lines = flyer.add_flyer(tmp_path, venue_hint=venue or None)
        return {"ok": True, "lines": lines}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
