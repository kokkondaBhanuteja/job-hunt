"""
Tiny argparse CLI. Lets you run each phase by hand before wiring the MCP host.

Examples:
    uv run hunt selfcheck
    uv run hunt parse-resume
    uv run hunt discover-naukri --keyword "nestjs backend" --location bangalore
    uv run hunt score
    uv run hunt top --min-score 70 --limit 10
    uv run hunt serve-mcp
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from job_hunt import services
from job_hunt.llm import chat  # AI Gateway entrypoint
from job_hunt.llm.ollama import installed_models, is_alive  # Ollama-provider liveness (selfcheck)
from job_hunt.llm.registry import resolve as resolve_llm
from job_hunt.sources.login import login_sync
from job_hunt.storage import repo


VAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "resumes"


# ---------- commands ----------


def cmd_selfcheck(_: argparse.Namespace) -> int:
    """Verify each task's configured LLM provider (local Ollama OR an API key) works."""
    print(f"Datastore:      {repo.describe()}")
    print(f"Vault dir:      {VAULT_DIR}")
    print(f"Ollama alive:   {is_alive()}")
    print(f"Models pulled:  {installed_models() or '(none)'}")

    ok = True
    for task in ("scoring", "drafting"):
        provider, model = resolve_llm(task)
        print(f"\ntask={task}: provider={provider.name} model={model!r}")
        print("  trying a tiny chat round-trip...", end=" ", flush=True)
        try:
            reply = chat("Respond with just the word: pong", task=task, temperature=0.0)
            print(f"ok ({reply.strip()[:50]!r})")
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED: {exc}")
            ok = False
    return 0 if ok else 1


def cmd_parse_resume(_: argparse.Namespace) -> int:
    """Parse every resume in data/resumes/ into the SQLite vault."""
    if not VAULT_DIR.exists() or not any(VAULT_DIR.iterdir()):
        print(f"!! Vault is empty: {VAULT_DIR}")
        print("   Add a .tex or .pdf file and re-run.")
        return 1
    results = services.parse_resume_vault(VAULT_DIR)
    print(f"Parsed {len(results)} resume variant(s):")
    for slug, vid in results:
        print(f"  - {slug:<20} → variant_id={vid}")
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    """One-time interactive login that persists cookies for later crawls."""
    return login_sync(args.site)


def cmd_discover_naukri(args: argparse.Namespace) -> int:
    # Default to HEADED (RPA-style). Pass --headless once the session is warm.
    headless = args.headless
    print(
        f"Crawling Naukri (headless={headless}): "
        f"keyword={args.keyword!r}, location={args.location!r}, pages={args.pages}"
    )
    result = services.discover_naukri(
        args.keyword,
        args.location,
        pages=args.pages,
        dry_run=args.dry_run,
        headless=headless,
    )
    print(f"  found={result['found']}  new={result['new']}  dry_run={args.dry_run}")
    if args.dry_run and args.verbose:
        for c in result["jobs"][:10]:
            print(f"   • {c['title']!r} @ {c['company']!r} — {c['location']!r}")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    """Discover jobs from any registered source (naukri, remoteok, ...)."""
    from job_hunt import plugins

    if args.source not in plugins.available_sources():
        print(f"!! unknown source '{args.source}'. Available: {plugins.available_sources()}")
        return 1
    print(f"Discovering via {args.source}: keyword={args.keyword!r}, location={args.location!r}")
    result = services.discover(
        args.source, args.keyword, args.location, pages=args.pages,
        dry_run=args.dry_run, headless=args.headless,
    )
    print(f"  found={result['found']}  new={result['new']}  dry_run={args.dry_run}")
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    """Fetch the full JD for discovered jobs (opens each job page)."""
    result = services.enrich_pending_jobs(limit=args.limit, headless=args.headless)
    print(f"  enriched {result['enriched']}/{result['candidates']} candidates")
    return 0


def cmd_tailor(args: argparse.Namespace) -> int:
    result = services.tailor_for_job(args.job_id)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    print(f"tailored resume for job {args.job_id} (variant {result['variant']}):\n")
    print(result["content"])
    return 0


