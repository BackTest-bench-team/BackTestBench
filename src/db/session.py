"""Database connection and session management."""
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DEFAULT_SQLITE_PATH = _DATA_DIR / "backtest.db"


def _default_sqlite_journal_mode() -> str:
    """WAL improves local concurrency; DELETE avoids bind-mount I/O errors in Docker."""
    explicit = os.getenv("SQLITE_JOURNAL_MODE", "").strip().upper()
    if explicit:
        return explicit
    if Path("/.dockerenv").exists():
        return "DELETE"
    return "WAL"


def _sqlite_db_path() -> Path | None:
    if not DATABASE_URL.startswith("sqlite:///"):
        return None
    raw = DATABASE_URL.removeprefix("sqlite:///")
    return Path(raw)


def _cleanup_stale_sqlite_sidecars(db_path: Path) -> None:
    """Remove WAL/SHM leftovers after an unclean shutdown on a bind-mounted volume."""
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = db_path.parent / f"{db_path.name}{suffix}"
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError:
                pass


def _resolve_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{_DEFAULT_SQLITE_PATH.as_posix()}"


DATABASE_URL = _resolve_database_url()
SQLITE_JOURNAL_MODE = _default_sqlite_journal_mode()

_engine_kwargs: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

engine = create_engine(DATABASE_URL, **_engine_kwargs)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute(f"PRAGMA journal_mode={SQLITE_JOURNAL_MODE}")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    """Create tables if they do not exist."""
    from src.db.models import CandleModel  # noqa: F401

    if DATABASE_URL.startswith("sqlite"):
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        if SQLITE_JOURNAL_MODE != "WAL":
            db_path = _sqlite_db_path()
            if db_path is not None:
                _cleanup_stale_sqlite_sidecars(db_path)

    Base.metadata.create_all(bind=engine)


def get_db():
    """Yield a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
