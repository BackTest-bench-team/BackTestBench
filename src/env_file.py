"""Read and write the repository .env file for local API tokens."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"

MANAGED_ENV_KEYS = (
    "TINKOFF_TOKEN",
    "TWELVEDATA_TOKEN",
    "BYBIT_TOKEN",
    "DATABASE_URL",
    "DATA_SOURCE",
)


def parse_env_lines(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def read_env_file(path: Path | None = None) -> dict[str, str]:
    env_path = path or ENV_FILE
    if not env_path.exists():
        return {}
    return parse_env_lines(env_path.read_text(encoding="utf-8"))


def format_env_file(values: dict[str, str]) -> str:
    lines = [
        "# Local API tokens and runtime overrides (never commit this file).",
        "# CI/CD uses GitHub repository secrets instead.",
        "",
    ]
    for key in MANAGED_ENV_KEYS:
        if key in values and values[key]:
            lines.append(f"{key}={values[key]}")
    extra_keys = sorted(k for k in values if k not in MANAGED_ENV_KEYS and values[k])
    if extra_keys:
        lines.append("")
        for key in extra_keys:
            lines.append(f"{key}={values[key]}")
    lines.append("")
    return "\n".join(lines)


def write_env_file(updates: dict[str, str], path: Path | None = None) -> dict[str, str]:
    env_path = path or ENV_FILE
    current = read_env_file(env_path)
    for key, value in updates.items():
        if value is None:
            current.pop(key, None)
        elif str(value).strip():
            current[key] = str(value).strip()
        else:
            current.pop(key, None)
    env_path.write_text(format_env_file(current), encoding="utf-8")
    return current


def load_env_file_into_process(path: Path | None = None, *, override: bool = False) -> None:
    for key, value in read_env_file(path).items():
        if override or not os.getenv(key):
            os.environ[key] = value


def mask_token(value: str | None) -> str | None:
    if not value:
        return None
    trimmed = value.strip()
    if len(trimmed) <= 8:
        return "*" * len(trimmed)
    return f"{trimmed[:4]}…{trimmed[-4:]}"
