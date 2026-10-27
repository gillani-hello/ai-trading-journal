"""MCP server: lets Claude log, annotate, query and coach from the journal.

Run with `tj mcp` (stdio). Every tool first syncs new MT5 trades (at most once
every 30 s), so answers include the latest fills even when the web app is off.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import Field

from mcp.server.mcpserver import MCPServer
from tj.config import get_settings
from tj.db import init_db, session_scope
from tj.ingest import watcher
from tj.models import Trade
from tj.services import calendar as cal
from tj.services import coaching, journal, reports
from tj.services.analytics import GROUPINGS, group_stats, summarize
from tj.services.behavior import detect
from tj.services.settings import get_all_settings, update_settings
from tj.services.trades import (
    TradeFilter,
    get_tz,
    load_rows,
    log_manual_trade,
    query_trades,
    resolve_trade,
    trade_to_dict,
)

INSTRUCTIONS = """\
This is the user's personal trading journal. Trades from their MetaTrader 5 account arrive automatically;
they can also dictate trades that happened elsewhere.

How to help:
- When the user describes a trade that MT5 already has (most of them), do NOT log it again: use
  annotate_trade (trade="last", or a symbol/date, or an id) to add setup, emotions, mistakes, notes, rating.
- Use log_trade only for trades MT5 doesn't know about. If it warns about a likely duplicate, tell the user.
- Use list_tags and reuse existing tag names so statistics group cleanly.
- For analysis, call get_coaching_context (or the narrower tools), reason from the numbers, cite them,
  then save the result with save_ai_report so it appears in the web app's AI Coach page.
- Be specific per instrument: what works, what leaks money, and concrete rules to fix it.
- Times are in the user's display timezone. Money is in the account currency.
- You are not a licensed financial adviser: coach on process, discipline and the trader's own statistics,
  never recommend specific trades to take.
