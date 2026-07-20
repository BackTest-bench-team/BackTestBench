"""Shared helpers for integration tests that touch SQLite candle storage."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.session import Base


def patch_isolated_candle_db(monkeypatch, db_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr("src.data_loader.loader.SessionLocal", test_session)

    def _init_db() -> None:
        Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("src.db.session.init_db", _init_db)
