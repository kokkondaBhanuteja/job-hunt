"""_fill_page drives a FormPage: fills what it can, records what it can't, never submits."""
from __future__ import annotations

from job_hunt.apply.formfill import _fill_page


class _FakePage:
    """Records fills; only selectors in `present` 'exist'; submit selector is never clicked."""

    def __init__(self, present: set[str]):
        self.present = present
        self.text: dict[str, str] = {}
        self.files: dict[str, str] = {}
        self.highlighted: list[str] = []
        self.submitted = False

    def has(self, selector: str) -> bool:
        return selector in self.present

    def fill_text(self, selector: str, value: str) -> None:
        self.text[selector] = value

    def select_option(self, selector: str, value: str) -> None:
        self.text[selector] = value

    def set_file(self, selector: str, path: str) -> None:
        self.files[selector] = path

    def set_checkbox(self, selector: str, checked: bool) -> None:
        self.text[selector] = str(checked)

    def highlight(self, selector: str) -> None:
        self.highlighted.append(selector)


PROFILE = {
    "ats": "greenhouse", "match": {}, "fields": [
        {"selector": "#first_name", "source": "applicant.first_name"},
        {"selector": "#email", "source": "applicant.email"},
        {"selector": "#phone", "source": "applicant.phone", "optional": True},
        {"selector": "#resume", "source": "file.resume_variant", "kind": "file"},
        {"selector": "#missing_required", "source": "applicant.years_experience"},
    ],
    "submit": {"selector": "#submit", "action": "highlight_only"},
}
DATA = {"applicant": {"first_name": "Bhanu", "email": "a@b.in"}, "resume": {},
        "context": None, "draft": {"cover": None}, "file": {"resume_variant": "/r.pdf"}}


def test_fill_page_fills_present_fields_and_records_unfilled():
    page = _FakePage(present={"#first_name", "#email", "#resume",
                              "#missing_required", "#submit"})
    result = _fill_page(page, PROFILE, DATA)
    assert page.text["#first_name"] == "Bhanu" and page.text["#email"] == "a@b.in"
    assert page.files["#resume"] == "/r.pdf"
    # required field with no data → unfilled; optional #phone → NOT unfilled
    assert "#missing_required" in result["unfilled"]
    assert "#phone" not in result["unfilled"]
    assert set(result["filled"]) == {"#first_name", "#email", "#resume"}


def test_fill_page_never_submits_and_highlights_submit():
    page = _FakePage(present={"#first_name", "#email", "#resume",
                              "#missing_required", "#submit"})
    _fill_page(page, PROFILE, DATA)
    assert page.submitted is False
    assert page.highlighted == ["#submit"]


def test_fill_page_skips_absent_selectors():
    page = _FakePage(present={"#email"})  # only email exists on the page
    result = _fill_page(page, PROFILE, DATA)
    assert result["filled"] == ["#email"]
