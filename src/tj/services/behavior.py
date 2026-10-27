"""Behavioural red flags: patterns that usually cost traders money.

Each flag lists the trades involved and what they cost, so both the UI and the
AI coach can point at concrete evidence instead of generic advice.
"""

import bisect
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from tj.services.analytics import WEEKDAYS, TradeRow, compact_summary, group_stats, summarize

MIN_GROUP = 5  # trades needed before calling a session or weekday weak


@dataclass
class Flag:
    code: str
    title: str
    severity: str  # high | medium | low
    description: str
    trade_ids: list[int] = field(default_factory=list)
    cost: float = 0.0  # net P&L of the flagged trades (negative = money lost)
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self, max_ids: int = 50) -> dict[str, Any]:
        d = asdict(self)
        d["count"] = len(self.trade_ids)
        d["trade_ids"] = self.trade_ids[:max_ids]
        d["cost"] = round(self.cost, 2)
        return d


def _money(x: float) -> str:
    return f"{'-' if x < 0 else '+'}{abs(x):,.2f}"


def _cost(rows: list[TradeRow]) -> float:
    return sum(r.net_pnl for r in rows)


def _severity(cost: float, total_loss: float) -> str:
    share = -cost / total_loss if total_loss else 0
    return "high" if share >= 0.25 else "medium" if share >= 0.1 else "low"


