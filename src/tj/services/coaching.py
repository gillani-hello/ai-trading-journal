"""Bundles of numbers for the UI and for Claude's coaching reviews."""

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from tj.models import Trade
from tj.services.accounts import account_overview, balance_curve
from tj.services.analytics import (
    TradeRow,
    compact_summary,
    daily_pnl,
    equity_curve,
    group_stats,
    instrument_verdict,
    summarize,
)
from tj.services.behavior import detect
from tj.services.insights import insights_for, instrument_insights, overall_insights
from tj.services.journal import day_note_dict, day_notes_between
from tj.services.reports import latest_instrument_section, list_reports
from tj.services.settings import get_all_settings
from tj.services.trades import TradeFilter, get_tz, load_rows, local_day_start, query_trades

PERIODS = {"week": 7, "month": 30, "quarter": 91, "year": 365}


def resolve_period(period: str | None, date_from: date | None, date_to: date | None, today: date) -> tuple[date | None, date | None]:
    """Explicit dates win; otherwise 'week'/'month'/... ending today; 'all' or None means everything."""
    if date_from or date_to:
        return date_from, date_to or today
    if period and period in PERIODS:
        return today - timedelta(days=PERIODS[period] - 1), today
    return None, None


def instrument_breakdown(session: Session, f: TradeFilter, rows: list[TradeRow] | None = None) -> list[dict[str, Any]]:
    tz = get_tz(session)
    rows = rows if rows is not None else load_rows(session, f)
    settings = get_all_settings(session)
    per = instrument_insights(rows, tz)
    out = []
    for g in group_stats(rows, "instrument", tz):
        inst_rows = [r for r in rows if r.instrument == g["key"]]
        s = summarize(inst_rows)
        out.append(
            {
                "instrument": g["key"],
                "verdict": instrument_verdict(s),
                "stats": s,
                "sessions": group_stats(inst_rows, "session", tz),
                "directions": group_stats(inst_rows, "direction", tz),
                "insights": [i.as_dict() for i in per.get(g["key"], [])][:6],
                "flags": [fl.as_dict(max_ids=10) for fl in detect(inst_rows, settings, tz)][:5],
            }
        )
    return out


def instrument_detail(session: Session, symbol: str, f: TradeFilter) -> dict[str, Any]:
    tz = get_tz(session)
    f.instrument = symbol
    rows = load_rows(session, f)
    settings = get_all_settings(session)
    s = summarize(rows)
    return {
        "instrument": rows[0].instrument if rows else symbol.upper(),
        "verdict": instrument_verdict(s),
        "stats": s,
        "equity": equity_curve(rows),
        "breakdowns": {
            by: group_stats(rows, by, tz)
            for by in ("session", "weekday", "direction", "setup", "close_reason", "hold", "emotion", "mistake")
        },
        "insights": [i.as_dict() for i in insights_for(rows[0].instrument if rows else symbol, rows, tz)],
        "flags": [fl.as_dict() for fl in detect(rows, settings, tz)],
        "ai": latest_instrument_section(session, symbol),
    }


def _digest(t: Trade, tz) -> dict[str, Any]:
    j = t.journal
    return {
        "id": t.id,
        "instrument": t.instrument,
        "direction": t.direction,
        "closed": t.close_time.astimezone(tz).strftime("%Y-%m-%d %H:%M") if t.close_time else None,
        "net": t.net_pnl,
        "r": round(t.r_multiple, 2) if t.r_multiple is not None else None,
        "setup": j.setup if j else None,
        "emotions": j.emotions if j else [],
        "mistakes": j.mistakes if j else [],
        "notes": (j.notes or "")[:240] if j else "",
        "rating": j.rating if j else None,
        "followed_plan": j.followed_plan if j else None,
    }


