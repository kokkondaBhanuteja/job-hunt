"""Resume services — parse the vault into structured variants."""
from __future__ import annotations

from pathlib import Path

from job_hunt.resume.parser import parse_vault as _parse_vault
from job_hunt.storage.repo import init_db


def parse_resume_vault(vault_dir: str | Path) -> list[tuple[str, int]]:
    """Parse every supported resume in `vault_dir`. Returns [(slug, variant_id), ...]."""
    init_db()
    return _parse_vault(Path(vault_dir))
