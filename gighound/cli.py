from __future__ import annotations

import argparse
import sys

from . import config, db, fetch, pipeline, query, registry


def cmd_sources_list(_args) -> int:
    for s in registry.load_sources():
        flags = []
        if not s.enabled:
            flags.append("disabled")
        if not s.verified:
            flags.append("unverified")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        print(f"{s.id:28} {s.kind:10} {s.url}{suffix}")
    return 0


def cmd_sources_check(_args) -> int:
    """Ping every source URL and report status. Seed URLs are best-effort —
    run this to find the ones that need fixing before the first crawl."""
    failures = 0
    for s in registry.load_sources():
        if not s.enabled:
            continue
        try:
            resp = fetch.fetch_url(s.url, timeout=15.0)
            ok = resp.status_code < 400
            print(f"{'ok ' if ok else 'ERR'} {resp.status_code}  {s.id:28} {s.url}")
            if not ok:
                failures += 1
        except Exception as e:
            print(f"ERR ---  {s.id:28} {s.url}  ({type(e).__name__}: {e})")
            failures += 1
    print(f"\n{failures} source(s) need attention" if failures else "\nall sources reachable")
    return 1 if failures else 0


def cmd_crawl(args) -> int:
    sources = registry.load_sources()
    if args.source:
        sources = [s for s in sources if s.id == args.source]
        if not sources:
            print(f"unknown source: {args.source}", file=sys.stderr)
            return 1
    for line in pipeline.crawl_all(sources, limit=args.limit):
        print(line)
    return 0


def cmd_events(args) -> int:
    conn = db.connect()
    rows = query.events_near(
        conn,
        lat=args.lat,
        lon=args.lon,
        radius_miles=args.radius,
        days=args.days,
    )
    if not rows:
        print("no events found — have you run `gighound crawl`?")
        return 0
    for r in rows:
        when = r["date"] + (f" {r['start_time']}" if r["start_time"] else "")
        who = r["artist"] or r["title"]
        print(f"{when:18} {who:40.40} @ {r['venue_name'] or '?':30.30} {r['distance_miles']:>5} mi")
    conn.close()
    return 0


def cmd_export(args) -> int:
    conn = db.connect()
    n = query.export_json(conn, args.out, days=args.days)
    conn.close()
    print(f"exported {n} events to {args.out}")
    return 0


def cmd_add_flyer(args) -> int:
    from . import flyer

    rc = 0
    for image in args.images:
        try:
            for line in flyer.add_flyer(image, venue_hint=args.venue):
                print(line)
        except Exception as e:
            print(f"{image}: FAILED — {e}", file=sys.stderr)
            rc = 1
    return rc


def cmd_serve(args) -> int:
    import uvicorn

    uvicorn.run("web.app:app", host="0.0.0.0", port=args.port, reload=False)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="gighound", description="Thorough live-music finder")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("sources", help="manage the source registry")
    ssub = sp.add_subparsers(dest="subcmd", required=True)
    ssub.add_parser("list", help="list all sources").set_defaults(func=cmd_sources_list)
    ssub.add_parser("check", help="ping every source URL").set_defaults(func=cmd_sources_check)

    cp = sub.add_parser("crawl", help="crawl sources and extract events")
    cp.add_argument("--source", help="crawl a single source by id")
    cp.add_argument("--limit", type=int, help="crawl at most N sources")
    cp.set_defaults(func=cmd_crawl)

    ep = sub.add_parser("events", help="list upcoming events near a point")
    ep.add_argument("--lat", type=float, default=config.DEFAULT_LAT)
    ep.add_argument("--lon", type=float, default=config.DEFAULT_LON)
    ep.add_argument("--radius", type=float, default=config.DEFAULT_RADIUS_MILES)
    ep.add_argument("--days", type=int, default=7)
    ep.set_defaults(func=cmd_events)

    xp = sub.add_parser(
        "export", help="write upcoming events to web/static/events.json"
    )
    xp.add_argument(
        "--out", default=str(config.REPO_ROOT / "web" / "static" / "events.json")
    )
    xp.add_argument("--days", type=int, default=90)
    xp.set_defaults(func=cmd_export)

    fp = sub.add_parser(
        "add-flyer", help="parse a gig-flyer screenshot into events (Claude vision)"
    )
    fp.add_argument("images", nargs="+", help="flyer image file(s)")
    fp.add_argument("--venue", help="venue hint when the flyer doesn't name it")
    fp.set_defaults(func=cmd_add_flyer)

    vp = sub.add_parser("serve", help="run the web UI")
    vp.add_argument("--port", type=int, default=8000)
    vp.set_defaults(func=cmd_serve)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
