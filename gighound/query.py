from __future__ import annotations

import math
import sqlite3
from datetime import date, timedelta


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8  # earth radius, miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def events_near(
    conn: sqlite3.Connection,
    lat: float,
    lon: float,
    radius_miles: float = 25,
    days: int = 7,
    genre: str | None = None,
) -> list[dict]:
    """Upcoming events within radius, soonest first."""
    start = date.today().isoformat()
    end = (date.today() + timedelta(days=days)).isoformat()
    # Coarse bounding box in SQL, exact haversine in Python.
    dlat = radius_miles / 69.0
    dlon = radius_miles / (69.0 * max(0.1, math.cos(math.radians(lat))))
    sql = (
        "SELECT * FROM events WHERE date >= ? AND date <= ? "
        "AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?"
    )
    params: list = [start, end, lat - dlat, lat + dlat, lon - dlon, lon + dlon]
    if genre:
        sql += " AND genre LIKE ?"
        params.append(f"%{genre}%")
    sql += " ORDER BY date, start_time"

    out = []
    for row in conn.execute(sql, params):
        d = dict(row)
        if d["lat"] is None:
            continue
        dist = haversine_miles(lat, lon, d["lat"], d["lon"])
        if dist <= radius_miles:
            d["distance_miles"] = round(dist, 1)
            out.append(d)
    return out
