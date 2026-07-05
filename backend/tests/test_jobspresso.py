"""Tests for the Jobspresso plugin (RSS mocked — no network)."""
from __future__ import annotations

from job_hunt import plugins
from job_hunt.plugins import jobspresso

CANNED_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:job_listing="https://jobspresso.co/">
  <channel>
    <title>Jobspresso Remote Jobs</title>
    <item>
      <title>Senior Python Engineer</title>
      <link>https://jobspresso.co/job/1/</link>
      <description>&lt;p&gt;Build &lt;b&gt;APIs&lt;/b&gt; in Python.&lt;/p&gt;</description>
      <pubDate>Mon, 10 Jan 2026 00:00:00 +0000</pubDate>
      <guid>https://jobspresso.co/job/1/</guid>
      <job_listing:company>Acme Corp</job_listing:company>
    </item>
    <item>
      <title>React Frontend Developer</title>
      <link>https://jobspresso.co/job/2/</link>
      <description>&lt;p&gt;Build UIs with React.&lt;/p&gt;</description>
      <pubDate>Tue, 11 Jan 2026 00:00:00 +0000</pubDate>
      <guid>https://jobspresso.co/job/2/</guid>
      <job_listing:company>Beta Ltd</job_listing:company>
    </item>
  </channel>
</rss>
"""

CANNED_RSS_COMPANY_IN_TITLE = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Jobspresso Remote Jobs</title>
    <item>
      <title>GoodCo: Python Dev</title>
      <link>https://jobspresso.co/job/3/</link>
      <description>Python backend work</description>
      <pubDate>Wed, 12 Jan 2026 00:00:00 +0000</pubDate>
      <guid>https://jobspresso.co/job/3/</guid>
    </item>
  </channel>
</rss>
"""


def test_registered():
    """Jobspresso should appear in available_sources."""
    assert "jobspresso" in plugins.available_sources()


def test_discover_keyword_filter_dry_run(monkeypatch):
    """Keyword filter should match python job and skip react job; dry_run skips DB."""
    monkeypatch.setattr(jobspresso, "_fetch", lambda *a, **k: CANNED_RSS)

    result = jobspresso.JobspressoSource().discover(keyword="python", dry_run=True)

    assert result["found"] >= 1
    titles = [j["title"] for j in result["jobs"]]
    assert any("Python" in t for t in titles)
    assert not any("React" in t for t in titles)
    assert result["new"] == 0


def test_company_from_namespace_element(monkeypatch):
    """Company should be extracted from job_listing:company namespace element."""
    monkeypatch.setattr(jobspresso, "_fetch", lambda *a, **k: CANNED_RSS)

    result = jobspresso.JobspressoSource().discover(keyword="python", dry_run=True)

    job = result["jobs"][0]
    assert job["company"] == "Acme Corp"


def test_company_from_title_fallback(monkeypatch):
    """Company should fall back to 'Company: Role' title split when no namespace elem."""
    monkeypatch.setattr(jobspresso, "_fetch", lambda *a, **k: CANNED_RSS_COMPANY_IN_TITLE)

    result = jobspresso.JobspressoSource().discover(keyword="python", dry_run=True)

    assert result["found"] >= 1
    job = result["jobs"][0]
    assert job["company"] == "GoodCo"
    assert job["title"] == "GoodCo: Python Dev"  # title is not stripped for this fallback


def test_html_stripped(monkeypatch):
    """HTML tags in description should be stripped."""
    from job_hunt.plugins._persist import strip_html
    raw = "<p>Build <b>APIs</b> in Python.</p>"
    stripped = strip_html(raw)
    assert "<b>" not in stripped
    assert "APIs" in stripped


def test_fields_parsed(monkeypatch):
    """All required job fields should be present."""
    monkeypatch.setattr(jobspresso, "_fetch", lambda *a, **k: CANNED_RSS)

    result = jobspresso.JobspressoSource().discover(keyword="python", dry_run=True)

    job = result["jobs"][0]
    assert job["title"] == "Senior Python Engineer"
    assert job["apply_url"] == "https://jobspresso.co/job/1/"
    assert job["location"] == "remote"


def test_bad_item_does_not_crash(monkeypatch):
    """A malformed item should be skipped without crashing the batch."""
    bad_rss = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item></item>
    <item>
      <title>Python Backend Dev</title>
      <link>https://jobspresso.co/job/4/</link>
      <description>Python work here</description>
      <guid>https://jobspresso.co/job/4/</guid>
    </item>
  </channel>
</rss>
"""
    monkeypatch.setattr(jobspresso, "_fetch", lambda *a, **k: bad_rss)

    result = jobspresso.JobspressoSource().discover(keyword="python", dry_run=True)

    assert result["found"] >= 1
