"""Tests for the home_status service: empty DB baseline and seeded-data assertions."""
from __future__ import annotations

from job_hunt.enums import JobState
from job_hunt.services.home import home_status
from job_hunt.storage import repo

# ---------- helpers ----------


def _seed_job(db, *, title: str, h: str | None = None) -> int:
    """Insert a minimal job row and return its id."""
    job_id = db.insert_job_if_new(
        dedup_hash=h or title.lower().replace(" ", "-"),
        source="naukri",
        source_job_id=None,
        title=title,
        company="TestCo",
        location="remote",
        description="stub",
        apply_url="https://example.com/job",
        posted_date=None,
    )
    assert job_id is not None
    return job_id


def _seed_variant(db) -> int:
    """Insert a minimal résumé variant and return its id."""
    return db.upsert_resume_variant(
        slug="base-py",
        source_path="/x.tex",
        parsed={"headline": "Backend", "skills": {"languages": ["python"]}},
        tags=["python"],
    )


# ---------- empty DB baseline ----------


def test_empty_db_setup_all_false(tmp_db):
    """On an empty database every setup flag is False and watchlist_count is 0."""
    result = home_status()
    setup = result["setup"]
    assert setup["resume"] is False
    assert setup["applicant"] is False
    assert setup["context"] is False
    assert setup["search_prefs"] is False
    assert setup["apply_policy"] is False
    assert setup["watchlist_count"] == 0


def test_empty_db_activity_all_zero(tmp_db):
    """On an empty database every activity count is 0."""
    result = home_status()
    activity = result["activity"]
    assert activity["total_jobs"] == 0
    assert activity["new_to_review"] == 0
    assert activity["ready_to_apply"] == 0
    assert activity["applications"] == 0


# ---------- seeded-data assertions ----------


def test_resume_flag_flips_when_variant_added(tmp_db):
    """setup.resume becomes True once a résumé variant exists."""
    _seed_variant(tmp_db)
    assert home_status()["setup"]["resume"] is True


def test_applicant_flag_flips_on_first_name(tmp_db):
    """setup.applicant becomes True when the profile has a first_name."""
    repo.set_applicant_profile(fields={"first_name": "Alice"})
    assert home_status()["setup"]["applicant"] is True


def test_applicant_flag_flips_on_email(tmp_db):
    """setup.applicant becomes True when the profile has an email."""
    repo.set_applicant_profile(fields={"email": "alice@example.com"})
    assert home_status()["setup"]["applicant"] is True


def test_context_flag_flips_when_set(tmp_db):
    """setup.context becomes True when the user context has content."""
    repo.set_user_context(content="I am a backend engineer", fmt="md")
    assert home_status()["setup"]["context"] is True


def test_search_prefs_flag_flips_when_set(tmp_db):
    """setup.search_prefs becomes True when search prefs have content."""
    repo.set_search_prefs(content="Python backend roles, remote")
    assert home_status()["setup"]["search_prefs"] is True


def test_apply_policy_flag_flips_on_min_score(tmp_db):
    """setup.apply_policy becomes True when min_fit_score > 0."""
    repo.set_apply_policy({"min_fit_score": 70, "must_have": [], "avoid": [],
                           "seniority": "", "remote_only": False})
    assert home_status()["setup"]["apply_policy"] is True


def test_apply_policy_flag_flips_on_must_have(tmp_db):
    """setup.apply_policy becomes True when must_have is non-empty."""
    repo.set_apply_policy({"min_fit_score": 0, "must_have": ["python"], "avoid": [],
                           "seniority": "", "remote_only": False})
    assert home_status()["setup"]["apply_policy"] is True


def test_watchlist_count_reflects_added_entries(tmp_db):
    """setup.watchlist_count matches the number of watchlist rows inserted."""
    repo.add_watch(company="Stripe", ats="greenhouse", board_token="stripe")
    repo.add_watch(company="Notion", ats="lever", board_token="notion")
    assert home_status()["setup"]["watchlist_count"] == 2


def test_total_jobs_counts_all_jobs(tmp_db):
    """activity.total_jobs reflects every job row regardless of state."""
    _seed_job(tmp_db, title="Job A", h="job-a")
    _seed_job(tmp_db, title="Job B", h="job-b")
    assert home_status()["activity"]["total_jobs"] == 2


def test_new_to_review_counts_scored_jobs(tmp_db):
    """activity.new_to_review counts only jobs in scored/tailoring_ready/drafted/review_pending."""
    jid1 = _seed_job(tmp_db, title="Scored Job", h="scored-1")
    jid2 = _seed_job(tmp_db, title="Discovered Job", h="discovered-1")
    jid3 = _seed_job(tmp_db, title="Applied Job", h="applied-1")
    tmp_db.set_job_state(jid1, JobState.SCORED)
    tmp_db.set_job_state(jid2, JobState.DISCOVERED)
    tmp_db.set_job_state(jid3, JobState.APPLIED)

    result = home_status()
    assert result["activity"]["new_to_review"] == 1


def test_new_to_review_includes_review_pending(tmp_db):
    """activity.new_to_review counts REVIEW_PENDING jobs as well."""
    jid = _seed_job(tmp_db, title="Review Pending Job", h="rp-1")
    tmp_db.set_job_state(jid, JobState.REVIEW_PENDING)
    assert home_status()["activity"]["new_to_review"] == 1


def test_applications_count_reflects_inserted_rows(tmp_db):
    """activity.applications matches the number of application rows."""
    vid = _seed_variant(tmp_db)
    jid1 = _seed_job(tmp_db, title="App Job 1", h="app-1")
    jid2 = _seed_job(tmp_db, title="App Job 2", h="app-2")
    repo.record_application(job_id=jid1, variant_id=vid, cover_letter="cl1")
    repo.record_application(job_id=jid2, variant_id=vid, cover_letter="cl2")
    assert home_status()["activity"]["applications"] == 2


def test_combined_seed_all_flags_and_counts(tmp_db):
    """Full combined seed: all setup flags True, activity counts match seeds."""
    # setup seeds
    vid = _seed_variant(tmp_db)
    repo.set_applicant_profile(fields={"first_name": "Bob"})
    repo.set_user_context(content="experienced backend", fmt="md")
    repo.set_search_prefs(content="backend remote")
    repo.set_apply_policy({"min_fit_score": 65, "must_have": [], "avoid": [],
                           "seniority": "", "remote_only": False})
    repo.add_watch(company="Stripe", ats="greenhouse", board_token="stripe")

    # activity seeds
    jid_scored = _seed_job(tmp_db, title="Python BE", h="py-be")
    jid_applied = _seed_job(tmp_db, title="Go BE", h="go-be")
    tmp_db.set_job_state(jid_scored, JobState.SCORED)
    tmp_db.set_job_state(jid_applied, JobState.APPLIED)
    repo.record_application(job_id=jid_applied, variant_id=vid, cover_letter="cl")
    # score the scored job so it can surface in ready_to_apply
    tmp_db.write_score(job_id=jid_scored, variant_id=vid, fit_score=80, reasoning="ok")

    result = home_status()
    setup = result["setup"]
    activity = result["activity"]

    assert setup["resume"] is True
    assert setup["applicant"] is True
    assert setup["context"] is True
    assert setup["search_prefs"] is True
    assert setup["apply_policy"] is True
    assert setup["watchlist_count"] == 1

    assert activity["total_jobs"] == 2
    assert activity["new_to_review"] == 1
    assert activity["applications"] == 1
    assert activity["ready_to_apply"] >= 1
