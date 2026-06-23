"""Database connection and session management."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import decouple


DB_NAME = decouple.config('DB_NAME')  # use .env to configure
DB_PASS = decouple.config('DB_PASS')
DATABASE_URL = os.getenv('DATABASE_URL', f'postgresql://{DB_NAME}:{DB_PASS}@localhost:5432/backtest')

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Yield a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
