"""SpreadWorks SQLAlchemy models — positions + daily_marks + cache tables."""

from sqlalchemy import (
    Column, Integer, String, Float, Text, Date, DateTime, ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .db import Base


# ---------------------------------------------------------------------------
# Cache tables — written on every successful live fetch, read as fallback
# ---------------------------------------------------------------------------

class QuoteCache(Base):
    """Last known quote per symbol. Updated on every candle/quote fetch."""
    __tablename__ = "quote_cache"

    symbol = Column(String(10), primary_key=True)
    last = Column(Float, nullable=True)
    bid = Column(Float, nullable=True)
    ask = Column(Float, nullable=True)
    volume = Column(Integer, nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())


class CandleCache(Base):
    """Last known candle array per symbol+interval. Stored as JSON text."""
    __tablename__ = "candle_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    interval = Column(String(10), nullable=False, default="15min")
    candles_json = Column(Text, nullable=True)  # JSON array of candle dicts
    last_price = Column(Float, nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("symbol", "interval"),)


class GexCache(Base):
    """Last known GEX snapshot per symbol."""
    __tablename__ = "gex_cache"

    symbol = Column(String(10), primary_key=True)
    flip_point = Column(Float, nullable=True)
    call_wall = Column(Float, nullable=True)
    put_wall = Column(Float, nullable=True)
    gamma_regime = Column(String(30), nullable=True)
    spot_price = Column(Float, nullable=True)
    vix = Column(Float, nullable=True)
    source = Column(String(30), nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())


class ChainCache(Base):
    """Last known option chain per symbol+expiration. Stored as JSON text."""
    __tablename__ = "chain_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    expiration = Column(String(12), nullable=False)
    chain_json = Column(Text, nullable=True)  # JSON: {strikes, options}
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("symbol", "expiration"),)


class GexSnapshot(Base):
    """Historical GEX snapshots for flip point tracking and alerts."""
    __tablename__ = "gex_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, default="SPY")
    flip_point = Column(Float, nullable=True)
    call_wall = Column(Float, nullable=True)
    put_wall = Column(Float, nullable=True)
    gamma_regime = Column(String(30), nullable=True)
    spot_price = Column(Float, nullable=True)
    vix = Column(Float, nullable=True)
    source = Column(String(30), nullable=True)
    captured_at = Column(DateTime(timezone=True), server_default=func.now())


class DiscordPostLog(Base):
    """One row per (message_key, fire_date). Cross-process / cross-replica
    dedup for scheduled Discord posts — guarantees only one worker actually
    sends a given daily message no matter how many uvicorn workers / Render
    instances are running.
    """
    __tablename__ = "discord_post_log"

    message_key = Column(String(64), primary_key=True)
    fire_date = Column(Date, primary_key=True)
    posted_at = Column(DateTime(timezone=True), server_default=func.now())


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, default="SPY")
    strategy = Column(String(30), nullable=False)  # double_diagonal, double_calendar, iron_condor
    label = Column(String(100), nullable=True)
    long_put = Column(Float, nullable=False)
    short_put = Column(Float, nullable=False)
    short_call = Column(Float, nullable=False)
    long_call = Column(Float, nullable=False)
    short_exp = Column(Date, nullable=False)
    long_exp = Column(Date, nullable=True)  # NULL for iron condor (single exp)
    contracts = Column(Integer, nullable=False, default=1)
    entry_credit = Column(Float, nullable=False)  # total credit received ($)
    entry_price = Column(Float, nullable=False)  # per-contract credit
    entry_date = Column(Date, nullable=False, server_default=func.current_date())
    entry_spot = Column(Float, nullable=True)  # underlying price at entry
    max_profit = Column(Float, nullable=True)
    max_loss = Column(Float, nullable=True)
    breakeven_low = Column(Float, nullable=True)
    breakeven_high = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(10), nullable=False, default="open")  # open | closed
    close_date = Column(Date, nullable=True)
    close_price = Column(Float, nullable=True)  # per-contract debit to close
    realized_pnl = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    marks = relationship("DailyMark", back_populates="position", cascade="all, delete-orphan")


class DailyMark(Base):
    __tablename__ = "daily_marks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(Integer, ForeignKey("positions.id", ondelete="CASCADE"), nullable=False)
    mark_date = Column(Date, nullable=False)
    current_value = Column(Float, nullable=True)  # what it costs to close
    unrealized_pnl = Column(Float, nullable=True)  # entry_credit - current_value * 100 * contracts
    spot_price = Column(Float, nullable=True)
    dte = Column(Integer, nullable=True)
    iv = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("position_id", "mark_date"),)

    position = relationship("Position", back_populates="marks")
