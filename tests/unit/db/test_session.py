"""SQLite session defaults for Docker vs local dev."""
from pathlib import Path

from src.db import session as db_session


def test_default_journal_mode_is_delete_in_docker(monkeypatch):
    monkeypatch.delenv("SQLITE_JOURNAL_MODE", raising=False)
    monkeypatch.setattr(db_session.Path, "exists", lambda self: self == Path("/.dockerenv"))
    assert db_session._default_sqlite_journal_mode() == "DELETE"


def test_default_journal_mode_is_wal_locally(monkeypatch):
    monkeypatch.delenv("SQLITE_JOURNAL_MODE", raising=False)
    monkeypatch.setattr(db_session.Path, "exists", lambda self: False)
    assert db_session._default_sqlite_journal_mode() == "WAL"


def test_journal_mode_env_override(monkeypatch):
    monkeypatch.setenv("SQLITE_JOURNAL_MODE", "truncate")
    assert db_session._default_sqlite_journal_mode() == "TRUNCATE"