def cmd_cover(args: argparse.Namespace) -> int:
    result = services.draft_cover_for_job(args.job_id)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    print(f"cover letter draft #{result['draft_id']} for job {args.job_id}:\n")
    print(result["body"])
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    try:
        summary = services.score_pending(verbose=args.verbose)
    except RuntimeError as exc:
        print(f"!! {exc}")
        return 1
    print(f"  {summary}")
    return 0


def cmd_top(args: argparse.Namespace) -> int:
    rows = services.list_top_matches(min_score=args.min_score, limit=args.limit)
    if not rows:
        print(f"(no jobs with score >= {args.min_score})")
        return 0
    print(f"Top {len(rows)} matches (min_score={args.min_score}):")
    for r in rows:
        print(
            f"  [{r['best_score']:3d}] {r['company'][:25]:<25} | "
            f"{r['title'][:55]:<55} | suggest: {r['best_variant']}"
        )
    return 0


def cmd_profiles(_: argparse.Namespace) -> int:
    rows = services.list_profiles()
    if not rows:
        print("(no search profiles — add one with `hunt add-profile`)")
        return 0
    for r in rows:
        flag = "on " if r["enabled"] else "off"
        print(f"  [{r['id']:>2}] {flag} {r['name']:<20} {r['keywords']!r} @ {r['location']!r} pages={r['pages']}")
    return 0


def cmd_add_profile(args: argparse.Namespace) -> int:
    pid = services.add_profile(
        name=args.name, keywords=args.keyword, location=args.location, pages=args.pages
    )
    print(f"added profile #{pid}: {args.name}")
    return 0


def cmd_run_cycle(args: argparse.Namespace) -> int:
    """Run a discovery+scoring cycle for every active profile."""
    from job_hunt.worker.runner import run_all_active_profiles

    results = run_all_active_profiles(headless=args.headless)
    if not results:
        print("(no active profiles — add one with `hunt add-profile`)")
        return 0
    for res in results:
        print(
            f"  run #{res['run_id']} {res['status']}: "
            f"found={res.get('found', '-')} new={res.get('new', '-')}"
        )
    return 0


def cmd_worker(_: argparse.Namespace) -> int:
    """Start the long-running background worker (APScheduler)."""
    from job_hunt.worker.scheduler import run as worker_run

    worker_run()
    return 0


def cmd_serve_api(args: argparse.Namespace) -> int:
    """Start the REST API (FastAPI) bound to localhost with a bearer token."""
    import os
    import secrets

    import uvicorn

    if not os.getenv("API_TOKEN"):
        token = secrets.token_hex(16)
        os.environ["API_TOKEN"] = token  # share with the in-process app
        print(f"API token (ephemeral): {token}")
        print("  → set API_TOKEN in .env.local to keep it stable across restarts")
    uvicorn.run("job_hunt.api.app:app", host=args.host, port=args.port)
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    result = services.embed_jobs(limit=args.limit)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    print(f"  embedded {result['embedded']}/{result['candidates']} jobs")
    return 0


