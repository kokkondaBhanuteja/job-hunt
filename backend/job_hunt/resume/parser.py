"""
Parse a resume file (PDF, DOCX, or LaTeX) into structured JSON using the local LLM.

Resume vault strategy: you hand-maintain ~3 LaTeX variants in data/resumes/
  - backend-node.tex
  - backend-java.tex
  - fullstack.tex
Each is a real reviewable PDF (compile with tectonic). This parser reads each one,
extracts text, and asks the model to structure it as JSON. The prompt + schema live in
the Prompt Library (job_hunt/llm/prompts.py) — the LaTeX you wrote stays the source of
truth for what's actually sent to recruiters.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pdfplumber

from job_hunt.llm import chat_json
from job_hunt.llm.prompts import RESUME_PARSE
from job_hunt.storage.repo import upsert_resume_variant

# ---------- File readers ----------


def _read_pdf(path: Path) -> str:
    """Extract text from a PDF using pdfplumber."""
    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            chunks.append(text)
    return "\n\n".join(chunks).strip()


_LATEX_COMMENT = re.compile(r"(?<!\\)%.*")

# Structural / metadata commands whose *arguments are noise* — drop command + brace args.
_LATEX_DROP_WITH_ARGS = re.compile(
    r"\\(?:documentclass|usepackage|input|include|includegraphics|geometry|"
    r"setlength|hspace|vspace|rule|label|ref|pageref|cite|bibliography|"
    r"definecolor|pagestyle|thispagestyle|fancyhf|fancyfoot|fancyhead|"
    r"renewcommand|newcommand|providecommand|titleformat|titlespacing|"
    r"setmainfont|setsansfont|fontsize|selectfont)\*?"
    r"(?:\[[^\]]*\])?(?:\s*\{[^{}]*\})*",
    re.IGNORECASE,
)
# \begin{env}[opt]{args} and \end{env} — structure, no prose.
_LATEX_BEGIN_END = re.compile(r"\\(?:begin|end)\s*\{[^{}]*\}(?:\[[^\]]*\])?(?:\{[^{}]*\})*")
# Two-argument commands where the LAST brace holds the text: \href{url}{text}, \textcolor{c}{text}.
_LATEX_TWO_ARG_KEEP_LAST = re.compile(
    r"\\(?:href|textcolor|hyperlink)\s*\{[^{}]*\}\s*\{([^{}]*)\}"
)
# Any remaining \cmd{content} → keep `content` (run inside-out for nesting).
_LATEX_CMD_KEEP_ARG = re.compile(r"\\[a-zA-Z@]+\*?\s*\{([^{}]*)\}")
# Bare command tokens with no brace argument (\hfill, \large, \newpage, ...).
_LATEX_BARE_CMD = re.compile(r"\\[a-zA-Z@]+\*?")
# Escaped specials → their literal character.
_LATEX_SPECIALS = {
    r"\&": "&", r"\%": "%", r"\#": "#", r"\_": "_", r"\$": "$", r"\{": "{", r"\}": "}",
}


def _read_latex(path: Path) -> str:
    """Lightweight LaTeX → plain-text strip. Good enough for LLM input.

    Unlike a naive `\\cmd{arg}` deletion, this PRESERVES the argument text of
    formatting/section commands (`\\textbf{Backend Engineer}` -> `Backend Engineer`,
    `\\section{Experience}` -> `Experience`) while dropping structural noise
    (preamble, environments, spacing). Not a full renderer — just the words.
    """
    src = path.read_text(encoding="utf-8")
    src = _LATEX_COMMENT.sub("", src)
    # Focus on the document body — drops the whole preamble (\newcommand defs,
    # \setlength, package setup) which otherwise leaks noise like "-0.5in" / "#1".
    body = re.search(r"\\begin\{document\}(.*?)\\end\{document\}", src, re.DOTALL)
    if body:
        src = body.group(1)
    elif "\\begin{document}" in src:
        src = src.split("\\begin{document}", 1)[1]
    src = _LATEX_DROP_WITH_ARGS.sub(" ", src)
    src = _LATEX_BEGIN_END.sub("\n", src)
    src = re.sub(r"\\item\b", "\n- ", src)        # list items → bullets
    src = re.sub(r"\\\\(?:\[[^\]]*\])?", "\n", src)  # line breaks

    # Keep the visible text of commands, working inside-out for nested braces.
    for pattern in (_LATEX_TWO_ARG_KEEP_LAST, _LATEX_CMD_KEEP_ARG):
        prev = None
        while prev != src:
            prev = src
            src = pattern.sub(r"\1", src)

    src = _LATEX_BARE_CMD.sub(" ", src)           # leftover argument-less commands
    src = re.sub(r"(?<!\\)\$", " ", src)          # math delimiters ($|$ -> |), keep escaped \$
    for esc, char in _LATEX_SPECIALS.items():
        src = src.replace(esc, char)
    src = src.replace("~", " ")
    src = re.sub(r"[{}]", " ", src)               # any stray braces
    src = re.sub(r"[ \t]+", " ", src)
    src = re.sub(r" *\n", "\n", src)
    src = re.sub(r"\n{3,}", "\n\n", src)
    return src.strip()


def extract_text(path: Path) -> str:
    """Pick the right reader based on file extension."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _read_pdf(path)
    if ext == ".tex":
        return _read_latex(path)
    if ext in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    raise ValueError(f"Unsupported resume format: {ext}")


# ---------- Public API ----------


def parse_resume_file(path: Path) -> dict[str, Any]:
    """Parse one resume file into the structured JSON schema."""
    text = extract_text(path)
    if not text:
        raise ValueError(f"Empty text extracted from {path}")

    prompt = (
        f"Resume file: {path.name}\n"
        f"Use the filename stem ('{path.stem}') as the `slug`.\n\n"
        "--- RESUME TEXT BELOW ---\n"
        f"{text}"
    )
    return chat_json(
        prompt,
        schema=RESUME_PARSE.schema,
        task="scoring",           # structured-output task
        system=RESUME_PARSE.system,
        temperature=0.1,          # parsing is fact-extraction; keep it tight
        prompt_name=RESUME_PARSE.name,
        prompt_version=RESUME_PARSE.version,
    )


def parse_and_store(path: Path) -> int:
    """Parse a resume and write/refresh its row in the resume_variants table.
    Returns the variant's row id.
    """
    parsed = parse_resume_file(path)
    slug = parsed.get("slug") or path.stem
    tags = parsed.get("tags") or []
    return upsert_resume_variant(
        slug=slug,
        source_path=str(path.resolve()),
        parsed=parsed,
        tags=tags,
    )


def parse_vault(vault_dir: Path) -> list[tuple[str, int]]:
    """Parse every supported resume in vault_dir. Returns [(slug, variant_id), ...]."""
    results: list[tuple[str, int]] = []
    for path in sorted(vault_dir.iterdir()):
        if path.suffix.lower() not in {".pdf", ".tex", ".txt", ".md"}:
            continue
        if path.name.startswith("."):
            continue
        variant_id = parse_and_store(path)
        results.append((path.stem, variant_id))
    return results
