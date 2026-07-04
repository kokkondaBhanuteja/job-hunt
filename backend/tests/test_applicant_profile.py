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
