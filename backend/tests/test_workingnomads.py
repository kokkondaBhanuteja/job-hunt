"""Tests for the Working Nomads plugin (RSS mocked — no network)."""
from __future__ import annotations

from job_hunt import plugins
from job_hunt.plugins import workingnomads

CANNED_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Working Nomads</title>
    <item>
      <title>Senior Python Developer</title>
      <link>https://www.workingnomads.com/jobs?id=1</link>
      <description>&lt;p&gt;Build &lt;b&gt;APIs&lt;/b&gt; in Python.&lt;/p&gt;</description>
      <pubDate>Mon, 10 Jan 2026 00:00:00 +0000</pubDate>
      <guid>wn-job-1</guid>
      <author>Acme Corp</author>
    </item>
    <item>
      <title>React Frontend Engineer</title>
      <link>https://www.workingnomads.com/jobs?id=2</link>
      <description>&lt;p&gt;Build UIs with React.&lt;/p&gt;</description>
      <pubDate>Tue, 11 Jan 2026 00:00:00 +0000</pubDate>
      <guid>wn-job-2</guid>
      <author>Beta Ltd</author>
    </item>
  </channel>
</rss>
"""


def test_registered():
    """WorkingNomads should appear in available_sources."""
    assert "workingnomads" in plugins.available_sources()


def test_discover_keyword_filter_dry_run(monkeypatch):
    """Keyword filter should match python job and skip react job; dry_run skips DB."""
    monkeypatch.setattr(workingnomads, "_fetch", lambda *a, **k: CANNED_RSS)

    result = workingnomads.WorkingNomadsSource().discover(keyword="python", dry_run=True)

    assert result["found"] >= 1
    titles = [j["title"] for j in result["jobs"]]
    assert any("Python" in t for t in titles)
    assert not any("React" in t for t in titles)
    assert result["new"] == 0


def test_fields_parsed(monkeypatch):
    """All key fields should be present and correct."""
    monkeypatch.setattr(workingnomads, "_fetch", lambda *a, **k: CANNED_RSS)

    result = workingnomads.WorkingNomadsSource().discover(keyword="python", dry_run=True)

    job = result["jobs"][0]
    assert job["title"] == "Senior Python Developer"
    assert job["company"] == "Acme Corp"
    assert job["apply_url"] == "https://www.workingnomads.com/jobs?id=1"
    assert job["location"] == "remote"


def test_html_stripped(monkeypatch):
    """HTML tags in description should be stripped."""
    from job_hunt.plugins._persist import strip_html
    raw = "<p>Build <b>APIs</b> in Python.</p>"
    stripped = strip_html(raw)
    assert "<b>" not in stripped
    assert "APIs" in stripped


def test_empty_keyword_returns_all(monkeypatch):
    """Empty keyword should return all jobs."""
    monkeypatch.setattr(workingnomads, "_fetch", lambda *a, **k: CANNED_RSS)

    result = workingnomads.WorkingNomadsSource().discover(keyword="", dry_run=True)

    assert result["found"] == 2


def test_bad_item_does_not_crash(monkeypatch):
    """A malformed item should be skipped without crashing the batch."""
    bad_rss = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item></item>
    <item>
      <title>Python Backend Dev</title>
      <link>https://www.workingnomads.com/jobs?id=3</link>
      <description>Python work here</description>
      <guid>wn-job-3</guid>
    </item>
  </channel>
</rss>
"""
    monkeypatch.setattr(workingnomads, "_fetch", lambda *a, **k: bad_rss)

    result = workingnomads.WorkingNomadsSource().discover(keyword="python", dry_run=True)

    assert result["found"] >= 1
