from pathlib import Path

import pytest

from src.env_file import (
    format_env_file,
    load_env_file_into_process,
    mask_token,
    parse_env_lines,
    read_env_file,
    write_env_file,
)


def test_parse_env_lines_ignores_comments_and_quotes():
    text = """
# comment
TINKOFF_TOKEN="abc123"
export TWELVEDATA_TOKEN='xyz789'
EMPTY=
"""
    assert parse_env_lines(text) == {
        "TINKOFF_TOKEN": "abc123",
        "TWELVEDATA_TOKEN": "xyz789",
        "EMPTY": "",
    }


def test_write_and_read_env_file_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr("src.env_file.ENV_FILE", env_path)

    write_env_file({"TINKOFF_TOKEN": "token-a", "TWELVEDATA_TOKEN": "token-b"})
    stored = read_env_file(env_path)

    assert stored["TINKOFF_TOKEN"] == "token-a"
    assert stored["TWELVEDATA_TOKEN"] == "token-b"
    assert "token-a" in format_env_file(stored)


def test_load_env_file_into_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_path = tmp_path / ".env"
    env_path.write_text("TINKOFF_TOKEN=from-file\n", encoding="utf-8")
    monkeypatch.delenv("TINKOFF_TOKEN", raising=False)

    load_env_file_into_process(env_path)

    import os

    assert os.getenv("TINKOFF_TOKEN") == "from-file"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("short", "*****"),
        ("abcdefghij", "abcd…ghij"),
    ],
)
def test_mask_token(value: str | None, expected: str | None):
    assert mask_token(value) == expected
