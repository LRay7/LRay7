from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gighound import config, db, query

app = FastAPI(title="GigHound")
STATIC = Path(__file__).parent / "static"


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


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
