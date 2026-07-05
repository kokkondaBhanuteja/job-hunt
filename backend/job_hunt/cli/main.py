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

# Ollama-provider liveness (selfcheck)
from job_hunt.llm.providers.ollama import installed_models, is_alive
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


def cmd_brief(args: argparse.Namespace) -> int:
    """Generate an interview-prep brief for a job."""
    result = services.brief_for_job(args.job_id)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    print(json.dumps(result, indent=2))
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    """Show which JD requirements the résumé meets/misses for a scored job."""
    result = services.explain_score(args.job_id, force=args.force)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    print(f"Score explanation for job {args.job_id} (fit_score={result.get('fit_score')})\n")
    print("MATCHED:")
    for item in result.get("matched", []):
        print(f"  + {item['requirement']}: {item['evidence']}")
    print("\nMISSING:")
    for item in result.get("missing", []):
        print(f"  - {item['requirement']}: {item['why_it_matters']}")
    print("\nSUGGESTIONS:")
    for s in result.get("suggestions", []):
        print(f"  * {s}")
    return 0


def cmd_skill_gap(args: argparse.Namespace) -> int:
    """Show the most common skill gaps across all scored jobs."""
    result = services.skill_gap(limit=args.limit)
    gaps = result.get("gaps", [])
    if not gaps:
        print("(no skill-gap data yet — run `hunt explain` on some jobs first)")
        return 0
    print(f"Top skill gaps ({result['considered']} learnings considered):")
    for g in gaps:
        print(f"  {g['count']:>3}x  {g['skill']}")
    return 0


def cmd_draft(args: argparse.Namespace) -> int:
    """Generate a thank-you, follow-up, or negotiation message for a job."""
    result = services.draft_message_for_job(args.job_id, args.kind)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    print(f"{args.kind} draft #{result['draft_id']} for job {args.job_id}:\n")
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


def cmd_ready(args: argparse.Namespace) -> int:
    """Show jobs that pass the apply policy — for human review, never auto-applies."""
    rows = services.list_ready_to_apply(limit=args.limit)
    if not rows:
        print("no jobs match your apply policy")
        return 0
    for r in rows:
        print(f"  {r['job_id']} · {r['best_score']} · {r['title']} · {r['company']}")
    return 0


def cmd_profiles(_: argparse.Namespace) -> int:
    rows = services.list_profiles()
    if not rows:
        print("(no search profiles — add one with `hunt add-profile`)")
        return 0
    for r in rows:
        flag = "on " if r["enabled"] else "off"
        print(
            f"  [{r['id']:>2}] {flag} {r['name']:<20} "
            f"{r['keywords']!r} @ {r['location']!r} pages={r['pages']}"
        )
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
    from job_hunt.settings import validate_settings
    from job_hunt.worker.scheduler import run as worker_run

    validate_settings()  # fail fast on a bad DB_BACKEND / cap / provider / active-hours
    worker_run()
    return 0


def cmd_serve_api(args: argparse.Namespace) -> int:
    """Start the REST API (FastAPI) bound to localhost with a bearer token."""
    import os
    import secrets

    import uvicorn

    from job_hunt.settings import validate_settings

    validate_settings()  # fail fast on misconfig before binding the port
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


def cmd_notify_test(_: argparse.Namespace) -> int:
    """Send a test message through the configured notification channel."""
    result = services.send_test_notification()
    channel = result["channel"]
    if channel == "none":
        print("NOTIFY_CHANNEL is 'none' — set it to 'telegram' plus TELEGRAM_BOT_TOKEN "
              "and TELEGRAM_CHAT_ID in backend/.env.local, then retry.")
        return 1
    if result["sent"]:
        print(f"sent via {channel} ✓ — check your chat")
        return 0
    print(f"send failed via {channel} — verify the token / chat id are correct")
    return 1


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


