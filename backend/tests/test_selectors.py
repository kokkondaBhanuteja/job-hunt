"""E: the Naukri selector hot-patch mechanism actually works (config/selectors/naukri.json
overrides DEFAULT_SELECTORS; absent file falls back to defaults)."""
from __future__ import annotations

from job_hunt.sources import naukri


def test_selector_override_merges_over_defaults(tmp_path, monkeypatch):
    override = tmp_path / "naukri.json"
    override.write_text('{"card": ".new-card-selector"}', encoding="utf-8")
    monkeypatch.setattr(naukri, "SELECTOR_FILE", override)

    selectors = naukri._load_selectors()
    assert selectors["card"] == ".new-card-selector"                     # overridden
    assert selectors["title"] == naukri.DEFAULT_SELECTORS["title"]       # default preserved


def test_absent_selector_file_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(naukri, "SELECTOR_FILE", tmp_path / "absent.json")
    assert naukri._load_selectors() == naukri.DEFAULT_SELECTORS
