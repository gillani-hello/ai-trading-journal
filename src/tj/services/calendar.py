"""Monthly P&L calendar, bucketed by close date in the display timezone."""

import calendar as pycal
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from tj.services.analytics import compact_summary, daily_pnl
from tj.services.journal import day_notes_between
from tj.services.trades import TradeFilter, get_tz, load_rows


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, pycal.monthrange(year, month)[1])


def month_calendar(session: Session, year: int, month: int, account_id: int | None = None) -> dict[str, Any]:
    tz: ZoneInfo = get_tz(session)
    first, last = month_bounds(year, month)
    grid_start = first - timedelta(days=first.weekday())  # Monday
    grid_end = last + timedelta(days=6 - last.weekday())  # Sunday

    rows = load_rows(session, TradeFilter(date_from=grid_start, date_to=grid_end, account_id=account_id))
    days = daily_pnl(rows, tz)
    notes = day_notes_between(session, grid_start, grid_end)
    month_rows = [r for r in rows if first <= r.close_time.astimezone(tz).date() <= last]

    weeks = []
    d = grid_start
    while d <= grid_end:
        week_days = []
        for _ in range(7):
            key = d.isoformat()
            info = days.get(key, {"net_pnl": 0.0, "trades": 0, "wins": 0, "losses": 0})
            note = notes.get(key)
            week_days.append(
                {
                    "date": key,
                    "in_month": d.month == month,
                    "net_pnl": info["net_pnl"],
                    "trades": info["trades"],
                    "wins": info["wins"],
                    "losses": info["losses"],
                    "win_rate": round(info["wins"] / info["trades"], 3) if info["trades"] else None,
                    "has_note": bool(note and (note.pre_session_plan or note.post_session_review)),
                    "mood": note.mood if note else None,
                }
            )
            d += timedelta(days=1)
        in_month = [x for x in week_days if x["in_month"]]
        weeks.append(
            {
                "week_start": week_days[0]["date"],
                "days": week_days,
                "net_pnl": round(sum(x["net_pnl"] for x in in_month), 2),
                "trades": sum(x["trades"] for x in in_month),
                "trading_days": sum(1 for x in in_month if x["trades"]),
            }
        )

    traded = [x for w in weeks for x in w["days"] if x["in_month"] and x["trades"]]
    return {
        "year": year,
        "month": month,
        "timezone": str(tz),
        "summary": compact_summary(month_rows),
        "trading_days": len(traded),
        "green_days": sum(1 for x in traded if x["net_pnl"] > 0),
        "red_days": sum(1 for x in traded if x["net_pnl"] < 0),
        "best_day": max(traded, key=lambda x: x["net_pnl"], default=None),
        "worst_day": min(traded, key=lambda x: x["net_pnl"], default=None),
        "max_abs_day": max((abs(x["net_pnl"]) for x in traded), default=0),
        "weeks": weeks,
    }