def cmd_context(args: argparse.Namespace) -> int:
    """Set the user career context from a file, or show the current one."""
    if args.file:
        content = Path(args.file).read_text(encoding="utf-8")
        result = services.set_context(content, args.format)
        if "error" in result:
            print(f"!! {result['error']}")
            return 1
        print(f"context set ({result['format']}, {result['length']} chars)")
        return 0
    ctx = services.get_context()
    if not ctx.get("content"):
        print("(no context set — pass a .md/.json file to set one)")
        return 0
    print(f"# context ({ctx['format']}, updated {ctx['updated_at']})\n")
    print(ctx["content"])
    return 0


def cmd_search_prefs(args: argparse.Namespace) -> int:
    """Set job-search preferences from a .md file, or show the stored prefs."""
    if args.file:
        content = Path(args.file).read_text(encoding="utf-8")
        result = services.set_search_prefs(content)
        if "error" in result:
            print(f"!! {result['error']}")
            return 1
        print(f"search prefs set ({result['profiles_created']} profile(s) created)")
        return 0
    prefs = services.get_search_prefs()
    if not prefs.get("content"):
        print("(no search prefs set — pass a .md file to set one)")
        return 0
    print(f"# search prefs (updated {prefs['updated_at']})\n")
    print(prefs["content"])
    return 0


def cmd_apply_fill(args: argparse.Namespace) -> int:
    """Open a job's ATS form, auto-fill it, and stop at the review screen."""
    result = services.prepare_form_fill(args.job_id)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    print(f"[{result['ats']}] filled {len(result['filled'])} field(s); "
          f"{len(result['unfilled'])} need you: {result['unfilled']}")
    print(f"review & submit: {result['review_url']}")
    return 0


def cmd_applicant(args: argparse.Namespace) -> int:
    """Set an applicant-profile field (--set key=value ...) or show the current profile."""
    if args.set:
        fields = dict(pair.split("=", 1) for pair in args.set)
        result = services.set_applicant(fields)
        print(result.get("error") or f"set {result['fields']} field(s)")
        return 1 if "error" in result else 0
    for k, v in services.get_applicant().items():
        if v is not None:
            print(f"{k}: {v}")
    return 0


def cmd_email_sync(args: argparse.Namespace) -> int:
    """Sync inbox from IMAP and structure pending emails with the LLM."""
    result = services.sync_inbox(mailbox=args.mailbox, limit=args.limit)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    sync_result = result
    struct = services.structure_pending(limit=args.structure_limit)
    if "error" in struct:
        print(f"!! {struct['error']}")
        return 1
    print(
        f"fetched={sync_result['fetched']} new={sync_result['new']} "
        f"structured={struct['structured']}"
    )
    return 0


def cmd_email_list(args: argparse.Namespace) -> int:
    """List emails from the inbox with optional filtering."""
    rows = services.list_inbox(
        category=args.category if args.category else None,
        action_state=args.state if args.state else None,
        limit=args.limit,
    )
    if not rows:
        print("(no emails)")
        return 0
    for r in rows:
        email_id = r.get("id", "?")
        category = r.get("category", "?")
        from_addr = r.get("from_addr", "?")
        subject = r.get("subject", "?")
        print(f"[{email_id:>4}] {category:<10} {from_addr:<30} {subject}")
    return 0


def cmd_email_show(args: argparse.Namespace) -> int:
    """Show a single email by ID."""
    result = services.get_email(args.email_id)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_email_action(args: argparse.Namespace) -> int:
    """Propose or confirm an email action (IMAP write requires --confirm)."""
    if args.confirm:
        result = services.confirm_action(args.email_id, confirm=True)
    else:
        result = services.propose_action(args.email_id, args.kind, label=args.label)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_email_dismiss(args: argparse.Namespace) -> int:
    """Dismiss the pending proposed action on an email."""
    result = services.dismiss_action(args.email_id)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_naukri_refresh(_: argparse.Namespace) -> int:
    """Draft an optimized Naukri headline, summary, and skills (paste it yourself)."""
    result = services.draft_profile_refresh()
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    print("--- Naukri Profile Draft (paste this into your Naukri profile yourself) ---\n")
    print(f"Headline:\n  {result['headline']}\n")
    print(f"Summary:\n  {result['summary']}\n")
    skills = result.get("skills") or []
    if skills:
        print(f"Skills:\n  {', '.join(skills)}\n")
    print("--------------------------------------------------------------------------")
    return 0


