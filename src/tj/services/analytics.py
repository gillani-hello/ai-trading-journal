"""Performance statistics over closed trades. Pure functions, no database access."""

import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from tj.models import Trade

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOLD_BUCKETS = [
    (5 * 60, "<5m"),
    (30 * 60, "5–30m"),
    (2 * 3600, "30m–2h"),
    (8 * 3600, "2–8h"),
    (24 * 3600, "8h–1d"),
    (float("inf"), ">1d"),
]
GROUPINGS = (
    "instrument", "direction", "session", "weekday", "hour", "setup", "emotion", "mistake",
    "close_reason", "hold", "month", "source",
)  # fmt: skip


@dataclass
class TradeRow:
    id: int
    instrument: str
    direction: str
    source: str
    open_time: datetime
    close_time: datetime
    volume: float
    net_pnl: float
    entry_price: float
    exit_price: float | None
    r_multiple: float | None
    points: float | None
    mfe_points: float | None
    mae_points: float | None
    holding_seconds: int | None
    session: str | None
    close_reason: str | None
    initial_sl: float | None
    final_sl: float | None
    risk_sl: float | None = None
    sl_source: str | None = None  # entry | added | close
    sl_delay_seconds: int | None = None
    setup: str | None = None
    emotions: list[str] = field(default_factory=list)
    mistakes: list[str] = field(default_factory=list)
    followed_plan: bool | None = None
    has_notes: bool = False

    @property
    def is_win(self) -> bool:
        return self.net_pnl > 0

    @property
    def is_loss(self) -> bool:
        return self.net_pnl < 0


def rows_from_trades(trades: Iterable[Trade]) -> list[TradeRow]:
    rows = []
    for t in trades:
        if t.status != "closed" or t.close_time is None:
            continue
        j = t.journal
        rows.append(
            TradeRow(
                id=t.id,
                instrument=t.instrument,
                direction=t.direction,
                source=t.source,
                open_time=t.open_time,
                close_time=t.close_time,
                volume=t.volume,
                net_pnl=t.net_pnl,
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                r_multiple=t.r_multiple,
                points=t.points,
                mfe_points=t.mfe_points,
                mae_points=t.mae_points,
                holding_seconds=t.holding_seconds,
                session=t.session,
                close_reason=t.close_reason,
                initial_sl=t.initial_sl,
                final_sl=t.final_sl,
                risk_sl=t.risk_sl,
                sl_source=t.sl_source,
                sl_delay_seconds=t.sl_delay_seconds,
                setup=j.setup if j else None,
                emotions=list(j.emotions or []) if j else [],
                mistakes=list(j.mistakes or []) if j else [],
                followed_plan=j.followed_plan if j else None,
                has_notes=bool(j and j.notes),
            )
        )
    rows.sort(key=lambda r: (r.close_time, r.id))
    return rows


def _r(x: float | None, nd: int = 2) -> float | None:
    return round(x, nd) if x is not None else None


def _streaks(rows: list[TradeRow]) -> tuple[int, int]:
    best_w = best_l = cur_w = cur_l = 0
    for r in rows:
        if r.is_win:
            cur_w, cur_l = cur_w + 1, 0
        elif r.is_loss:
            cur_w, cur_l = 0, cur_l + 1
        best_w, best_l = max(best_w, cur_w), max(best_l, cur_l)
    return best_w, best_l


def max_drawdown(rows: list[TradeRow]) -> float:
    peak = equity = dd = 0.0
    for r in rows:
        equity += r.net_pnl
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    return round(dd, 2)


def summarize(rows: list[TradeRow]) -> dict[str, Any]:
    n = len(rows)
    wins = [r for r in rows if r.is_win]
    losses = [r for r in rows if r.is_loss]
    gross_profit = sum(r.net_pnl for r in wins)
    gross_loss = sum(r.net_pnl for r in losses)
    net = gross_profit + gross_loss
    avg_win = gross_profit / len(wins) if wins else None
    avg_loss = gross_loss / len(losses) if losses else None
    rs = [r.r_multiple for r in rows if r.r_multiple is not None]
    hold_w = [r.holding_seconds for r in wins if r.holding_seconds is not None]
    hold_l = [r.holding_seconds for r in losses if r.holding_seconds is not None]
    max_w, max_l = _streaks(rows)
    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": n - len(wins) - len(losses),
        "win_rate": _r(len(wins) / n, 4) if n else None,
        "net_pnl": round(net, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": _r(gross_profit / -gross_loss) if gross_loss < 0 else None,
        "expectancy": _r(net / n) if n else None,
        "avg_win": _r(avg_win),
        "avg_loss": _r(avg_loss),
        "payoff_ratio": _r(avg_win / -avg_loss) if avg_win and avg_loss else None,
        "largest_win": _r(max((r.net_pnl for r in wins), default=None)),
        "largest_loss": _r(min((r.net_pnl for r in losses), default=None)),
        "avg_r": _r(statistics.fmean(rs)) if rs else None,
        "total_r": _r(sum(rs)) if rs else None,
        "trades_with_r": len(rs),
        "avg_hold_win_min": _r(statistics.fmean(hold_w) / 60, 1) if hold_w else None,
        "avg_hold_loss_min": _r(statistics.fmean(hold_l) / 60, 1) if hold_l else None,
        "max_consecutive_wins": max_w,
        "max_consecutive_losses": max_l,
        "max_drawdown": max_drawdown(rows),
        "long_trades": sum(1 for r in rows if r.direction == "long"),
        "short_trades": sum(1 for r in rows if r.direction == "short"),
    }


