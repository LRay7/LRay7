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


def test_jsonld_extraction():
    from gighound.extract_structured import from_jsonld

    html = """<html><head><script type="application/ld+json">
    {"@context": "https://schema.org", "@graph": [
      {"@type": "MusicEvent", "name": "Bluegrass Night",
       "startDate": "2099-06-05T19:30:00-04:00",
       "location": {"@type": "Place", "name": "The Strand",
         "address": {"streetAddress": "119 N Main St", "addressLocality": "Zelienople"}},
       "performer": {"@type": "MusicGroup", "name": "The Hillbenders"},
       "offers": {"price": "15", "url": "https://tix.example/1"}},
      {"@type": "Event", "name": "Trivia Tuesday", "startDate": "2099-06-02"},
      {"@type": "Event", "name": "Acoustic Evening", "startDate": "1999-01-01"}
    ]}</script></head></html>"""
    events = from_jsonld(html)
    assert len(events) == 2  # past event dropped
    music = next(e for e in events if e.title == "Bluegrass Night")
    assert music.is_live_music and music.artist == "The Hillbenders"
    assert music.date == "2099-06-05" and music.start_time == "19:30"
    assert music.venue_name == "The Strand"
    assert "Zelienople" in music.venue_address
    trivia = next(e for e in events if e.title == "Trivia Tuesday")
    assert trivia.is_live_music is False


def test_ics_extraction():
    from gighound.extract_structured import from_ics, looks_like_ics

    ics = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        "BEGIN:VEVENT\r\nSUMMARY:Jazz Trio\r\n"
        "DTSTART;TZID=America/New_York:20990821T200000\r\n"
        "LOCATION:Harmony Inn\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nSUMMARY:Bingo Night\r\nDTSTART:20990822\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    assert looks_like_ics(ics)
    events = from_ics(ics)
    assert len(events) == 2
    jazz = events[0]
    assert jazz.title == "Jazz Trio" and jazz.date == "2099-08-21"
    assert jazz.start_time == "20:00" and jazz.venue_name == "Harmony Inn"
    assert events[1].is_live_music is False  # bingo filtered by flag


def test_ticketmaster_parse():
    from gighound.ticketmaster import parse_response

    data = {"_embedded": {"events": [{
        "name": "The Avett Brothers",
        "url": "https://www.ticketmaster.com/event/x",
        "dates": {"start": {"localDate": "2099-09-12", "localTime": "19:00:00"}},
        "classifications": [{"genre": {"name": "Folk"}}],
        "priceRanges": [{"min": 45.0, "max": 89.5}],
        "_embedded": {"venues": [{
            "name": "Stage AE",
            "address": {"line1": "400 North Shore Dr"},
            "location": {"latitude": "40.4463", "longitude": "-80.0110"},
        }]},
    }]}}
    events = parse_response(data)
    assert len(events) == 1
    ev = events[0]
    assert ev.start_time == "19:00" and ev.genre == "folk"
    assert ev.price == "$45–$90"
    assert abs(ev.lat - 40.4463) < 1e-6


def test_cli_envelope_and_fence_stripping():
    from gighound.extract import _strip_fences, parse_cli_envelope

    stdout = '{"type":"result","result":"```json\\n{\\"events\\": [], \\"page_has_event_listings\\": false}\\n```"}'
    text = parse_cli_envelope(stdout)
    assert _strip_fences(text) == '{"events": [], "page_has_event_listings": false}'


def test_flyer_venue_hint_applied(tmp_path: Path, monkeypatch):
    from gighound import flyer
    from gighound.models import ExtractedEvent, ExtractionResult

    img = tmp_path / "flyer.png"
    img.write_bytes(b"\x89PNG fake")
    monkeypatch.setenv("GIGHOUND_DB_PATH", str(tmp_path / "flyer.db"))
    monkeypatch.setattr(
        flyer,
        "parse_flyer",
        lambda *a, **k: ExtractionResult(
            events=[ExtractedEvent(title="Porch Band", date="2099-07-04", is_live_music=True)],
            page_has_event_listings=True,
        ),
    )
    # DB path is read at connect time via config; patch config to be safe.
    from gighound import config as cfg

    monkeypatch.setattr(cfg, "DB_PATH", tmp_path / "flyer.db")
    lines = flyer.add_flyer(img, venue_hint="North Park Lounge")
    assert any("North Park Lounge" in line for line in lines)
    assert any("1 new" in line for line in lines)


def test_page_hash_gate(tmp_path: Path):
    conn = db.connect(tmp_path / "gate.db")
    assert db.page_changed(conn, "src", "hash1") is True
    db.mark_page_extracted(conn, "src", "hash1")
    assert db.page_changed(conn, "src", "hash1") is False
    assert db.page_changed(conn, "src", "hash2") is True


def test_export_json(tmp_path: Path):
    import json
    from datetime import date

    from gighound.query import export_json

    conn = db.connect(tmp_path / "exp.db")
    row = {
        "title": "Export Band", "artist": "Export Band",
        "date": date.today().isoformat(), "venue_name": "Jergel's",
        "lat": 40.654, "lon": -80.096, "source_id": "jergels",
    }
    db.upsert_event(conn, dedupe_key("Export Band", None, "Jergel's", row["date"]), row)
    conn.commit()

    out = tmp_path / "events.json"
    n = export_json(conn, out)
    assert n == 1
    data = json.loads(out.read_text())
    assert data["count"] == 1
    assert data["events"][0]["artist"] == "Export Band"
    assert data["events"][0]["lat"] == 40.654


def test_flyer_upload_endpoint(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient

    from gighound import flyer
    from web.app import app

    monkeypatch.setattr(
        flyer, "add_flyer", lambda path, venue_hint=None: [f"stored 1 event ({venue_hint})"]
    )
    client = TestClient(app)

    resp = client.post(
        "/api/flyer",
        files={"file": ("flyer.png", b"\x89PNG fake", "image/png")},
        data={"venue": "North Park Lounge"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "North Park Lounge" in body["lines"][0]

    bad = client.post(
        "/api/flyer", files={"file": ("f.pdf", b"%PDF", "application/pdf")}
    )
    assert bad.json()["ok"] is False
