"""Database tables.

Times are stored as naive UTC in SQLite and come back as aware UTC datetimes.
MT5-derived trade fields are rebuilt on every sync; everything the trader adds
lives in `trade_journal`, `screenshots` and `day_notes`, which sync never touches.
"""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    type_annotation_map = {datetime: UTCDateTime, dict[str, Any]: JSON, list[str]: JSON}


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("source", "login", "server"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16))  # mt5 | manual
    login: Mapped[str | None] = mapped_column(String(32))
    server: Mapped[str | None] = mapped_column(String(128))
    broker: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    leverage: Mapped[int | None]
    utc_offset_sec: Mapped[int] = mapped_column(default=0)
    margin_mode: Mapped[str | None] = mapped_column(String(16))  # hedging | netting
    trade_mode: Mapped[str | None] = mapped_column(String(16))  # demo | real | contest
    balance: Mapped[float | None]
    equity: Mapped[float | None]
    ea_seen_at: Mapped[datetime | None]  # last heartbeat written by the EA
    last_sync_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Symbol(Base):
    __tablename__ = "symbols"
    __table_args__ = (UniqueConstraint("account_id", "symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(64))
    canonical: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(256))
    digits: Mapped[int | None]
    point: Mapped[float | None]
    tick_size: Mapped[float | None]
    tick_value: Mapped[float | None]
    contract_size: Mapped[float | None]
    base_ccy: Mapped[str | None] = mapped_column(String(16))
    profit_ccy: Mapped[str | None] = mapped_column(String(16))
    asset_class: Mapped[str | None] = mapped_column(String(32))


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = (UniqueConstraint("account_id", "ticket"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    ticket: Mapped[int]
    order: Mapped[int | None]
    position_id: Mapped[int | None] = mapped_column(index=True)
    time: Mapped[datetime]
    time_msc: Mapped[int]
    type: Mapped[str] = mapped_column(String(32))  # buy | sell | balance | credit | ...
    entry: Mapped[str] = mapped_column(String(8))  # in | out | inout | out_by
    symbol: Mapped[str | None] = mapped_column(String(64))
    volume: Mapped[float] = mapped_column(default=0.0)
    price: Mapped[float] = mapped_column(default=0.0)
    sl: Mapped[float | None]
    tp: Mapped[float | None]
    commission: Mapped[float] = mapped_column(default=0.0)
    fee: Mapped[float] = mapped_column(default=0.0)
    swap: Mapped[float] = mapped_column(default=0.0)
    profit: Mapped[float] = mapped_column(default=0.0)
    reason: Mapped[str | None] = mapped_column(String(32))
    magic: Mapped[int | None]
    comment: Mapped[str | None] = mapped_column(String(256))


class PositionExcursion(Base):
    """Highest and lowest price while a position was open, from the EA's M1 bars."""

    __tablename__ = "position_excursions"
    __table_args__ = (UniqueConstraint("account_id", "position_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    position_id: Mapped[int]
    high: Mapped[float]
    low: Mapped[float]


class PositionStop(Base):
    """First stop-loss the EA saw on a position, which catches stops added after entry."""

    __tablename__ = "position_stops"
    __table_args__ = (UniqueConstraint("account_id", "position_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    position_id: Mapped[int]
    first_sl: Mapped[float]
    first_sl_time: Mapped[datetime]


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (UniqueConstraint("account_id", "position_id", "leg"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(16))  # mt5 | manual
    position_id: Mapped[int | None]
    leg: Mapped[int] = mapped_column(default=0)  # >0 after a netting-account reversal
    symbol: Mapped[str] = mapped_column(String(64))
    instrument: Mapped[str] = mapped_column(String(64), index=True)  # canonical symbol
    direction: Mapped[str] = mapped_column(String(8))  # long | short
    status: Mapped[str] = mapped_column(String(8))  # open | closed
    volume: Mapped[float]
    open_time: Mapped[datetime] = mapped_column(index=True)
    close_time: Mapped[datetime | None] = mapped_column(index=True)
    entry_price: Mapped[float]
    exit_price: Mapped[float | None]
    initial_sl: Mapped[float | None]
    initial_tp: Mapped[float | None]
    final_sl: Mapped[float | None]
    final_tp: Mapped[float | None]
    # The stop that defines the trade's risk (1R): the order's stop, else the first stop
    # added after entry, else the stop at close if it was still on the losing side.
    risk_sl: Mapped[float | None]
    sl_source: Mapped[str | None] = mapped_column(String(8))  # entry | added | close
    sl_delay_seconds: Mapped[int | None]  # how long after entry the stop was added
    close_reason: Mapped[str | None] = mapped_column(String(16))
    commission: Mapped[float] = mapped_column(default=0.0)
    swap: Mapped[float] = mapped_column(default=0.0)
    gross_pnl: Mapped[float] = mapped_column(default=0.0)
    net_pnl: Mapped[float] = mapped_column(default=0.0)
    floating_pnl: Mapped[float | None]
    r_multiple: Mapped[float | None]
    points: Mapped[float | None]
    mfe_points: Mapped[float | None]
    mae_points: Mapped[float | None]
    holding_seconds: Mapped[int | None]
    session: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    account: Mapped[Account] = relationship()
    journal: Mapped["TradeJournal | None"] = relationship(
        back_populates="trade", cascade="all, delete-orphan", uselist=False, lazy="joined"
    )
    screenshots: Mapped[list["Screenshot"]] = relationship(
        back_populates="trade", cascade="all, delete-orphan", order_by="Screenshot.id"
    )


class TradeJournal(Base):
    __tablename__ = "trade_journal"

    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), primary_key=True)
    setup: Mapped[str | None] = mapped_column(String(64))
    emotions: Mapped[list[str]] = mapped_column(default=list)
    mistakes: Mapped[list[str]] = mapped_column(default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int | None]
    followed_plan: Mapped[bool | None] = mapped_column(Boolean)
    ai_feedback: Mapped[str | None] = mapped_column(Text)
    ai_feedback_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    trade: Mapped[Trade] = relationship(back_populates="journal")


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(256))
    caption: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    trade: Mapped[Trade] = relationship(back_populates="screenshots")


class DayNote(Base):
    __tablename__ = "day_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True)
    pre_session_plan: Mapped[str | None] = mapped_column(Text)
    post_session_review: Mapped[str | None] = mapped_column(Text)
    mood: Mapped[str | None] = mapped_column(String(32))
    rules_followed: Mapped[bool | None] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AIReport(Base):
    __tablename__ = "ai_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # weekly | monthly | instrument | custom
    symbol: Mapped[str | None] = mapped_column(String(64))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(256))
    summary: Mapped[str] = mapped_column(Text)
    content: Mapped[dict[str, Any]]
    source: Mapped[str] = mapped_column(String(32), default="claude-mcp")


class CashFlow(Base):
    __tablename__ = "cash_flows"
    __table_args__ = (UniqueConstraint("account_id", "ticket"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    ticket: Mapped[int]
    time: Mapped[datetime]
    amount: Mapped[float]
    type: Mapped[str] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(String(256))


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("category", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(16))  # setup | emotion | mistake
    name: Mapped[str] = mapped_column(String(64))


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