"""

Period = Annotated[
    Literal["week", "month", "quarter", "year", "all"] | None,
    Field(description="Rolling window ending today. Ignored when date_from/date_to are given."),
]
DateFrom = Annotated[date | None, Field(description="Start date (YYYY-MM-DD), inclusive")]
DateTo = Annotated[date | None, Field(description="End date (YYYY-MM-DD), inclusive")]
Symbol = Annotated[str | None, Field(description="Instrument, e.g. EURUSD or XAUUSD (broker suffixes are ignored)")]


@asynccontextmanager
async def _lifespan(_server: MCPServer) -> AsyncIterator[None]:
    init_db()
    watcher.run_sync()
    yield


mcp = MCPServer("trading-journal", instructions=INSTRUCTIONS, lifespan=_lifespan)


def _app_url(path: str = "") -> str:
    s = get_settings()
    return f"http://{s.host}:{s.port}{path}"


def _compact(t: Trade, tz) -> dict[str, Any]:
    j = t.journal
    when = t.close_time or t.open_time
    return {
        "id": t.id,
        "time": when.astimezone(tz).strftime("%Y-%m-%d %H:%M"),
        "instrument": t.instrument,
        "direction": t.direction,
        "status": t.status,
        "volume": t.volume,
        "entry": t.entry_price,
        "exit": round(t.exit_price, 6) if t.exit_price is not None else None,
        "sl": t.risk_sl,
        "sl_set": t.sl_source,  # entry = on the order, added = after entry, close = only seen at close
        "net": t.net_pnl if t.status == "closed" else t.floating_pnl,
        "r": round(t.r_multiple, 2) if t.r_multiple is not None else None,
        "close_reason": t.close_reason,
        "session": t.session,
        "source": t.source,
        "setup": j.setup if j else None,
        "emotions": j.emotions if j else [],
        "mistakes": j.mistakes if j else [],
        "notes": (j.notes or "")[:120] if j else "",
    }


def _period(f: TradeFilter) -> dict[str, str | None]:
    return {"from": f.date_from.isoformat() if f.date_from else None, "to": f.date_to.isoformat() if f.date_to else None}


def _filter(period, date_from, date_to, symbol, session) -> TradeFilter:
    today = datetime.now(get_tz(session)).date()
    start, end = coaching.resolve_period(period, date_from, date_to, today)
    return TradeFilter(date_from=start, date_to=end, instrument=symbol)


def _merge(existing: list[str], new: list[str] | None, replace: bool) -> list[str] | None:
    if new is None:
        return None
    return new if replace else existing + [x for x in new if x not in existing]


# Logging and annotating -----------------------------------------------------


@mcp.tool()
def log_trade(
    symbol: Annotated[str, Field(description="Instrument, e.g. EURUSD")],
    direction: Annotated[str, Field(description="long/buy or short/sell")],
    entry_price: float,
    exit_price: Annotated[float | None, Field(description="Leave empty if the trade is still open")] = None,
    volume: Annotated[float | None, Field(description="Lots")] = None,
    open_time: Annotated[str | None, Field(description="ISO datetime, e.g. 2026-10-26T09:30 (local time)")] = None,
    close_time: Annotated[str | None, Field(description="ISO datetime (local time)")] = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    pnl: Annotated[float | None, Field(description="Money result before commission, if the user said it")] = None,
    commission: float = 0.0,
    setup: str | None = None,
    emotions: list[str] | None = None,
    mistakes: list[str] | None = None,
    notes: str | None = None,
    rating: Annotated[int | None, Field(ge=1, le=5, description="Execution quality 1-5")] = None,
    followed_plan: bool | None = None,
) -> dict[str, Any]:
    """Log a trade the user dictates that is NOT in MT5 (other broker, or not synced). Returns the trade and warnings."""
    watcher.maybe_sync()
    with session_scope() as s:
        trade, warnings = log_manual_trade(
            s, symbol=symbol, direction=direction, entry_price=entry_price, exit_price=exit_price, volume=volume,
            open_time=open_time, close_time=close_time, stop_loss=stop_loss, take_profit=take_profit, pnl=pnl,
            commission=commission,
        )  # fmt: skip
        journal.update_journal(
            s, trade, setup=setup, emotions=emotions or [], mistakes=mistakes or [], notes=notes,
            rating=rating, followed_plan=followed_plan,
        )  # fmt: skip
        return {"trade": trade_to_dict(trade, get_tz(s)), "warnings": warnings, "view": _app_url(f"/trades/{trade.id}")}


@mcp.tool()
def annotate_trade(
    trade: Annotated[str, Field(description='Trade id, or "last" for the most recent trade (optionally narrowed by symbol/date)')] = "last",
    symbol: Symbol = None,
    on_date: Annotated[date | None, Field(description="Narrow 'last' to trades closed on this date")] = None,
    setup: str | None = None,
    emotions: Annotated[list[str] | None, Field(description="Added to existing emotions unless replace_tags is true")] = None,
    mistakes: Annotated[list[str] | None, Field(description="Added to existing mistakes unless replace_tags is true")] = None,
    notes: Annotated[str | None, Field(description="Appended to existing notes unless replace_notes is true")] = None,
    rating: Annotated[int | None, Field(ge=1, le=5)] = None,
    followed_plan: bool | None = None,
    replace_tags: bool = False,
    replace_notes: bool = False,
) -> dict[str, Any]:
    """Add journal details (setup, emotions, mistakes, notes, rating) to a trade, usually one synced from MT5."""
    watcher.maybe_sync()
    with session_scope() as s:
        t = resolve_trade(s, trade if trade != "last" else None, symbol, on_date)
        if t is None:
            return {"error": "No matching trade found. Try find_trades to locate it."}
        j = t.journal
        kwargs: dict[str, Any] = {}
        if setup is not None:
            kwargs["setup"] = setup
        if (merged := _merge(list(j.emotions) if j else [], emotions, replace_tags)) is not None:
            kwargs["emotions"] = merged
        if (merged := _merge(list(j.mistakes) if j else [], mistakes, replace_tags)) is not None:
            kwargs["mistakes"] = merged
        if notes is not None:
            kwargs["notes"] = notes
        if rating is not None:
            kwargs["rating"] = rating
        if followed_plan is not None:
            kwargs["followed_plan"] = followed_plan
        journal.update_journal(s, t, append_notes=not replace_notes, **kwargs)
        return {"trade": _compact(t, get_tz(s)), "view": _app_url(f"/trades/{t.id}")}


@mcp.tool()
def delete_trade(trade_id: int) -> dict[str, Any]:
    """Delete a manually logged trade (MT5 trades can't be deleted; they come back on sync)."""
    with session_scope() as s:
        t = s.get(Trade, trade_id)
        if t is None:
            return {"error": f"Trade {trade_id} not found"}
        if t.source != "manual":
            return {"error": "Only manually logged trades can be deleted; MT5 trades mirror your account history."}
        s.delete(t)
        return {"deleted": trade_id}


@mcp.tool()
def write_day_note(
    day: Annotated[date | None, Field(description="Defaults to today")] = None,
    pre_session_plan: str | None = None,
    post_session_review: str | None = None,
    mood: Annotated[str | None, Field(description="One word, e.g. focused, tired, anxious")] = None,
    rules_followed: bool | None = None,
) -> dict[str, Any]:
    """Save the pre-session plan or post-session review for a day (text is appended to what is there)."""
    with session_scope() as s:
        d = day or datetime.now(get_tz(s)).date()
        kwargs: dict[str, Any] = {}
        for k, v in (("pre_session_plan", pre_session_plan), ("post_session_review", post_session_review),
                     ("mood", mood), ("rules_followed", rules_followed)):  # fmt: skip
            if v is not None:
                kwargs[k] = v
        note = journal.upsert_day_note(s, d, append=True, **kwargs)
        return journal.day_note_dict(note, d)


@mcp.tool()
def list_tags() -> dict[str, list[str]]:
    """The user's setup, emotion and mistake vocabularies. Reuse these names when tagging."""
    with session_scope() as s:
        return journal.list_tags(s)


@mcp.tool()
def set_trading_rules(rules: Annotated[str, Field(description="The user's full trading plan/rules as text")]) -> dict[str, str]:
    """Save the user's written trading rules; coaching reviews check behaviour against them."""
    with session_scope() as s:
        update_settings(s, {"trading_rules": rules})
    return {"saved": "ok"}


# Reading ----------------------------------------------------------------------


@mcp.tool()
def find_trades(
    period: Period = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    symbol: Symbol = None,
    direction: Literal["long", "short"] | None = None,
    outcome: Literal["win", "loss", "breakeven"] | None = None,
    status: Literal["closed", "open", "all"] = "all",
    setup: str | None = None,
    emotion: str | None = None,
    mistake: str | None = None,
    source: Literal["mt5", "manual"] | None = None,
    sort: Annotated[str, Field(description="time, net_pnl, r_multiple, volume, holding; prefix - for descending")] = "-time",
    limit: Annotated[int, Field(ge=1, le=200)] = 20,
) -> dict[str, Any]:
    """Search trades. Returns a compact list plus the total count."""
    watcher.maybe_sync()
    with session_scope() as s:
        f = _filter(period, date_from, date_to, symbol, s)
        f.direction, f.outcome, f.setup, f.emotion, f.mistake, f.source = direction, outcome, setup, emotion, mistake, source
        f.status = None if status == "all" else status
        trades, total = query_trades(s, f, sort=sort, limit=limit)
        tz = get_tz(s)
        return {"total": total, "shown": len(trades), "trades": [_compact(t, tz) for t in trades]}


@mcp.tool()
def get_trade(trade_id: int) -> dict[str, Any]:
    """Full detail of one trade: prices, costs, R, MFE/MAE, deals, journal, and any behaviour flags it triggered."""
    with session_scope() as s:
        t = s.get(Trade, trade_id)
        if t is None:
            return {"error": f"Trade {trade_id} not found"}
        tz = get_tz(s)
        d = trade_to_dict(t, tz, detail=True, session=s)
        rows = load_rows(s, TradeFilter(instrument=None))
        d["flags"] = [f.title for f in detect(rows, get_all_settings(s), tz) if trade_id in f.trade_ids]
        return d


@mcp.tool()
def get_performance(
    period: Period = "month",
    date_from: DateFrom = None,
    date_to: DateTo = None,
    symbol: Symbol = None,
    group_by: Annotated[
        list[str] | None, Field(description=f"Any of: {', '.join(GROUPINGS)}")
    ] = None,
) -> dict[str, Any]:
    """Win rate, P&L, profit factor, expectancy, R, drawdown, streaks — optionally broken down by dimension."""
    watcher.maybe_sync()
    with session_scope() as s:
        f = _filter(period, date_from, date_to, symbol, s)
        rows = load_rows(s, f)
        tz = get_tz(s)
        out: dict[str, Any] = {
            "period": _period(f),
            "scope": symbol or "all instruments",
            "summary": summarize(rows),
        }
        for by in group_by or []:
            out[f"by_{by}"] = group_stats(rows, by, tz)
        return out


@mcp.tool()
def get_instrument_breakdown(period: Period = "month", date_from: DateFrom = None, date_to: DateTo = None) -> dict[str, Any]:
    """Per-instrument stats, verdict (edge/leaking/breakeven/unproven), best/worst sessions, insights and red flags."""
    watcher.maybe_sync()
    with session_scope() as s:
        f = _filter(period, date_from, date_to, None, s)
        return {"period": _period(f), "instruments": coaching.instrument_breakdown(s, f)}


@mcp.tool()
def get_calendar(month: Annotated[str | None, Field(description="YYYY-MM, defaults to the current month")] = None) -> dict[str, Any]:
    """Daily P&L for a month (trading days only), weekly totals and the month summary."""
    watcher.maybe_sync()
    with session_scope() as s:
        today = datetime.now(get_tz(s)).date()
        year, mon = (int(x) for x in month.split("-")) if month else (today.year, today.month)
        c = cal.month_calendar(s, year, mon)
        return {
            "month": f"{year}-{mon:02d}",
            "summary": c["summary"],
            "green_days": c["green_days"],
            "red_days": c["red_days"],
            "days": [
                {k: d[k] for k in ("date", "net_pnl", "trades", "win_rate", "mood")}
                for w in c["weeks"]
                for d in w["days"]
                if d["in_month"] and d["trades"]
            ],
            "weeks": [{"week_start": w["week_start"], "net_pnl": w["net_pnl"], "trades": w["trades"]} for w in c["weeks"]],
        }


@mcp.tool()
def get_behavior_report(period: Period = "month", date_from: DateFrom = None, date_to: DateTo = None, symbol: Symbol = None) -> dict[str, Any]:
    """Behavioural red flags (revenge trading, overtrading, no/widened stops, early exits, sizing up after losses...) with cost."""
    watcher.maybe_sync()
    with session_scope() as s:
        f = _filter(period, date_from, date_to, symbol, s)
        rows = load_rows(s, f)
        return {"trades_analysed": len(rows), "flags": [x.as_dict(max_ids=20) for x in detect(rows, get_all_settings(s), get_tz(s))]}


@mcp.tool()
def get_coaching_context(period: Period = "week", date_from: DateFrom = None, date_to: DateTo = None, symbol: Symbol = None) -> dict[str, Any]:
    """Everything needed for a coaching review in one call: stats vs previous period, per-instrument verdicts and
    insights, breakdowns, behaviour flags, best/worst trades, journal notes, day notes, the user's trading rules
    and the previous report's action plan."""
    watcher.maybe_sync()
    with session_scope() as s:
        return coaching.coaching_context(s, period=period, date_from=date_from, date_to=date_to, symbol=symbol)


# Writing analysis back --------------------------------------------------------


@mcp.tool()
def save_ai_report(report: reports.AIReportIn) -> dict[str, Any]:
    """Save a coaching review so it shows in the web app (AI Coach page and each instrument's page).
    Every claim should be backed by numbers from the journal."""
    with session_scope() as s:
        row = reports.save_report(s, report)
        return {"id": row.id, "view": _app_url(f"/coach/{row.id}")}


@mcp.tool()
def save_trade_feedback(trade_id: int, feedback: Annotated[str, Field(description="Coaching feedback on this trade")]) -> dict[str, Any]:
    """Attach AI feedback to a single trade (shown on the trade's page)."""
    with session_scope() as s:
        t = s.get(Trade, trade_id)
        if t is None:
            return {"error": f"Trade {trade_id} not found"}
        journal.set_ai_feedback(s, t, feedback)
        return {"saved": trade_id, "view": _app_url(f"/trades/{trade_id}")}


@mcp.tool()
def sync_mt5(force: Annotated[bool, Field(description="Re-read every file and rebuild all trades")] = False) -> dict[str, Any]:
    """Pull the latest trades from MT5 right now."""
    return watcher.run_sync(force=force).as_dict()


# Prompts ------------------------------------------------------------------------

_REVIEW = """\
Run a {label} trading review{scope}.

1. Call get_coaching_context with {args}.
2. Analyse it like a demanding but supportive trading coach:
   - Overall: what changed vs the previous period, and whether the previous action plan was followed.
   - For EVERY instrument traded: verdict, what is working, what is leaking money, specific improvements,
     and 1-3 concrete if/then rules. Quote the numbers (win rate, net, R, sessions, flags).
   - Psychology: patterns in the behaviour flags, emotions/mistakes tags and notes.
   - Compare behaviour against the user's trading rules.
3. Save it with save_ai_report (kind="{kind}"{symbol_arg}), with a 3-5 item action plan for next period.
4. Then give me a short conversational summary and the link to the saved report.
If there are few trades, say so and keep conclusions tentative. Coach process and discipline; do not recommend specific trades.
"""


@mcp.prompt()
def weekly_review() -> str:
    """Review the last 7 days and save a coaching report."""
    return _REVIEW.format(label="weekly", scope="", args='period="week"', kind="weekly", symbol_arg="")


@mcp.prompt()
def monthly_review() -> str:
    """Review the last 30 days and save a coaching report."""
    return _REVIEW.format(label="monthly", scope="", args='period="month"', kind="monthly", symbol_arg="")


@mcp.prompt()
def instrument_review(symbol: str) -> str:
    """Deep-dive one instrument over the last quarter."""
    return _REVIEW.format(
        label=f"{symbol} instrument",
        scope=f" focused only on {symbol}",
        args=f'period="quarter", symbol="{symbol}"',
        kind="instrument",
        symbol_arg=f', symbol="{symbol}"',
    )


@mcp.prompt()
def trade_review(trade_id: str) -> str:
    """Review one trade and attach feedback to it."""
    return (
        f"Review trade {trade_id}. Call get_trade({trade_id}), then get_performance for its instrument "
        "(period='quarter', group_by=['session','setup']) for context. Judge entry, stop placement, exit "
        "(use MFE/MAE and close reason), sizing and the journal notes. Save 3-6 sentences of feedback with "
        "save_trade_feedback, then summarise for me."
    )


@mcp.prompt()
def log_trades() -> str:
    """Dictate one or more trades or annotations."""
    return (
        "I'm going to tell you about my trades. For each one: if it's in MT5 (check with find_trades for that "
        "symbol and day), use annotate_trade to add my setup, emotions, mistakes, notes and rating; otherwise use "
        "log_trade. Call list_tags first and reuse tag names. Ask me briefly for anything important that's missing "
        "(direction, entry, exit or result, stop). Confirm what you saved in one line per trade."
    )


def main() -> None:
    mcp.run("stdio")
