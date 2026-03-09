"""SpreadWorks SQLAlchemy models — positions + daily_marks tables."""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .db import Base


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, default="SPY")
    strategy = Column(String(30), nullable=False)  # double_diagonal | double_calendar
    contracts = Column(Integer, nullable=False, default=1)
    legs = Column(JSON, nullable=False)  # strike/exp details
    net_debit = Column(Float, nullable=False)  # entry cost in dollars
    spot_at_entry = Column(Float, nullable=False)
    label = Column(String(60), nullable=True, default="")
    notes = Column(Text, nullable=True, default="")
    status = Column(String(10), nullable=False, default="open")  # open | closed
    opened_at = Column(DateTime, nullable=False, server_default=func.now())
    closed_at = Column(DateTime, nullable=True)
    close_price = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)

    marks = relationship("DailyMark", back_populates="position", cascade="all, delete-orphan")


class DailyMark(Base):
    __tablename__ = "daily_marks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(Integer, ForeignKey("positions.id", ondelete="CASCADE"), nullable=False)
    mark_date = Column(DateTime, nullable=False, server_default=func.now())
    spot_price = Column(Float, nullable=False)
    mark_value = Column(Float, nullable=False)  # current spread value in dollars
    unrealised_pnl = Column(Float, nullable=False)
    pnl_pct = Column(Float, nullable=False)

    position = relationship("Position", back_populates="marks")