def cmd_post(args: argparse.Namespace) -> int:
    """Draft a new tech post grounded in a current trending topic."""
    result = services.generate_post(topic=args.topic if args.topic else None)
    if "error" in result:
        print(f"!! {result['error']}")
        return 1
    print(f"[post_id={result['post_id']}] topic: {result['topic']}")
    print(f"source: {result.get('source_url') or '(none)'}\n")
    print(result["body"])
    return 0


def cmd_posts(args: argparse.Namespace) -> int:
    """List stored post drafts."""
    rows = services.list_posts(status=args.status if args.status else None)
    if not rows:
        print("(no posts)")
        return 0
    for r in rows:
        post_id = r.get("id", "?")
        status = r.get("status", "?")
        topic = r.get("topic") or "(no topic)"
        print(f"[{post_id:>4}] {status:<10} {topic}")
    return 0


# ---------- argparse wiring ----------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hunt", description="Personal job-hunt toolkit")
    sub = p.add_subparsers(dest="command", required=True)

    sc = sub.add_parser("selfcheck", help="Verify Ollama + DB are ready")
    sc.set_defaults(func=cmd_selfcheck)

    pr = sub.add_parser("parse-resume", help="Parse data/resumes/ vault into DB")
    pr.set_defaults(func=cmd_parse_resume)

    lg = sub.add_parser("login", help="One-time login that persists cookies for a site")
    lg.add_argument("site", choices=["naukri", "foundit"])
    lg.set_defaults(func=cmd_login)

    d = sub.add_parser(
        "discover-naukri",
        help="Crawl Naukri.com (RPA-style — visible browser by default)",
    )
    d.add_argument("--keyword", required=True)
    d.add_argument("--location", required=True)
    d.add_argument("--pages", type=int, default=1)
    d.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    d.add_argument(
        "--headless",
        action="store_true",
        help="Hide the browser (only after a successful warm run)",
    )
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

    brf = sub.add_parser("brief", help="Generate an interview-prep brief for a job")
    brf.add_argument("job_id", type=int)
    brf.set_defaults(func=cmd_brief)

    ex = sub.add_parser("explain", help="Explain why a job scored the way it did")
    ex.add_argument("job_id", type=int)
    ex.add_argument("--force", action="store_true", help="Re-run LLM even if cached")
    ex.set_defaults(func=cmd_explain)

    sg = sub.add_parser("skill-gap", help="Show most common skill gaps across all jobs")
    sg.add_argument("--limit", type=int, default=20)
    sg.set_defaults(func=cmd_skill_gap)

    dr = sub.add_parser("draft", help="Generate a thank-you, follow-up, or negotiation message")
    dr.add_argument("kind", choices=["thank_you", "follow_up", "negotiation"])
    dr.add_argument("job_id", type=int)
    dr.set_defaults(func=cmd_draft)

    s = sub.add_parser("score", help="LLM-score every pending job × every variant")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(func=cmd_score)

    t = sub.add_parser("top", help="Show top matches")
    t.add_argument("--min-score", type=int, default=70)
    t.add_argument("--limit", type=int, default=10)
    t.set_defaults(func=cmd_top)

    rd = sub.add_parser(
        "ready", help="Show jobs passing the apply policy (human reviews, never auto-applies)"
    )
    rd.add_argument("--limit", type=int, default=50)
    rd.set_defaults(func=cmd_ready)

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

    nt = sub.add_parser("notify-test", help="Send a test message via the configured channel")
    nt.set_defaults(func=cmd_notify_test)

    wk = sub.add_parser("worker", help="Start the background worker (APScheduler)")
    wk.set_defaults(func=cmd_worker)

    sa = sub.add_parser("serve-api", help="Start the REST API (FastAPI, 127.0.0.1)")
    sa.add_argument("--host", default="127.0.0.1")
    sa.add_argument("--port", type=int, default=8000)
    sa.set_defaults(func=cmd_serve_api)

    nr = sub.add_parser(
        "naukri-refresh",
        help="Draft an optimized Naukri headline/summary/skills (you paste it yourself)",
    )
    nr.set_defaults(func=cmd_naukri_refresh)

    pt = sub.add_parser("post", help="Draft a new tech post grounded in a current trending topic")
    pt.add_argument("--topic", default=None, help="specific topic (omit to auto-pick from HN/dev.to)")
    pt.set_defaults(func=cmd_post)

    pts = sub.add_parser("posts", help="List stored post drafts")
    pts.add_argument("--status", default=None, help="filter by status (draft/posted/dismissed)")
    pts.set_defaults(func=cmd_posts)

    mc = sub.add_parser("serve-mcp", help="Start the MCP server (stdio)")
    mc.set_defaults(func=cmd_serve_mcp)

    db = sub.add_parser("db", help="Run a quick raw SQL SELECT against jobhunt.db")
    db.add_argument("sql")
    db.set_defaults(func=cmd_db)

    cx = sub.add_parser("context", help="Set/show the career context injected into AI prompts")
    cx.add_argument("file", nargs="?", help="path to a .md/.json context file (omit to show)")
    cx.add_argument("--format", choices=["md", "json"], default="md")
    cx.set_defaults(func=cmd_context)

    sp_cmd = sub.add_parser(
        "search-prefs", help="Set/show job-search preferences (parsed into search profiles)"
    )
    sp_cmd.add_argument("file", nargs="?", help="path to a .md preferences file (omit to show)")
    sp_cmd.set_defaults(func=cmd_search_prefs)

    af = sub.add_parser("apply-fill", help="Auto-fill a job's ATS form (stops at review)")
    af.add_argument("job_id", type=int)
    af.set_defaults(func=cmd_apply_fill)

    ap = sub.add_parser("applicant", help="Set/show standing application answers")
    ap.add_argument("--set", nargs="*", metavar="key=value", help="fields to set")
    ap.set_defaults(func=cmd_applicant)

    em = sub.add_parser("email", help="Email triage and inbox management")
    em_sub = em.add_subparsers(dest="email_command", required=True)

    es = em_sub.add_parser("sync", help="Sync inbox from IMAP and structure emails")
    es.add_argument("--mailbox", default="INBOX", help="mailbox to sync (default: INBOX)")
    es.add_argument("--limit", type=int, default=200, help="max emails to fetch (default: 200)")
    es.add_argument(
        "--structure-limit",
        type=int,
        default=50,
        help="max emails to structure (default: 50)",
    )
    es.set_defaults(func=cmd_email_sync)

    el = em_sub.add_parser("list", help="List emails with optional filtering")
    el.add_argument(
        "--category",
        help="filter by category (e.g., recruiter_outreach, rejection, other)",
    )
    el.add_argument("--state", help="filter by action_state")
    el.add_argument("--limit", type=int, default=100, help="max rows to return (default: 100)")
    el.set_defaults(func=cmd_email_list)

    esh = em_sub.add_parser("show", help="Show a single email by ID")
    esh.add_argument("email_id", type=int, help="email ID to display")
    esh.set_defaults(func=cmd_email_show)

    ea = em_sub.add_parser("action", help="Propose or confirm an email action")
    ea.add_argument("email_id", type=int, help="email ID")
    ea.add_argument(
        "--kind",
        choices=["draft_reply", "apply_label", "archive"],
        required=True,
        help="action kind: draft_reply, apply_label, or archive",
    )
    ea.add_argument("--label", help="label name (required for apply_label kind)")
    ea.add_argument(
        "--confirm",
        action="store_true",
        help="confirm and execute the proposed action (opens IMAP for write)",
    )
    ea.set_defaults(func=cmd_email_action)

    edm = em_sub.add_parser("dismiss", help="Dismiss the pending action on an email")
    edm.add_argument("email_id", type=int, help="email ID")
    edm.set_defaults(func=cmd_email_dismiss)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
