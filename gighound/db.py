from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    dedupe_key TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    artist TEXT,
    date TEXT NOT NULL,           -- YYYY-MM-DD
    start_time TEXT,              -- HH:MM
    venue_name TEXT,
    venue_address TEXT,
    lat REAL,
    lon REAL,
    price TEXT,
    genre TEXT,
    url TEXT,
    source_id TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);

CREATE TABLE IF NOT EXISTS crawl_log (
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    ok INTEGER NOT NULL,
    http_status INTEGER,
    events_found INTEGER,
    error TEXT
);

CREATE TABLE IF NOT EXISTS geocode_cache (
    query TEXT PRIMARY KEY,
    lat REAL,
    lon REAL,
    resolved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pages (
    source_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    last_llm_extracted_at TEXT
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def upsert_event(conn: sqlite3.Connection, key: str, row: dict) -> bool:
    """Insert an event, or refresh last_seen if we already have it.

    Returns True if the event was new.
    """
    now = _now()
    existing = conn.execute(
        "SELECT id FROM events WHERE dedupe_key = ?", (key,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE events SET last_seen = ?, price = COALESCE(?, price), "
            "url = COALESCE(?, url), genre = COALESCE(?, genre) WHERE id = ?",
            (now, row.get("price"), row.get("url"), row.get("genre"), existing["id"]),
        )
        return False
    conn.execute(
        """INSERT INTO events (dedupe_key, title, artist, date, start_time,
               venue_name, venue_address, lat, lon, price, genre, url,
               source_id, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            key,
            row["title"],
            row.get("artist"),
            row["date"],
            row.get("start_time"),
            row.get("venue_name"),
            row.get("venue_address"),
            row.get("lat"),
            row.get("lon"),
            row.get("price"),
            row.get("genre"),
            row.get("url"),
            row["source_id"],
            now,
            now,
        ),
    )
    return True


def page_changed(conn: sqlite3.Connection, source_id: str, content_hash: str) -> bool:
    """True if this source's page content differs from the last LLM extraction.

    Gates the LLM fallback only — structured parsers are free and always run.
    """
    row = conn.execute(
        "SELECT content_hash FROM pages WHERE source_id = ?", (source_id,)
    ).fetchone()
    return row is None or row["content_hash"] != content_hash


def mark_page_extracted(conn: sqlite3.Connection, source_id: str, content_hash: str) -> None:
    conn.execute(
        "INSERT INTO pages (source_id, content_hash, last_llm_extracted_at) VALUES (?, ?, ?) "
        "ON CONFLICT(source_id) DO UPDATE SET content_hash = excluded.content_hash, "
        "last_llm_extracted_at = excluded.last_llm_extracted_at",
        (source_id, content_hash, _now()),
    )


def log_crawl(
    conn: sqlite3.Connection,
    source_id: str,
    ok: bool,
    http_status: int | None = None,
    events_found: int | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO crawl_log (source_id, fetched_at, ok, http_status, events_found, error) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (source_id, _now(), int(ok), http_status, events_found, error),
    )
