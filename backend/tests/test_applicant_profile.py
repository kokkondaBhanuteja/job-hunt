"""applicant_profile singleton: store the standing answers forms re-ask."""
from __future__ import annotations

from job_hunt.storage import repo


def test_set_and_get_applicant_profile(tmp_db):
    repo.set_applicant_profile(fields={"first_name": "Bhanu", "email": "a@b.in",
                                        "notice_period": "30 days"})
    row = repo.get_applicant_profile()
    assert row["first_name"] == "Bhanu" and row["notice_period"] == "30 days"


def test_get_applicant_profile_none_when_unset(tmp_db):
    assert repo.get_applicant_profile() is None


def test_set_applicant_profile_upserts_single_row(tmp_db):
    repo.set_applicant_profile(fields={"first_name": "A"})
    repo.set_applicant_profile(fields={"first_name": "B", "phone": "+91"})
    row = repo.get_applicant_profile()
    assert row["first_name"] == "B" and row["phone"] == "+91"


def test_service_set_and_get_applicant(tmp_db):
    from job_hunt import services
    r = services.set_applicant({"first_name": "Bhanu", "email": "a@b.in"})
    assert r["ok"] is True and r["fields"] == 2
    got = services.get_applicant()
    assert got["first_name"] == "Bhanu"


def test_service_set_applicant_rejects_unknown_field(tmp_db):
    from job_hunt import services
    assert "error" in services.set_applicant({"nope": "x"})


def test_service_get_applicant_all_null_when_unset(tmp_db):
    from job_hunt import services
    assert services.get_applicant()["first_name"] is None
