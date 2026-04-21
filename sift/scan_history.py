"""Scan history tracking for progressive seed coverage.

Stores scan records in a local JSON file (not checked into git) so that
repeated scans cover new ground instead of re-scanning the same seeds.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_DIR = Path(__file__).resolve().parent.parent / ".sift"
HISTORY_PATH = HISTORY_DIR / "scan_history.json"


@dataclass
class ScanRecord:
    scan_type: str
    timestamp: str
    seeds_used: list[str]
    findings_count: int
    last_offset: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def load_history() -> dict[str, list[dict]]:
    """Load scan history, keyed by scan_type."""
    if not HISTORY_PATH.exists():
        return {}
    try:
        return json.loads(HISTORY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_record(record: ScanRecord) -> None:
    """Append a record to the history file (atomic write)."""
    history = load_history()
    history.setdefault(record.scan_type, []).append(asdict(record))

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    # Atomic write: write to temp file, then rename
    fd, tmp = tempfile.mkstemp(dir=HISTORY_DIR, suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        os.replace(tmp, HISTORY_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_used_seeds(scan_type: str) -> set[str]:
    """Return all seeds previously used for a scan type."""
    history = load_history()
    seeds: set[str] = set()
    for record in history.get(scan_type, []):
        seeds.update(record.get("seeds_used", []))
    return seeds


def get_last_offset(scan_type: str) -> dict[str, int]:
    """Return the most recent pagination offsets for a scan type."""
    history = load_history()
    records = history.get(scan_type, [])
    if not records:
        return {}
    return records[-1].get("last_offset", {})


def get_last_metadata(scan_type: str) -> dict[str, Any]:
    """Return the most recent metadata for a scan type."""
    history = load_history()
    records = history.get(scan_type, [])
    if not records:
        return {}
    return records[-1].get("metadata", {})


def get_summary(scan_type: str) -> dict[str, Any]:
    """Return a summary of scan history for a scan type."""
    history = load_history()
    records = history.get(scan_type, [])
    if not records:
        return {
            "run_count": 0,
            "seeds_used": [],
            "last_offset": {},
            "last_metadata": {},
        }
    all_seeds = set()
    for r in records:
        all_seeds.update(r.get("seeds_used", []))
    return {
        "run_count": len(records),
        "seeds_used": sorted(all_seeds),
        "last_offset": records[-1].get("last_offset", {}),
        "last_metadata": records[-1].get("metadata", {}),
        "last_run": records[-1].get("timestamp", ""),
        "total_findings": sum(r.get("findings_count", 0) for r in records),
    }