def coaching_context(
    session: Session,
    period: str | None = "week",
    date_from: date | None = None,
    date_to: date | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    """Everything a coach needs to review a period, kept compact for an LLM."""
    tz = get_tz(session)
    today = datetime.now(tz).date()
    start, end = resolve_period(period, date_from, date_to, today)
    f = TradeFilter(date_from=start, date_to=end, instrument=symbol)
    rows = load_rows(session, f)
    settings = get_all_settings(session)

    previous = None
    if start and end:
        span = (end - start).days + 1
        prev_rows = load_rows(
            session, TradeFilter(date_from=start - timedelta(days=span), date_to=start - timedelta(days=1), instrument=symbol)
        )
        previous = compact_summary(prev_rows)

    trades, _ = query_trades(session, TradeFilter(date_from=start, date_to=end, instrument=symbol), sort="-time", limit=400)
    annotated = [t for t in trades if t.journal and (t.journal.notes or t.journal.emotions or t.journal.mistakes or t.journal.setup)]
    by_pnl = sorted(trades, key=lambda t: t.net_pnl)

    notes = day_notes_between(session, start or date(1970, 1, 1), end or today)
    last_report = next(iter(list_reports(session, limit=1)), None)

    return {
        "period": {"from": start.isoformat() if start else None, "to": end.isoformat() if end else None, "timezone": str(tz)},
        "scope": symbol.upper() if symbol else "all instruments",
        "summary": summarize(rows),
        "previous_period": previous,
        "instruments": [
            {k: v for k, v in item.items() if k not in ("sessions", "directions")}
            for item in instrument_breakdown(session, f, rows)
        ],
        "by_session": group_stats(rows, "session", tz),
        "by_weekday": group_stats(rows, "weekday", tz),
        "by_direction": group_stats(rows, "direction", tz),
        "by_setup": group_stats(rows, "setup", tz),
        "by_close_reason": group_stats(rows, "close_reason", tz),
        "by_hold_time": group_stats(rows, "hold", tz),
        "by_emotion": group_stats(rows, "emotion", tz),
        "by_mistake": group_stats(rows, "mistake", tz),
        "behaviour_flags": [fl.as_dict(max_ids=15) for fl in detect(rows, settings, tz)],
        "insights": [i.as_dict() for i in overall_insights(rows, tz)],
        "best_trades": [_digest(t, tz) for t in by_pnl[-5:][::-1] if t.net_pnl > 0],
        "worst_trades": [_digest(t, tz) for t in by_pnl[:5] if t.net_pnl < 0],
        "journal_notes": [_digest(t, tz) for t in annotated[:40]],
        "untagged_trades": sum(1 for t in trades if not (t.journal and t.journal.setup)),
        "day_notes": [day_note_dict(n, n.date) for n in sorted(notes.values(), key=lambda n: n.date)][-14:],
        "trading_rules": settings.get("trading_rules") or "(none written yet — suggest some)",
        "previous_report": {
            "id": last_report.id,
            "title": last_report.title,
            "created_at": last_report.created_at.isoformat(),
            "action_plan": last_report.content.get("action_plan", []),
        }
        if last_report
        else None,
    }


def _previous(session: Session, f: TradeFilter) -> dict[str, Any] | None:
    """Summary of the equally long period just before this one, for deltas."""
    if not (f.date_from and f.date_to):
        return None
    span = (f.date_to - f.date_from).days + 1
    prev = TradeFilter(
        date_from=f.date_from - timedelta(days=span), date_to=f.date_from - timedelta(days=1), account_id=f.account_id
    )
    rows = load_rows(session, prev)
    if not rows:
        return None  # nothing to compare against
    return {"from": prev.date_from.isoformat(), "to": prev.date_to.isoformat(), **summarize(rows)}


def dashboard(session: Session, f: TradeFilter) -> dict[str, Any]:
    tz = get_tz(session)
    rows = load_rows(session, f)
    open_q = session.query(Trade).filter(Trade.status == "open")
    latest = next(iter(list_reports(session, limit=1)), None)
    today = datetime.now(tz).date()
    today_rows = load_rows(session, TradeFilter(date_from=today, date_to=today, account_id=f.account_id))
    start = local_day_start(f.date_from, tz) if f.date_from else None
    end = local_day_start(f.date_to + timedelta(days=1), tz) if f.date_to else None
    return {
        "period": {"from": f.date_from.isoformat() if f.date_from else None, "to": f.date_to.isoformat() if f.date_to else None},
        "account": account_overview(session),
        "balance": balance_curve(session, start, end),
        "previous": _previous(session, f),
        "today": {
            "net_pnl": round(sum(r.net_pnl for r in today_rows), 2),
            "trades": len(today_rows),
            "floating": round(sum(t.floating_pnl or 0.0 for t in open_q), 2),
        },
        "summary": summarize(rows),
        "equity": equity_curve(rows),
        "daily": sorted(daily_pnl(rows, tz).values(), key=lambda d: d["date"]),
        "by_instrument": group_stats(rows, "instrument", tz),
        "by_session": group_stats(rows, "session", tz),
        "insights": [i.as_dict() for i in overall_insights(rows, tz, limit=6)],
        "flags": [fl.as_dict(max_ids=10) for fl in detect(rows, get_all_settings(session), tz)][:5],
        "open_trades": open_q.count(),
        "latest_report": {
            "id": latest.id,
            "title": latest.title,
            "created_at": latest.created_at.isoformat(),
            "summary": latest.summary,
            "action_plan": latest.content.get("action_plan", []),
        }
        if latest
        else None,
    }
