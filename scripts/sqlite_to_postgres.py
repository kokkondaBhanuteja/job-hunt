"""One-shot migration of existing SQLite data into Postgres.

The v0 toolkit stored everything in data/jobhunt.db. This copies that data into the
Postgres datastore, remapping primary keys so foreign keys stay intact (IDENTITY
columns assign fresh ids; we translate child rows through old→new maps).

Usage:
    uv run python scripts/sqlite_to_postgres.py            # copy data/jobhunt.db → $DATABASE_URL
    uv run python scripts/sqlite_to_postgres.py --truncate # wipe target tables first

Idempotency: by default it APPENDS. Re-running without --truncate will duplicate
rows (dedup_hash/slug uniqueness will instead raise). Use --truncate for a clean redo.
"""
from __future__ import annotations

import argparse
import json
import sys

from psycopg.types.json import Jsonb

from job_hunt.storage import db, pg


def _jsonb(text_value):
    """SQLite stores JSON as text; Postgres wants JSONB. None passes through."""
    if text_value is None:
        return None
    return Jsonb(json.loads(text_value) if isinstance(text_value, str) else text_value)


def _rows(sconn, table):
    return sconn.execute(f"SELECT * FROM {table}").fetchall()


def migrate(*, truncate: bool) -> dict[str, int]:
    db.init_db()   # ensure source schema exists (no-op if present)
    pg.init_db()   # ensure target schema (applies migrations)

    counts: dict[str, int] = {}
    with db.connect() as sconn, pg.connect() as pconn:
        if truncate:
            pconn.execute(
                "TRUNCATE llm_calls, runs, outreach, contacts, applications, "
                "scores, jobs, resume_variants RESTART IDENTITY CASCADE"
            )

        # --- parents first; build old→new id maps ---
        variant_map: dict[int, int] = {}
        for r in _rows(sconn, "resume_variants"):
            new_id = pconn.execute(
                "INSERT INTO resume_variants (slug, source_path, parsed_json, tags, updated_at) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (r["slug"], r["source_path"], _jsonb(r["parsed_json"]),
                 _jsonb(r["tags"]), r["updated_at"]),
            ).fetchone()["id"]
            variant_map[r["id"]] = new_id
        counts["resume_variants"] = len(variant_map)

        job_map: dict[int, int] = {}
        for r in _rows(sconn, "jobs"):
            new_id = pconn.execute(
                "INSERT INTO jobs (dedup_hash, source, source_job_id, title, company, "
                "location, description, apply_url, posted_date, discovered_at, raw_payload, status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (r["dedup_hash"], r["source"], r["source_job_id"], r["title"], r["company"],
                 r["location"], r["description"], r["apply_url"], r["posted_date"],
                 r["discovered_at"], _jsonb(r["raw_payload"]), r["status"]),
            ).fetchone()["id"]
            job_map[r["id"]] = new_id
        counts["jobs"] = len(job_map)

        contact_map: dict[int, int] = {}
        for r in _rows(sconn, "contacts"):
            new_id = pconn.execute(
                "INSERT INTO contacts (company, name, role, persona, email_guess, "
                "linkedin_url, notes, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (r["company"], r["name"], r["role"], r["persona"], r["email_guess"],
                 r["linkedin_url"], r["notes"], r["created_at"]),
            ).fetchone()["id"]
            contact_map[r["id"]] = new_id
        counts["contacts"] = len(contact_map)

        # --- children, FKs translated through the maps ---
        n = 0
        for r in _rows(sconn, "scores"):
            pconn.execute(
                "INSERT INTO scores (job_id, variant_id, fit_score, confidence, reasoning, scored_at) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (job_map[r["job_id"]], variant_map[r["variant_id"]], r["fit_score"],
                 r["confidence"], r["reasoning"], r["scored_at"]),
            )
            n += 1
        counts["scores"] = n

        n = 0
        for r in _rows(sconn, "applications"):
            pconn.execute(
                "INSERT INTO applications (job_id, variant_id, cover_letter, applied_at, "
                "reply_type, reply_notes) VALUES (%s,%s,%s,%s,%s,%s)",
                (job_map[r["job_id"]], variant_map[r["variant_id"]], r["cover_letter"],
                 r["applied_at"], r["reply_type"], r["reply_notes"]),
            )
            n += 1
        counts["applications"] = n

        n = 0
        for r in _rows(sconn, "outreach"):
            pconn.execute(
                "INSERT INTO outreach (contact_id, job_id, template_slug, subject, body, "
                "mailto_url, drafted_at, sent_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (contact_map[r["contact_id"]], job_map.get(r["job_id"]) if r["job_id"] else None,
                 r["template_slug"], r["subject"], r["body"], r["mailto_url"],
                 r["drafted_at"], r["sent_at"]),
            )
            n += 1
        counts["outreach"] = n

        n = 0
        for r in _rows(sconn, "runs"):
            pconn.execute(
                "INSERT INTO runs (started_at, finished_at, sources, jobs_found, jobs_new, errors) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (r["started_at"], r["finished_at"], _jsonb(r["sources"]),
                 r["jobs_found"], r["jobs_new"], _jsonb(r["errors"])),
            )
            n += 1
        counts["runs"] = n

        # llm_calls only exists on DBs created after the Phase 0 migration.
        n = 0
        try:
            llm_rows = _rows(sconn, "llm_calls")
        except Exception:
            llm_rows = []
        for r in llm_rows:
            pconn.execute(
                "INSERT INTO llm_calls (task, provider, model, prompt, response, prompt_tokens, "
                "completion_tokens, cost, latency_ms, ok, error, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (r["task"], r["provider"], r["model"], r["prompt"], r["response"],
                 r["prompt_tokens"], r["completion_tokens"], r["cost"], r["latency_ms"],
                 bool(r["ok"]), r["error"], r["created_at"]),
            )
            n += 1
        counts["llm_calls"] = n

    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description="Copy SQLite jobhunt.db → Postgres")
    ap.add_argument("--truncate", action="store_true", help="wipe target tables first")
    args = ap.parse_args()

    print(f"Source: {db.describe()}")
    print(f"Target: {pg.describe()}")
    counts = migrate(truncate=args.truncate)
    print("Copied:")
    for table, n in counts.items():
        print(f"  {table:<16} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
