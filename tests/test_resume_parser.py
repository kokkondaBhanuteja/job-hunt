"""Characterization tests for the resume text extractors (no LLM involved)."""
from __future__ import annotations

import pytest

from job_hunt.resume.parser import _read_latex, extract_text


def test_read_latex_preserves_command_argument_text(tmp_path):
    """The stripper must KEEP the visible text of formatting/section commands
    while removing LaTeX syntax (regression test for the lossy-stripper bug)."""
    tex = tmp_path / "r.tex"
    tex.write_text(
        r"""
% a comment that should vanish
\section{Experience}
\textbf{Backend Engineer} at \emph{Acme}
        """.strip(),
        encoding="utf-8",
    )
    out = _read_latex(tex)
    assert "comment that should vanish" not in out
    assert "\\section" not in out and "\\textbf" not in out
    assert "{" not in out and "}" not in out
    # The actual words now survive.
    assert "Experience" in out
    assert "Backend Engineer" in out
    assert "Acme" in out
    assert "at" in out


def test_read_latex_handles_links_items_environments_and_escapes(tmp_path):
    tex = tmp_path / "r.tex"
    tex.write_text(
        r"""
\usepackage{geometry}
\begin{itemize}
  \item Built \href{https://x.io}{payments API} at R\&D Labs
  \item Scaled to 5\% error budget
\end{itemize}
        """.strip(),
        encoding="utf-8",
    )
    out = _read_latex(tex)
    assert "\\usepackage" not in out and "geometry" not in out   # preamble dropped
    assert "payments API" in out and "https://x.io" not in out   # \href keeps text, drops url
    assert "R&D Labs" in out                                     # \& unescaped
    assert "5% error budget" in out
    assert "- Built" in out                                      # \item → bullet


def test_extract_text_dispatch_by_suffix(tmp_path):
    txt = tmp_path / "r.txt"
    txt.write_text("plain resume text", encoding="utf-8")
    assert extract_text(txt) == "plain resume text"


def test_extract_text_rejects_unsupported_format(tmp_path):
    bad = tmp_path / "r.rtf"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        extract_text(bad)
