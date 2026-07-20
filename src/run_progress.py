"""Lightweight run progress file for bootstrap fetch + backtest phases."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PROGRESS_FILE = _DATA_DIR / "run-progress.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clear_run_progress() -> None:
    PROGRESS_FILE.unlink(missing_ok=True)


def write_run_progress(
    *,
    phase: str,
    current: int,
    total: int,
    label: str,
    display_pct: int | None = None,
) -> None:
    total_safe = max(int(total), 1)
    current_safe = max(0, min(int(current), total_safe))
    pct = display_pct if display_pct is not None else round(100 * current_safe / total_safe)
    pct = max(0, min(100, int(pct)))
    payload = {
        "phase": phase,
        "current": current_safe,
        "total": total_safe,
        "pct": pct,
        "label": label,
        "updated_at": _now_iso(),
    }
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def read_run_progress() -> dict[str, Any] | None:
    if not PROGRESS_FILE.exists():
        return None
    try:
        payload = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload
