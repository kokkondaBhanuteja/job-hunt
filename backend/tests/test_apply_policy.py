"""Tests for the apply-policy service: storage round-trip, filtering, and search_prefs integration."""
from __future__ import annotations

from job_hunt.services import apply_policy as ap_service
from job_hunt.services import search_prefs
from job_hunt.storage import repo

# ---------- helpers ----------


def _seed_job(db, *, title: str, description: str = "", h: str | None = None) -> int:
    """Insert a job and return its id. Uses title as fallback dedup hash."""
    job_id = db.insert_job_if_new(
        dedup_hash=h or title.lower().replace(" ", "-"),
        source="naukri",
        source_job_id=None,
        title=title,
        company="TestCorp",
        location="remote",
        description=description,
        apply_url="https://example.com/job",
        posted_date=None,
    )
    assert job_id is not None
    return job_id


def _seed_variant(db) -> int:
    return db.upsert_resume_variant(
        slug="backend-py",
        source_path="/x.tex",
        parsed={"headline": "Backend", "skills": {"languages": ["python"]}},
        tags=["python"],
    )


def _score(db, job_id: int, variant_id: int, score: int) -> None:
    db.write_score(
        job_id=job_id,
        variant_id=variant_id,
        fit_score=score,
        reasoning="stub",
    )


# ---------- storage round-trip ----------


def test_set_and_get_apply_policy(tmp_db):
    """set_apply_policy then get_apply_policy round-trips the dict."""
    policy = {"min_fit_score": 70, "must_have": ["python"], "avoid": ["crypto"],
              "seniority": "mid", "remote_only": True}
    repo.set_apply_policy(policy)
    stored = repo.get_apply_policy()
    assert stored == policy


def test_get_apply_policy_returns_none_when_unset(tmp_db):
    """get_apply_policy returns None when no policy has been stored."""
    assert repo.get_apply_policy() is None


def test_get_policy_returns_defaults_when_unset(tmp_db):
    """get_policy returns safe defaults when the table is empty."""
    p = ap_service.get_policy()
    assert p["min_fit_score"] == 0
    assert p["must_have"] == []
    assert p["avoid"] == []
    assert p["remote_only"] is False


# ---------- filtering ----------


def test_list_ready_filters_by_min_score(tmp_db):
    """Only jobs with score >= min_fit_score are returned."""
    vid = _seed_variant(tmp_db)
    jid_high = _seed_job(tmp_db, title="Python Backend", h="job-high")
    jid_low = _seed_job(tmp_db, title="Python Analyst", h="job-low")
    _score(tmp_db, jid_high, vid, 80)
    _score(tmp_db, jid_low, vid, 50)

    repo.set_apply_policy({"min_fit_score": 70, "must_have": [], "avoid": [],
                           "seniority": "", "remote_only": False})
    rows = ap_service.list_ready_to_apply()
    ids = {r["job_id"] for r in rows}
    assert jid_high in ids
    assert jid_low not in ids


def test_list_ready_filters_must_have(tmp_db):
    """Jobs whose text lacks a must_have keyword are excluded."""
    vid = _seed_variant(tmp_db)
    jid_py = _seed_job(tmp_db, title="Python Backend Engineer", h="job-py")
    jid_go = _seed_job(tmp_db, title="Go Backend Engineer", h="job-go")
    _score(tmp_db, jid_py, vid, 80)
    _score(tmp_db, jid_go, vid, 80)

    repo.set_apply_policy({"min_fit_score": 0, "must_have": ["python"], "avoid": [],
                           "seniority": "", "remote_only": False})
    rows = ap_service.list_ready_to_apply()
    ids = {r["job_id"] for r in rows}
    assert jid_py in ids
    assert jid_go not in ids


def test_list_ready_filters_avoid(tmp_db):
    """Jobs whose text contains an avoid keyword are excluded."""
    vid = _seed_variant(tmp_db)
    jid_ok = _seed_job(tmp_db, title="Python Backend Engineer", h="job-ok")
    jid_bad = _seed_job(tmp_db, title="Python Crypto Engineer", h="job-bad")
    _score(tmp_db, jid_ok, vid, 80)
    _score(tmp_db, jid_bad, vid, 80)

    repo.set_apply_policy({"min_fit_score": 0, "must_have": ["python"], "avoid": ["crypto"],
                           "seniority": "", "remote_only": False})
    rows = ap_service.list_ready_to_apply()
    ids = {r["job_id"] for r in rows}
    assert jid_ok in ids
    assert jid_bad not in ids


def test_list_ready_no_policy_returns_all_top_matches(tmp_db):
    """With no policy set, list_ready_to_apply returns all scored jobs (defaults: score>=0)."""
    vid = _seed_variant(tmp_db)
    jid1 = _seed_job(tmp_db, title="Backend Dev", h="job-1")
    jid2 = _seed_job(tmp_db, title="Frontend Dev", h="job-2")
    _score(tmp_db, jid1, vid, 60)
    _score(tmp_db, jid2, vid, 55)

    rows = ap_service.list_ready_to_apply()
    ids = {r["job_id"] for r in rows}
    assert jid1 in ids
    assert jid2 in ids


# ---------- search_prefs integration ----------


_STUB_WITH_POLICY = {
    "profiles": [
        {"name": "BE", "keywords": "python backend", "location": "remote", "pages": 1},
    ],
    "apply_policy": {
        "min_fit_score": 75,
        "must_have": ["python"],
        "avoid": ["blockchain"],
        "seniority": "mid",
        "remote_only": True,
    },
}


def test_set_search_prefs_stores_apply_policy(tmp_db, monkeypatch):
    """When LLM returns apply_policy, set_search_prefs persists it via repo.set_apply_policy."""
    monkeypatch.setattr(search_prefs, "chat_json", lambda *a, **k: _STUB_WITH_POLICY)
    search_prefs.set_search_prefs("I want mid-level Python backend roles, remote only, score >= 75")
    stored = repo.get_apply_policy()
    assert stored is not None
    assert stored["min_fit_score"] == 75
    assert "python" in stored["must_have"]
    assert stored["remote_only"] is True


def test_set_search_prefs_without_policy_leaves_policy_unset(tmp_db, monkeypatch):
    """When LLM returns no apply_policy, the policy singleton is untouched."""
    stub_no_policy = {
        "profiles": [{"keywords": "python backend", "location": "remote"}]
    }
    monkeypatch.setattr(search_prefs, "chat_json", lambda *a, **k: stub_no_policy)
    search_prefs.set_search_prefs("Backend roles")
    assert repo.get_apply_policy() is None