def compact_summary(rows: list[TradeRow]) -> dict[str, Any]:
    s = summarize(rows)
    keys = ("trades", "win_rate", "net_pnl", "profit_factor", "expectancy", "avg_r", "avg_win", "avg_loss")
    return {k: s[k] for k in keys}


def _hold_bucket(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    return next(label for limit, label in HOLD_BUCKETS if seconds < limit)


def key_fn(by: str, tz: ZoneInfo) -> Callable[[TradeRow], list[str]]:
    if by not in GROUPINGS:
        raise ValueError(f"group_by must be one of {', '.join(GROUPINGS)}")
    simple: dict[str, Callable[[TradeRow], Any]] = {
        "instrument": lambda r: r.instrument,
        "direction": lambda r: r.direction,
        "session": lambda r: r.session or "unknown",
        "weekday": lambda r: WEEKDAYS[r.open_time.astimezone(tz).weekday()],
        "hour": lambda r: f"{r.open_time.astimezone(tz).hour:02d}:00",
        "setup": lambda r: r.setup or "(untagged)",
        "close_reason": lambda r: r.close_reason or "unknown",
        "hold": lambda r: _hold_bucket(r.holding_seconds),
        "month": lambda r: r.close_time.astimezone(tz).strftime("%Y-%m"),
        "source": lambda r: r.source,
    }
    if by == "emotion":
        return lambda r: r.emotions or ["(none)"]
    if by == "mistake":
        return lambda r: r.mistakes or ["(none)"]
    fn = simple[by]
    return lambda r: [fn(r)]


def group_stats(rows: list[TradeRow], by: str, tz: ZoneInfo) -> list[dict[str, Any]]:
    keyf = key_fn(by, tz)
    groups: dict[str, list[TradeRow]] = defaultdict(list)
    for r in rows:
        for k in keyf(r):
            groups[k].append(r)
    out = [{"key": k, **compact_summary(g)} for k, g in groups.items()]
    if by == "weekday":
        out.sort(key=lambda g: WEEKDAYS.index(g["key"]))
    elif by in ("hour", "month"):
        out.sort(key=lambda g: g["key"])
    elif by == "hold":
        order = [label for _, label in HOLD_BUCKETS] + ["unknown"]
        out.sort(key=lambda g: order.index(g["key"]))
    else:
        out.sort(key=lambda g: g["net_pnl"], reverse=True)
    return out


def equity_curve(rows: list[TradeRow]) -> list[dict[str, Any]]:
    total = 0.0
    curve = []
    for r in rows:
        total += r.net_pnl
        curve.append({"time": r.close_time.isoformat(), "trade_id": r.id, "pnl": r.net_pnl, "equity": round(total, 2)})
    return curve


def daily_pnl(rows: list[TradeRow], tz: ZoneInfo) -> dict[str, dict[str, Any]]:
    """Per local close date: net, trades, wins, losses."""
    days: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = r.close_time.astimezone(tz).date().isoformat()
        d = days.setdefault(key, {"date": key, "net_pnl": 0.0, "trades": 0, "wins": 0, "losses": 0})
        d["net_pnl"] = round(d["net_pnl"] + r.net_pnl, 2)
        d["trades"] += 1
        d["wins"] += r.is_win
        d["losses"] += r.is_loss
    return days


def instrument_verdict(summary: dict[str, Any]) -> str:
    """edge | leaking | breakeven | unproven — the label shown on instrument cards."""
    n, net, pf = summary["trades"], summary["net_pnl"], summary["profit_factor"]
    if n < 5:
        return "unproven"
    if net < 0 and (pf is None or pf < 0.95):
        return "leaking"
    if net > 0 and (pf is None or pf >= 1.2):
        return "edge"
    return "breakeven"
