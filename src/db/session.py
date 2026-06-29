"""Database connection and session management."""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DEFAULT_SQLITE_PATH = _DATA_DIR / "backtest.db"


def _resolve_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    _DATA_DIR.mkdir(exist_ok=True)
    return f"sqlite:///{_DEFAULT_SQLITE_PATH.as_posix()}"


DATABASE_URL = _resolve_database_url()

_engine_kwargs: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    """Create tables if they do not exist."""
    from src.db.models import CandleModel  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    """Yield a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
