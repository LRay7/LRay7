from pathlib import Path

from gighound import db, registry
from gighound.fetch import html_to_text
from gighound.models import dedupe_key, normalize
from gighound.query import events_near, haversine_miles


def test_registry_loads_and_ids_unique():
    sources = registry.load_sources()
    assert len(sources) >= 15
    assert len({s.id for s in sources}) == len(sources)
    for s in sources:
        assert s.url.startswith("http")
        assert s.lat is not None and s.lon is not None


def test_dedupe_key_collapses_variants():
    a = dedupe_key("The Clarks — Live!", "The Clarks", "Jergel's Rhythm Grille", "2026-08-21")
    b = dedupe_key("THE CLARKS", "The  Clarks", "Jergels Rhythm Grille", "2026-08-21")
    assert a == b
    assert normalize("Jergel's") == normalize("JERGELS")


def test_db_upsert_and_radius_query(tmp_path: Path):
    conn = db.connect(tmp_path / "test.db")
    from datetime import date

    today = date.today().isoformat()
    row = {
        "title": "Test Band",
        "artist": "Test Band",
        "date": today,
        "venue_name": "Jergel's",
        "lat": 40.654,
        "lon": -80.096,
        "source_id": "jergels",
    }
    key = dedupe_key(row["title"], row["artist"], row["venue_name"], row["date"])
    assert db.upsert_event(conn, key, row) is True
    assert db.upsert_event(conn, key, row) is False  # second time is an update
    conn.commit()

    # Cranberry Twp is ~4 miles from Warrendale: inside a 10mi radius…
    hits = events_near(conn, 40.685, -80.107, radius_miles=10, days=1)
    assert len(hits) == 1
    assert hits[0]["distance_miles"] < 10
    # …and outside a 1mi radius.
    assert events_near(conn, 40.685, -80.107, radius_miles=1, days=1) == []


def test_haversine_sanity():
    # Cranberry -> downtown Pittsburgh is roughly 17-20 miles straight-line
    d = haversine_miles(40.685, -80.107, 40.441, -79.996)
    assert 15 < d < 22


def test_html_to_text_keeps_links():
    html = '<div><script>junk()</script><p>Fri 8pm: <a href="/show/1">The Clarks</a></p></div>'
    text = html_to_text(html)
    assert "junk" not in text
    assert "The Clarks (/show/1)" in text