def cmd_semantic(args: argparse.Namespace) -> int:
    result = services.semantic_match(args.query, limit=args.limit)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    for r in result["results"]:
        print(f"  [{r['distance']:.3f}] {r['company'][:25]:<25} | {r['title'][:55]}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Print the daily report; optionally send it to the configured channel."""
    print(services.daily_report_text())
    if args.send:
        print(f"\n[sent: {services.send_daily_report()}]")
    return 0


def cmd_serve_mcp(_: argparse.Namespace) -> int:
    """Start the MCP server over stdio. Use this in your MCP host's config."""
    from job_hunt.mcp_server.server import main as mcp_main

    mcp_main()
    return 0


def cmd_db(args: argparse.Namespace) -> int:
    """Quick raw-SQL SELECT utility for inspection (active backend)."""
    repo.init_db()
    rows = repo.raw_select(args.sql)
    print(json.dumps(rows, indent=2, default=str))
    return 0


# ---------- argparse wiring ----------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hunt", description="Personal job-hunt toolkit")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("selfcheck", help="Verify Ollama + DB are ready").set_defaults(func=cmd_selfcheck)
    sub.add_parser("parse-resume", help="Parse data/resumes/ vault into DB").set_defaults(func=cmd_parse_resume)

    lg = sub.add_parser("login", help="One-time login that persists cookies for a site")
    lg.add_argument("site", choices=["naukri", "foundit"])
    lg.set_defaults(func=cmd_login)

    d = sub.add_parser("discover-naukri", help="Crawl Naukri.com (RPA-style — visible browser by default)")
    d.add_argument("--keyword", required=True)
    d.add_argument("--location", required=True)
    d.add_argument("--pages", type=int, default=1)
    d.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    d.add_argument("--headless", action="store_true", help="Hide the browser (only after a successful warm run)")
    d.add_argument("--verbose", action="store_true")
    d.set_defaults(func=cmd_discover_naukri)

    gd = sub.add_parser("discover", help="Discover jobs from any source (naukri, remoteok, ...)")
    gd.add_argument("--source", default="naukri")
    gd.add_argument("--keyword", required=True)
    gd.add_argument("--location", default="remote")
    gd.add_argument("--pages", type=int, default=1)
    gd.add_argument("--dry-run", action="store_true")
    gd.add_argument("--headless", action="store_true")
    gd.set_defaults(func=cmd_discover)

    en = sub.add_parser("enrich", help="Fetch full JDs for discovered jobs")
    en.add_argument("--limit", type=int, default=50)
    en.add_argument("--headless", action="store_true", help="Hide the browser")
    en.set_defaults(func=cmd_enrich)

    tl = sub.add_parser("tailor", help="Generate a JD-tailored resume for a job")
    tl.add_argument("job_id", type=int)
    tl.set_defaults(func=cmd_tailor)

    cv = sub.add_parser("cover", help="Generate a cover letter for a job")
    cv.add_argument("job_id", type=int)
    cv.set_defaults(func=cmd_cover)

    s = sub.add_parser("score", help="LLM-score every pending job × every variant")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(func=cmd_score)

    t = sub.add_parser("top", help="Show top matches")
    t.add_argument("--min-score", type=int, default=70)
    t.add_argument("--limit", type=int, default=10)
    t.set_defaults(func=cmd_top)

    sub.add_parser("profiles", help="List saved search profiles").set_defaults(func=cmd_profiles)

    ap = sub.add_parser("add-profile", help="Add a saved search profile")
    ap.add_argument("--name", required=True)
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--location", required=True)
    ap.add_argument("--pages", type=int, default=1)
    ap.set_defaults(func=cmd_add_profile)

    rc = sub.add_parser("run-cycle", help="Discovery+scoring for all active profiles")
    rc.add_argument("--headless", action="store_true", help="Hide the browser")
    rc.set_defaults(func=cmd_run_cycle)

    eb = sub.add_parser("embed", help="Embed jobs for semantic search (Postgres only)")
    eb.add_argument("--limit", type=int, default=200)
    eb.set_defaults(func=cmd_embed)

    sm = sub.add_parser("semantic", help="Semantic job search (Postgres only)")
    sm.add_argument("query")
    sm.add_argument("--limit", type=int, default=10)
    sm.set_defaults(func=cmd_semantic)

    rp = sub.add_parser("report", help="Print (and optionally send) the daily report")
    rp.add_argument("--send", action="store_true", help="Send to the configured channel")
    rp.set_defaults(func=cmd_report)

    sub.add_parser("worker", help="Start the background worker (APScheduler)").set_defaults(func=cmd_worker)

    sa = sub.add_parser("serve-api", help="Start the REST API (FastAPI, 127.0.0.1)")
    sa.add_argument("--host", default="127.0.0.1")
    sa.add_argument("--port", type=int, default=8000)
    sa.set_defaults(func=cmd_serve_api)

    sub.add_parser("serve-mcp", help="Start the MCP server (stdio)").set_defaults(func=cmd_serve_mcp)

    db = sub.add_parser("db", help="Run a quick raw SQL SELECT against jobhunt.db")
    db.add_argument("sql")
    db.set_defaults(func=cmd_db)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
