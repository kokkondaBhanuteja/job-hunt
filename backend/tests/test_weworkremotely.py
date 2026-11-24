"""Tests for the We Work Remotely plugin (RSS mocked — no network)."""
from __future__ import annotations

from job_hunt import plugins
from job_hunt.plugins import weworkremotely

CANNED_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>We Work Remotely: Remote Jobs</title>
    <item>
      <title>Acme Corp: Senior Python Engineer</title>
      <link>https://weworkremotely.com/jobs/1</link>
      <description>&lt;p&gt;Build &lt;b&gt;APIs&lt;/b&gt; in Python.&lt;/p&gt;</description>
      <pubDate>Mon, 10 Jan 2026 00:00:00 +0000</pubDate>
      <guid>https://weworkremotely.com/jobs/1</guid>
    </item>
    <item>
      <title>Beta Ltd: React Developer</title>
      <link>https://weworkremotely.com/jobs/2</link>
      <description>&lt;p&gt;Build UIs with React.&lt;/p&gt;</description>
      <pubDate>Tue, 11 Jan 2026 00:00:00 +0000</pubDate>
      <guid>https://weworkremotely.com/jobs/2</guid>
    </item>
  </channel>
</rss>
"""


def test_registered():
    """WeWorkRemotely should appear in available_sources."""
    assert "weworkremotely" in plugins.available_sources()


def test_discover_keyword_filter_dry_run(monkeypatch):
    """Keyword filter should match python job and skip react job; dry_run skips DB."""
    monkeypatch.setattr(weworkremotely, "_fetch", lambda *a, **k: CANNED_RSS)

    result = weworkremotely.WeWorkRemotelySource().discover(keyword="python", dry_run=True)

    assert result["found"] >= 1
    titles = [j["title"] for j in result["jobs"]]
    assert any("Python" in t for t in titles)
    assert not any("React" in t for t in titles)
    assert result["new"] == 0


def test_company_title_split(monkeypatch):
    """'Company: Role' title format should be split correctly."""
    monkeypatch.setattr(weworkremotely, "_fetch", lambda *a, **k: CANNED_RSS)

    result = weworkremotely.WeWorkRemotelySource().discover(keyword="python", dry_run=True)

    job = result["jobs"][0]
    assert job["title"] == "Senior Python Engineer"
    assert job["company"] == "Acme Corp"


def test_html_stripped(monkeypatch):
    """HTML entities in description should be stripped."""
    monkeypatch.setattr(weworkremotely, "_fetch", lambda *a, **k: CANNED_RSS)

    from job_hunt.plugins._persist import strip_html
    raw = "<p>Build <b>APIs</b> in Python.</p>"
    stripped = strip_html(raw)
    assert "<b>" not in stripped
    assert "APIs" in stripped


def test_fields_present(monkeypatch):
    """All required job fields should be present."""
    monkeypatch.setattr(weworkremotely, "_fetch", lambda *a, **k: CANNED_RSS)

    result = weworkremotely.WeWorkRemotelySource().discover(keyword="python", dry_run=True)

    job = result["jobs"][0]
    assert job["apply_url"] == "https://weworkremotely.com/jobs/1"
    assert job["location"] == "remote"


def test_bad_item_does_not_crash(monkeypatch):
    """A malformed item should be skipped without crashing the batch."""
    bad_rss = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item></item>
    <item>
      <title>GoodCo: Python Dev</title>
      <link>https://weworkremotely.com/jobs/3</link>
      <description>Python work here</description>
      <guid>https://weworkremotely.com/jobs/3</guid>
    </item>
  </channel>
</rss>
"""
    monkeypatch.setattr(weworkremotely, "_fetch", lambda *a, **k: bad_rss)

    result = weworkremotely.WeWorkRemotelySource().discover(keyword="python", dry_run=True)

    assert result["found"] >= 1


_REGION_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Acme: Backend Engineer</title><link>https://weworkremotely.com/jobs/10</link>
    <description>Python APIs</description><guid>https://weworkremotely.com/jobs/10</guid>
    <region>USA Only</region>
  </item>
  <item>
    <title>Beta: Backend Engineer</title><link>https://weworkremotely.com/jobs/11</link>
    <description>Python APIs</description><guid>https://weworkremotely.com/jobs/11</guid>
    <region>Anywhere in the World</region>
  </item>
  <item>
    <title>Gamma: Backend Engineer</title><link>https://weworkremotely.com/jobs/12</link>
    <description>Python APIs</description><guid>https://weworkremotely.com/jobs/12</guid>
  </item>
</channel></rss>
"""


def test_region_becomes_the_job_location(monkeypatch):
    """Each job keeps its own <region>; without one it falls back to the profile location."""
    monkeypatch.setattr(weworkremotely, "_fetch", lambda *a, **k: _REGION_RSS)
    result = weworkremotely.WeWorkRemotelySource().discover(keyword="python", dry_run=True)
    assert [j["location"] for j in result["jobs"]] == [
        "Remote - USA Only", "Remote - Anywhere in the World", "remote",
    ]
