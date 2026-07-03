"""The .env loader: parses values, strips export/quotes, splits on the first '=' only,
and never clobbers a real shell export."""
from __future__ import annotations

import os

from job_hunt import env


def test_apply_parses_and_respects_precedence(tmp_path, monkeypatch):
    f = tmp_path / ".env.local"
    f.write_text(
        "# a comment\n"
        "\n"
        "API_TOKEN=mrdtPLU1A+MkP1ZlvcHebLaVBxqFhXIOP91to1P6JNE=\n"  # base64: has + and trailing =
        "export DB_BACKEND=postgres\n"                              # 'export ' prefix tolerated
        'QUOTED="q val"\n',
        encoding="utf-8",
    )
    for k in ("API_TOKEN", "DB_BACKEND", "QUOTED"):
        monkeypatch.delenv(k, raising=False)

    env._apply(f, override=False)
    # split on FIRST '=' → the base64 token keeps its + and trailing =
    assert os.environ["API_TOKEN"] == "mrdtPLU1A+MkP1ZlvcHebLaVBxqFhXIOP91to1P6JNE="
    assert os.environ["DB_BACKEND"] == "postgres"   # export prefix stripped
    assert os.environ["QUOTED"] == "q val"          # surrounding quotes stripped


def test_real_export_is_not_clobbered(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("API_TOKEN=from_file\n", encoding="utf-8")
    monkeypatch.setenv("API_TOKEN", "from_shell_export")

    env._apply(f, override=False)
    assert os.environ["API_TOKEN"] == "from_shell_export"  # real export wins


def test_loader_is_noop_under_pytest():
    # The whole-file loader must be inert during tests (fixtures own the env).
    before = dict(os.environ)
    env.load_env_files()
    assert dict(os.environ) == before
