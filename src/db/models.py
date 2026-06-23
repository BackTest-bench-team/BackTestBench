"""SQLAlchemy ORM models aligned with MVP1 schema."""
from sqlalchemy import Column, Integer, String, DateTime, Numeric, BigInteger, UniqueConstraint
from .session import Base

class CandleModel(Base):
    __tablename__ = 'candles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    open = Column(Numeric(12, 4))
    high = Column(Numeric(12, 4))
    low = Column(Numeric(12, 4))
    close = Column(Numeric(12, 4))
    volume = Column(BigInteger)

    __table_args__ = (
        UniqueConstraint('instrument', 'timeframe', 'timestamp', name='uq_candle_uniq'),
    )
