"""Plain-English, rule-based insights per instrument and overall.

These are computed instantly from the numbers; the AI coach builds on them.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any
from zoneinfo import ZoneInfo

from tj.services.analytics import TradeRow, group_stats, instrument_verdict, summarize

MIN_SLICE = 3  # trades a slice needs before it is worth commenting on


@dataclass
class Insight:
    scope: str  # instrument symbol, or "overall"
    kind: str  # positive | negative | neutral
    text: str
    impact: float  # money the observation is about, for ranking

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["impact"] = round(self.impact, 2)
        return d


def _m(x: float) -> str:
    return f"{'−' if x < 0 else '+'}{abs(x):,.0f}"


def _pct(x: float | None) -> str:
    return f"{x:.0%}" if x is not None else "n/a"


def _slices(rows: list[TradeRow], by: str, tz: ZoneInfo) -> list[dict[str, Any]]:
    return [g for g in group_stats(rows, by, tz) if g["trades"] >= MIN_SLICE and g["key"] not in ("unknown", "(untagged)", "(none)")]


def _best_worst(scope: str, rows: list[TradeRow], by: str, label: str, tz: ZoneInfo) -> list[Insight]:
    groups = _slices(rows, by, tz)
    if len(groups) < 2:
        return []
    best, worst = max(groups, key=lambda g: g["net_pnl"]), min(groups, key=lambda g: g["net_pnl"])
    out = []
    if worst["net_pnl"] < 0 and best["net_pnl"] > 0:
        out.append(
            Insight(
                scope,
                "negative",
                f"{label.capitalize()}: {worst['key']} is {_m(worst['net_pnl'])} ({_pct(worst['win_rate'])} win rate, "
                f"{worst['trades']} trades) while {best['key']} is {_m(best['net_pnl'])} ({_pct(best['win_rate'])}).",
                abs(worst["net_pnl"]),
            )
        )
    elif worst["net_pnl"] < 0:
        total = sum(g["net_pnl"] for g in groups)
        share = worst["net_pnl"] / total if total < 0 else 1.0
        if share >= 0.4:
            out.append(
                Insight(
                    scope,
                    "negative",
                    f"{label.capitalize()}: {worst['key']} accounts for {_m(worst['net_pnl'])} ({share:.0%} of the losses; "
                    f"{_pct(worst['win_rate'])} win rate, {worst['trades']} trades). Least bad: {best['key']} at {_m(best['net_pnl'])}.",
                    abs(worst["net_pnl"]),
                )
            )
    elif best["net_pnl"] > 0:
        out.append(
            Insight(
                scope,
                "positive",
                f"Best {label}: {best['key']} at {_m(best['net_pnl'])} ({_pct(best['win_rate'])} win rate, {best['trades']} trades).",
                best["net_pnl"],
            )
        )
    return out


def insights_for(scope: str, rows: list[TradeRow], tz: ZoneInfo) -> list[Insight]:
    if len(rows) < MIN_SLICE:
        return []
    s = summarize(rows)
    out: list[Insight] = []

    verdict = instrument_verdict(s)
    pf = f", profit factor {s['profit_factor']:.2f}" if s["profit_factor"] else ""
    exp = f", expectancy {_m(s['expectancy'])}/trade" if s["expectancy"] is not None else ""
    out.append(
        Insight(
            scope,
            {"edge": "positive", "leaking": "negative"}.get(verdict, "neutral"),
            f"{s['trades']} trades, {_pct(s['win_rate'])} win rate, net {_m(s['net_pnl'])}{pf}{exp}.",
            abs(s["net_pnl"]),
        )
    )

    out += _best_worst(scope, rows, "session", "session", tz)
    out += _best_worst(scope, rows, "direction", "direction", tz)
    out += _best_worst(scope, rows, "weekday", "weekday", tz)
    out += _best_worst(scope, rows, "setup", "setup", tz)

    # Payoff: are winners big enough to pay for losers?
    if s["avg_win"] and s["avg_loss"] and s["win_rate"]:
        payoff = s["payoff_ratio"]
        breakeven_wr = 1 / (1 + payoff) if payoff else None
        if payoff is not None and payoff < 1 and breakeven_wr and s["win_rate"] < breakeven_wr + 0.05:
            out.append(
                Insight(
                    scope,
                    "negative",
                    f"Average win {_m(s['avg_win'])} vs average loss {_m(s['avg_loss'])} (payoff {payoff:.2f}). "
                    f"At this payoff you need a {_pct(breakeven_wr)} win rate just to break even.",
                    abs(s["gross_loss"]) * 0.2,
                )
            )
        elif payoff is not None and payoff >= 1.5:
            out.append(
                Insight(scope, "positive", f"Winners are {payoff:.1f}x the size of losers on average.", s["gross_profit"] * 0.1)
            )

    # Exits: manual closes vs letting TP/SL work.
    reasons = {g["key"]: g for g in group_stats(rows, "close_reason", tz)}
    manual, tp = reasons.get("manual"), reasons.get("tp")
    manual_wins = [r for r in rows if r.close_reason == "manual" and r.is_win and r.r_multiple is not None]
    tp_wins = [r for r in rows if r.close_reason == "tp" and r.r_multiple is not None]
    if manual and tp and manual_wins and tp_wins and len(manual_wins) >= MIN_SLICE:
        avg_manual = sum(r.r_multiple for r in manual_wins) / len(manual_wins)  # type: ignore[misc]
        avg_tp = sum(r.r_multiple for r in tp_wins) / len(tp_wins)  # type: ignore[misc]
        if avg_tp > avg_manual * 1.3:
            out.append(
                Insight(
                    scope,
                    "negative",
                    f"Winners you close by hand average {avg_manual:.2f}R; winners that reach TP average {avg_tp:.2f}R. "
                    f"{len(manual_wins)} manual exits may be leaving R on the table.",
                    sum(r.net_pnl for r in manual_wins) * 0.3,
                )
            )
    sl = reasons.get("sl")
    if sl and sl["trades"] / s["trades"] >= 0.5:
        out.append(
            Insight(
                scope,
                "neutral",
                f"{sl['trades'] / s['trades']:.0%} of trades end at the stop-loss. Check whether stops sit at obvious levels "
                "or entries are early.",
                abs(sl["net_pnl"]) * 0.2,
            )
        )

    # How much of the favourable move winners keep.
    captured = [r.points / r.mfe_points for r in rows if r.is_win and r.points and r.mfe_points and r.mfe_points > 0]
    if len(captured) >= MIN_SLICE:
        avg_cap = sum(captured) / len(captured)
        out.append(
            Insight(
                scope,
                "negative" if avg_cap < 0.5 else "positive",
                f"Winners keep {avg_cap:.0%} of their best open profit on average.",
                s["gross_profit"] * (1 - avg_cap) * 0.3,
            )
        )

    # Holding time.
    hw, hl = s["avg_hold_win_min"], s["avg_hold_loss_min"]
    if hw and hl and hl > 1.5 * hw:
        out.append(
            Insight(
                scope,
                "negative",
                f"Losers are held {hl:.0f} min vs {hw:.0f} min for winners — cutting losers sooner would help.",
                abs(s["gross_loss"]) * 0.2,
            )
        )

    # Emotions and mistakes tagged in the journal (tags that always co-occur are reported once).
    seen_sets: set[frozenset[int]] = set()
    for by in ("mistake", "emotion"):
        for g in _slices(rows, by, tz):
            members = frozenset(r.id for r in rows if g["key"] in (r.mistakes if by == "mistake" else r.emotions))
            if g["net_pnl"] < 0 and members not in seen_sets:
                seen_sets.add(members)
                out.append(
                    Insight(
                        scope,
                        "negative",
                        f"Trades tagged '{g['key']}' ({by}): {g['trades']} trades, net {_m(g['net_pnl'])}, "
                        f"{_pct(g['win_rate'])} win rate.",
                        abs(g["net_pnl"]),
                    )
                )

    out[1:] = sorted(out[1:], key=lambda i: i.impact, reverse=True)
    return out


def instrument_insights(rows: list[TradeRow], tz: ZoneInfo) -> dict[str, list[Insight]]:
    by_inst: dict[str, list[TradeRow]] = defaultdict(list)
    for r in rows:
        by_inst[r.instrument].append(r)
    return {inst: insights_for(inst, rs, tz) for inst, rs in by_inst.items()}


def overall_insights(rows: list[TradeRow], tz: ZoneInfo, limit: int = 8) -> list[Insight]:
    out = insights_for("overall", rows, tz)
    groups = group_stats(rows, "instrument", tz)
    if len(groups) >= 2:
        best, worst = groups[0], groups[-1]
        if worst["net_pnl"] < 0:
            out.append(
                Insight(
                    "overall",
                    "negative",
                    f"{worst['key']} is your biggest leak at {_m(worst['net_pnl'])} over {worst['trades']} trades; "
                    f"{best['key']} is your best at {_m(best['net_pnl'])}.",
                    abs(worst["net_pnl"]),
                )
            )
    head, rest = out[:1], sorted(out[1:], key=lambda i: i.impact, reverse=True)
    return (head + rest)[:limit]
