from __future__ import annotations

import logging
from pathlib import Path

from kubeweekly.models import Briefing

log = logging.getLogger(__name__)

LINKEDIN_MAX_CHARS = 3000


def enforce_linkedin_limit(text: str, max_chars: int = LINKEDIN_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    log.warning("render: draft exceeds %d chars (%d), truncating at last paragraph break", max_chars, len(text))
    truncated = text[:max_chars]
    last_break = truncated.rfind("\n\n")
    return truncated[:last_break] if last_break > 0 else truncated


def write_draft(output_dir: str | Path, briefing: Briefing) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{briefing.date}-linkedin-draft.txt"
    path.write_text(briefing.linkedin_text, encoding="utf-8")
    log.info("render: draft written to %s (%d chars)", path, len(briefing.linkedin_text))
    return path