def detect(rows: list[TradeRow], settings: dict[str, Any], tz: ZoneInfo) -> list[Flag]:
    if not rows:
        return []
    total_loss = -sum(r.net_pnl for r in rows if r.is_loss) or 1.0
    flags: list[Flag] = []
    by_open = sorted(rows, key=lambda r: r.open_time)

    # Revenge trading: a new trade soon after a losing close.
    window = timedelta(minutes=settings["revenge_minutes"])
    revenge, bigger = [], 0
    by_close = sorted(rows, key=lambda r: r.close_time)
    close_times = [r.close_time for r in by_close]
    for r in by_open:
        i = bisect.bisect_right(close_times, r.open_time) - 1
        if i < 0:
            continue
        last = by_close[i]
        if last.id != r.id and last.is_loss and r.open_time - last.close_time <= window:
            revenge.append(r)
            bigger += r.volume > last.volume
    if revenge:
        cost = _cost(revenge)
        wr = sum(r.is_win for r in revenge) / len(revenge)
        flags.append(
            Flag(
                "revenge_trading",
                "Re-entering quickly after losses",
                "high" if cost < 0 and bigger else _severity(cost, total_loss),
                f"{len(revenge)} trades opened within {settings['revenge_minutes']} min of a losing close "
                f"({bigger} with bigger size). Win rate {wr:.0%}, net {_money(cost)}.",
                [r.id for r in revenge],
                cost,
                {"bigger_size": bigger, "win_rate": round(wr, 3)},
            )
        )

    # Overtrading: trades beyond the daily limit.
    per_day: dict[str, list[TradeRow]] = defaultdict(list)
    for r in by_open:
        per_day[r.open_time.astimezone(tz).date().isoformat()].append(r)
    limit = settings["max_trades_per_day"]
    excess = [r for day in per_day.values() if len(day) > limit for r in day[limit:]]
    if excess:
        days = [d for d, day in per_day.items() if len(day) > limit]
        cost = _cost(excess)
        flags.append(
            Flag(
                "overtrading",
                f"More than {limit} trades a day",
                _severity(cost, total_loss) if cost < 0 else "low",
                f"{len(days)} day(s) above your {limit}-trade limit. The {len(excess)} trades past the limit "
                f"netted {_money(cost)}.",
                [r.id for r in excess],
                cost,
                {"days": days[:20]},
            )
        )

    # Never protected by a stop at all.
    no_sl = [r for r in rows if r.source == "mt5" and r.risk_sl is None and r.final_sl is None]
    if no_sl:
        cost = _cost(no_sl)
        flags.append(
            Flag(
                "no_stop_loss",
                "Trades with no stop-loss at all",
                "high" if cost < 0 else "medium",
                f"{len(no_sl)} trades never had a stop-loss, net {_money(cost)}. "
                f"Largest loss among them: {_money(min(r.net_pnl for r in no_sl))}.",
                [r.id for r in no_sl],
                cost,
            )
        )

    # Opened unprotected, stop added afterwards.
    late = [
        r
        for r in rows
        if r.source == "mt5" and r.sl_source != "entry" and (r.sl_source is not None or r.final_sl is not None)
    ]
    if late:
        cost = _cost(late)
        delays = sorted(r.sl_delay_seconds for r in late if r.sl_delay_seconds is not None)
        timing = f" The stop came a median {delays[len(delays) // 2] / 60:.0f} min after entry." if delays else ""
        flags.append(
            Flag(
                "late_stop",
                "Stop-loss added after entry",
                "medium" if len(late) / len(rows) >= 0.3 else "low",
                f"{len(late)} of {len(rows)} trades were opened without a stop on the order; the stop was set afterwards."
                f"{timing} Until then the position is unprotected against a fast move. These trades netted {_money(cost)}.",
                [r.id for r in late],
                cost,
                {"median_delay_seconds": delays[len(delays) // 2] if delays else None},
            )
        )

    # Stop widened after it was set, on losing trades (ignoring moves under 10% of the risk).
    def _widened(r: TradeRow) -> bool:
        if not (r.is_loss and r.risk_sl is not None and r.final_sl is not None):
            return False
        risk = abs(r.entry_price - r.risk_sl)
        moved = (r.risk_sl - r.final_sl) if r.direction == "long" else (r.final_sl - r.risk_sl)
        return risk > 0 and moved > 0.1 * risk

    widened = [r for r in rows if _widened(r)]
    if widened:
        cost = _cost(widened)
        flags.append(
            Flag(
                "stop_widened",
                "Stop-loss moved further away on losers",
                "high",
                f"On {len(widened)} losing trade{'s' if len(widened) > 1 else ''} the stop was moved away from entry, turning planned losses "
                f"into bigger ones (net {_money(cost)}).",
                [r.id for r in widened],
                cost,
            )
        )

    # Losses bigger than the planned 1R.
    oversized = [r for r in rows if r.r_multiple is not None and r.r_multiple < -1.2]
    if oversized:
        excess_loss = sum(r.net_pnl * (1 - 1 / abs(r.r_multiple)) for r in oversized)
        flags.append(
            Flag(
                "loss_beyond_plan",
                "Losses bigger than the planned risk",
                _severity(excess_loss, total_loss),
                f"{len(oversized)} trades lost more than 1.2R (worst {min(r.r_multiple for r in oversized):.1f}R). "
                f"Losing only 1R on them would have saved {abs(excess_loss):,.2f}.",
                [r.id for r in oversized],
                excess_loss,
            )
        )

    # Holding losers longer than winners.
    summary = summarize(rows)
    hw, hl = summary["avg_hold_win_min"], summary["avg_hold_loss_min"]
    if hw and hl and hl > 1.5 * hw:
        long_losers = [r for r in rows if r.is_loss and r.holding_seconds and r.holding_seconds / 60 > hw]
        cost = _cost(long_losers)
        flags.append(
            Flag(
                "holding_losers",
                "Holding losers longer than winners",
                _severity(cost, total_loss),
                f"Losers are held {hl:.0f} min on average vs {hw:.0f} min for winners "
                f"({hl / hw:.1f}x). Losers held longer than your average winner add up to {_money(cost)}.",
                [r.id for r in long_losers],
                cost,
                {"avg_hold_win_min": hw, "avg_hold_loss_min": hl},
            )
        )

    # Cutting winners early compared with how far price went in their favour.
    capture = settings["early_exit_capture"]
    early, left = [], 0.0
    for r in rows:
        if r.is_win and r.mfe_points and r.points and r.points > 0 and r.points / r.mfe_points < capture:
            early.append(r)
            left += (r.mfe_points - r.points) * (r.net_pnl / r.points)
    if early:
        flags.append(
            Flag(
                "early_exits",
                "Cutting winners early",
                "medium" if len(early) >= 3 else "low",
                f"{len(early)} winners kept less than {capture:.0%} of their best open profit. "
                f"About {left:,.2f} was left on the table at the peak.",
                [r.id for r in early],
                -left,
                {"left_on_table": round(left, 2)},
            )
        )

    # Size increase right after a loss.
    vols: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        vols[r.instrument].append(r.volume)
    medians = {k: statistics.median(v) for k, v in vols.items()}
    tilt = [
        cur
        for prev, cur in zip(by_open, by_open[1:])
        if prev.is_loss and cur.volume > 1.5 * medians[cur.instrument] and cur.volume > prev.volume
    ]
    if tilt:
        cost = _cost(tilt)
        flags.append(
            Flag(
                "size_up_after_loss",
                "Sizing up after a loss",
                "high" if cost < 0 else "medium",
                f"{len(tilt)} time{'s' if len(tilt) > 1 else ''} the next trade after a loss was over 1.5x your usual size, net {_money(cost)}.",
                [r.id for r in tilt],
                cost,
            )
        )

    # Sessions and weekdays that consistently lose.
    overall_wr = summary["win_rate"] or 0
    for by, label in (("session", "session"), ("weekday", "day")):
        for g in group_stats(rows, by, tz):
            if g["trades"] >= MIN_GROUP and g["net_pnl"] < 0 and (g["win_rate"] or 0) < overall_wr:
                members = [r for r in rows if _key(r, by, tz) == g["key"]]
                flags.append(
                    Flag(
                        f"weak_{by}",
                        f"Losing {label}: {g['key']}",
                        _severity(g["net_pnl"], total_loss),
                        f"{g['key']}: {g['trades']} trades, win rate {g['win_rate']:.0%} "
                        f"(overall {overall_wr:.0%}), net {_money(g['net_pnl'])}.",
                        [r.id for r in members],
                        g["net_pnl"],
                        {"key": g["key"], "stats": compact_summary(members)},
                    )
                )

    if summary["max_consecutive_losses"] >= 4:
        flags.append(
            Flag(
                "loss_streak",
                "Long losing streak",
                "low",
                f"Longest losing streak: {summary['max_consecutive_losses']} trades in a row. "
                "Consider a stop-trading rule after 3 straight losses.",
            )
        )

    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: (order[f.severity], f.cost))
    return flags


def _key(r: TradeRow, by: str, tz: ZoneInfo) -> str:
    if by == "session":
        return r.session or "unknown"
    return WEEKDAYS[r.open_time.astimezone(tz).weekday()]
