"""Utility helpers for Claw Claw."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


REDACT_PATTERNS = [
    re.compile(r"\b\d{6,}\b"),
    re.compile(r"(?i)(password|pass|pwd|token|secret)=\S+"),
]


def redact_text(text: str, max_len: int = 500) -> str:
    """Redact likely sensitive tokens and truncate long strings."""
    redacted = text
    for pattern in REDACT_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    if len(redacted) > max_len:
        redacted = redacted[:max_len] + "..."
    return redacted


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load config JSON with a small safety check."""
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data


def kill_switch_triggered(project_root: Path) -> bool:
    return (project_root / "KILL_SWITCH").exists()


def env_flag(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "y"}
