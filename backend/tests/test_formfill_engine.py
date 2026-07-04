"""_fill_page drives a FormPage: fills what it can, records what it can't, never submits."""
from __future__ import annotations

import asyncio

from job_hunt.apply.formfill import _fill_page, _fill_page_async


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


def test_prepare_form_fill_uses_profile_and_returns_summary(tmp_db, monkeypatch):
    from job_hunt.apply import formfill
    from job_hunt.storage import repo

    jid = tmp_db.insert_job_if_new(
        dedup_hash="gh", source="greenhouse", source_job_id=None, title="BE",
        company="Acme", location="remote", description="d",
        apply_url="https://boards.greenhouse.io/acme/jobs/1", posted_date=None,
        emit_discovered=False,
    )
    repo.set_applicant_profile(fields={"first_name": "Bhanu", "email": "a@b.in"})

    captured = {}

    class _FakeOrcPage:
        def __init__(self): self.text = {}
        def has(self, s): return True
        def fill_text(self, s, v): self.text[s] = v
        def select_option(self, s, v): self.text[s] = v
        def set_file(self, s, p): self.text[s] = p
        def set_checkbox(self, s, c): self.text[s] = str(c)
        def highlight(self, s): captured["highlighted"] = s

    def factory(url):
        captured["url"] = url
        return _FakeOrcPage()

    result = formfill.prepare_form_fill(jid, page_factory=factory)
    assert result["ats"] == "greenhouse"
    assert "a@b.in" in captured["url"] or result["review_url"].startswith("https://boards")
    assert "input#email" in result["filled"] or "input#first_name" in result["filled"]


def test_prepare_form_fill_unknown_ats_errors(tmp_db):
    from job_hunt.apply import formfill
    jid = tmp_db.insert_job_if_new(
        dedup_hash="nk", source="naukri", source_job_id=None, title="BE", company="Acme",
        location="blr", description="d", apply_url="https://naukri.com/j/1",
        posted_date=None, emit_discovered=False,
    )
    assert "error" in formfill.prepare_form_fill(jid)


# ---------------------------------------------------------------------------
# Async fill loop tests — no real browser; driven via asyncio.run (no pytest-asyncio)
# ---------------------------------------------------------------------------


class _FakeAsyncPage:
    """Async fake page: records fills; only selectors in `present` 'exist'."""

    def __init__(self, present: set[str]):
        self.present = present
        self.text: dict[str, str] = {}
        self.files: dict[str, str] = {}
        self.highlighted: list[str] = []
        self.submitted = False

    async def query_selector(self, s: str) -> object | None:
        return object() if s in self.present else None

    async def fill(self, s: str, v: str) -> None:
        self.text[s] = v

    async def select_option(self, s: str, *, label: str) -> None:
        self.text[s] = label

    async def set_input_files(self, s: str, p: str) -> None:
        self.files[s] = p

    async def set_checked(self, s: str, c: bool) -> None:
        self.text[s] = str(c)

    async def eval_on_selector(self, s: str, _js: str) -> None:
        self.highlighted.append(s)


def test_fill_page_async_fills_present_fields_and_records_unfilled():
    page = _FakeAsyncPage(present={"#first_name", "#email", "#resume",
                                   "#missing_required", "#submit"})
    result = asyncio.run(_fill_page_async(page, PROFILE, DATA))
    assert page.text["#first_name"] == "Bhanu"
    assert page.text["#email"] == "a@b.in"
    assert page.files["#resume"] == "/r.pdf"
    assert "#missing_required" in result["unfilled"]
    assert "#phone" not in result["unfilled"]
    assert set(result["filled"]) == {"#first_name", "#email", "#resume"}


def test_fill_page_async_skips_optional_missing():
    # #phone is optional and has no value in DATA; it must not appear in unfilled
    page = _FakeAsyncPage(present={"#phone"})
    result = asyncio.run(_fill_page_async(page, PROFILE, DATA))
    assert "#phone" not in result["unfilled"]


def test_fill_page_async_never_submits_highlights_submit():
    page = _FakeAsyncPage(present={"#first_name", "#email", "#resume",
                                   "#missing_required", "#submit"})
    asyncio.run(_fill_page_async(page, PROFILE, DATA))
    assert page.submitted is False
    assert page.highlighted == ["#submit"]
