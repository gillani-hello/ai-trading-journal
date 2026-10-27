"""Querying, serialising and manually logging trades."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, String, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from tj.ingest.instruments import canonical_symbol
from tj.models import Deal, Symbol, Trade, TradeJournal
from tj.services.analytics import TradeRow, rows_from_trades
from tj.services.seed import get_manual_account
from tj.services.settings import get_setting, session_for_hour

SORTABLE = {
    "time": func.coalesce(Trade.close_time, Trade.open_time),
    "open_time": Trade.open_time,
    "instrument": Trade.instrument,
    "net_pnl": Trade.net_pnl,
    "r_multiple": Trade.r_multiple,
    "volume": Trade.volume,
    "holding": Trade.holding_seconds,
}


def get_tz(session: Session) -> ZoneInfo:
    try:
        return ZoneInfo(get_setting(session, "display_timezone"))
    except Exception:
        return ZoneInfo("UTC")


def local_day_start(d: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, time.min, tzinfo=tz).astimezone(UTC)


def parse_local_datetime(value: str | datetime | None, tz: ZoneInfo) -> datetime | None:
    """ISO string or datetime; naive values are read in the display timezone."""
    if value is None or value == "":
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(UTC)


@dataclass
class TradeFilter:
    date_from: date | None = None
    date_to: date | None = None  # inclusive
    instrument: str | None = None
    direction: str | None = None
    status: str | None = "closed"  # closed | open | None for all
    outcome: str | None = None  # win | loss | breakeven
    setup: str | None = None
    emotion: str | None = None
    mistake: str | None = None
    source: str | None = None
    session: str | None = None
    account_id: int | None = None
    search: str | None = None


def _apply(stmt: Select, f: TradeFilter, tz: ZoneInfo) -> Select:
    when = func.coalesce(Trade.close_time, Trade.open_time)
    if f.date_from:
        stmt = stmt.where(when >= local_day_start(f.date_from, tz))
    if f.date_to:
        stmt = stmt.where(when < local_day_start(f.date_to + timedelta(days=1), tz))
    if f.instrument:
        stmt = stmt.where(Trade.instrument == canonical_symbol(f.instrument))
    if f.direction:
        stmt = stmt.where(Trade.direction == normalise_direction(f.direction))
    if f.status:
        stmt = stmt.where(Trade.status == f.status)
    if f.outcome == "win":
        stmt = stmt.where(Trade.net_pnl > 0)
    elif f.outcome == "loss":
        stmt = stmt.where(Trade.net_pnl < 0)
    elif f.outcome == "breakeven":
        stmt = stmt.where(Trade.net_pnl == 0)
    if f.source:
        stmt = stmt.where(Trade.source == f.source)
    if f.session:
        stmt = stmt.where(Trade.session == f.session)
    if f.account_id:
        stmt = stmt.where(Trade.account_id == f.account_id)
    if f.setup or f.emotion or f.mistake or f.search:
        stmt = stmt.outerjoin(TradeJournal, TradeJournal.trade_id == Trade.id)
        if f.setup:
            stmt = stmt.where(func.lower(TradeJournal.setup) == f.setup.lower())
        if f.emotion:
            stmt = stmt.where(cast(TradeJournal.emotions, String).like(f'%"{f.emotion}"%'))
        if f.mistake:
            stmt = stmt.where(cast(TradeJournal.mistakes, String).like(f'%"{f.mistake}"%'))
        if f.search:
            like = f"%{f.search}%"
            stmt = stmt.where(or_(TradeJournal.notes.like(like), Trade.symbol.like(like), TradeJournal.setup.like(like)))
    return stmt


def query_trades(
    session: Session,
    f: TradeFilter,
    sort: str = "-time",
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[Trade], int]:
    tz = get_tz(session)
    base = _apply(select(Trade), f, tz)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    desc = sort.startswith("-")
    col = SORTABLE.get(sort.lstrip("-"), SORTABLE["time"])
    stmt = base.order_by(col.desc() if desc else col.asc(), Trade.id.desc() if desc else Trade.id.asc())
    if limit:
        stmt = stmt.limit(limit).offset(offset)
    trades = list(session.scalars(stmt.options(selectinload(Trade.screenshots))).unique())
    return trades, total


def load_rows(session: Session, f: TradeFilter | None = None) -> list[TradeRow]:
    f = f or TradeFilter()
    f.status = "closed"
    trades, _ = query_trades(session, f, sort="time")
    return rows_from_trades(trades)


def _iso(dt: datetime | None, tz: ZoneInfo) -> str | None:
    return dt.astimezone(tz).isoformat() if dt else None


def _round(x: float | None, nd: int) -> float | None:
    return round(x, nd) if x is not None else None


def journal_dict(j: TradeJournal | None, tz: ZoneInfo) -> dict[str, Any]:
    return {
        "setup": j.setup if j else None,
        "emotions": list(j.emotions or []) if j else [],
        "mistakes": list(j.mistakes or []) if j else [],
        "notes": j.notes if j else None,
        "rating": j.rating if j else None,
        "followed_plan": j.followed_plan if j else None,
        "ai_feedback": j.ai_feedback if j else None,
        "ai_feedback_at": _iso(j.ai_feedback_at, tz) if j else None,
    }


def trade_to_dict(t: Trade, tz: ZoneInfo, detail: bool = False, session: Session | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": t.id,
        "account_id": t.account_id,
        "source": t.source,
        "symbol": t.symbol,
        "instrument": t.instrument,
        "direction": t.direction,
        "status": t.status,
        "volume": t.volume,
        "open_time": _iso(t.open_time, tz),
        "close_time": _iso(t.close_time, tz),
        "entry_price": t.entry_price,
        "exit_price": _round(t.exit_price, 6),
        "initial_sl": t.initial_sl,
        "initial_tp": t.initial_tp,
        "final_sl": t.final_sl,
        "final_tp": t.final_tp,
        "risk_sl": t.risk_sl,
        "sl_source": t.sl_source,
        "sl_delay_seconds": t.sl_delay_seconds,
        "close_reason": t.close_reason,
        "commission": t.commission,
        "swap": t.swap,
        "gross_pnl": t.gross_pnl,
        "net_pnl": t.net_pnl,
        "floating_pnl": t.floating_pnl,
        "r_multiple": _round(t.r_multiple, 2),
        "points": _round(t.points, 1),
        "mfe_points": _round(t.mfe_points, 1),
        "mae_points": _round(t.mae_points, 1),
        "holding_seconds": t.holding_seconds,
        "session": t.session,
        "journal": journal_dict(t.journal, tz),
        "screenshot_count": len(t.screenshots),
    }
    if detail:
        d["screenshots"] = [
            {"id": s.id, "url": f"/screenshots/{s.filename}", "caption": s.caption, "created_at": _iso(s.created_at, tz)}
            for s in t.screenshots
        ]
        d["account"] = {"id": t.account.id, "name": t.account.name, "currency": t.account.currency}
        if session is not None and t.position_id is not None:
            deals = session.scalars(
                select(Deal)
                .where(Deal.account_id == t.account_id, Deal.position_id == t.position_id)
                .order_by(Deal.time_msc, Deal.ticket)
            )
            d["deals"] = [
                {
                    "ticket": x.ticket,
                    "time": _iso(x.time, tz),
                    "type": x.type,
                    "entry": x.entry,
                    "volume": x.volume,
                    "price": x.price,
                    "sl": x.sl,
                    "tp": x.tp,
                    "profit": x.profit,
                    "commission": x.commission + x.fee,
                    "swap": x.swap,
                    "reason": x.reason,
                }
                for x in deals
            ]
        else:
            d["deals"] = []
    return d


def normalise_direction(value: str) -> str:
    v = value.strip().lower()
    if v in ("buy", "long", "b", "l"):
        return "long"
    if v in ("sell", "short", "s"):
        return "short"
    raise ValueError(f"direction must be long/buy or short/sell, got {value!r}")


def resolve_trade(
    session: Session, ref: int | str | None = None, symbol: str | None = None, on_date: date | None = None
) -> Trade | None:
    """Find a trade by id, or the latest one (optionally for a symbol and/or local date)."""
    if ref is not None and str(ref).strip().isdigit():
        return session.get(Trade, int(ref))
    f = TradeFilter(instrument=symbol, status=None, date_from=on_date, date_to=on_date)
    trades, _ = query_trades(session, f, sort="-time", limit=1)
    return trades[0] if trades else None


def find_symbol_spec(session: Session, instrument: str) -> Symbol | None:
    return session.scalar(select(Symbol).where(Symbol.canonical == canonical_symbol(instrument)).limit(1))


def log_manual_trade(
    session: Session,
    *,
    symbol: str,
    direction: str,
    entry_price: float,
    exit_price: float | None = None,
    volume: float | None = None,
    open_time: str | datetime | None = None,
    close_time: str | datetime | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    pnl: float | None = None,
    commission: float = 0.0,
) -> tuple[Trade, list[str]]:
    tz = get_tz(session)
    warnings: list[str] = []
    side = normalise_direction(direction)
    sign = 1 if side == "long" else -1
    instrument = canonical_symbol(symbol)
    closed = exit_price is not None or pnl is not None
    now = datetime.now(UTC)
    opened = parse_local_datetime(open_time, tz)
    closed_at = parse_local_datetime(close_time, tz) if closed else None
    duration_known = opened is not None and closed_at is not None
    if closed and closed_at is None:
        closed_at = opened or now
        warnings.append("Close time not given; using the open time. Tell me when you closed it to fix holding time.")
    opened = opened or closed_at or now

    spec = find_symbol_spec(session, instrument)
    if pnl is None and exit_price is not None and volume and spec and spec.tick_size and spec.tick_value:
        pnl = (exit_price - entry_price) * sign / spec.tick_size * spec.tick_value * volume
        warnings.append("P&L estimated from your broker's tick value; tell me the exact figure to override it.")
    if closed and pnl is None:
        warnings.append("P&L unknown — give the money result (or the lot size) so stats stay accurate.")

    points = r_mult = None
    if exit_price is not None:
        move = (exit_price - entry_price) * sign
        if spec and spec.point:
            points = move / spec.point
        if stop_loss and abs(entry_price - stop_loss) > 0:
            r_mult = move / abs(entry_price - stop_loss)

    dupe = session.scalar(
        select(Trade).where(
            Trade.source == "mt5",
            Trade.instrument == instrument,
            Trade.direction == side,
            Trade.open_time.between(opened - timedelta(minutes=10), opened + timedelta(minutes=10)),
        )
    )
    if dupe is not None:
        warnings.append(
            f"MT5 trade #{dupe.id} looks like the same trade ({dupe.instrument} {dupe.direction} opened "
            f"{_iso(dupe.open_time, tz)}). If so, delete this one and annotate #{dupe.id} instead."
        )

    net = round((pnl or 0.0) + (commission or 0.0), 2)
    trade = Trade(
        account_id=get_manual_account(session).id,
        source="manual",
        symbol=symbol.upper(),
        instrument=instrument,
        direction=side,
        status="closed" if closed else "open",
        volume=volume or 0.0,
        open_time=opened,
        close_time=closed_at,
        entry_price=entry_price,
        exit_price=exit_price,
        initial_sl=stop_loss,
        initial_tp=take_profit,
        final_sl=stop_loss,
        final_tp=take_profit,
        risk_sl=stop_loss,
        sl_source="entry" if stop_loss else None,
        close_reason="manual" if closed else None,
        commission=commission or 0.0,
        gross_pnl=round(pnl or 0.0, 2),
        net_pnl=net,
        r_multiple=r_mult,
        points=points,
        holding_seconds=int((closed_at - opened).total_seconds()) if closed_at and duration_known else None,
        session=session_for_hour(opened.hour, get_setting(session, "sessions")),
    )
    session.add(trade)
    session.flush()
    return trade, warnings
