"""Turn the MT5 deals of one position into journal trades.

A position normally becomes one trade: entries and partial exits are averaged
(volume-weighted). On netting accounts a reversal deal (`inout`) closes the
current trade and opens an opposite one, so a position can produce several
trades ("legs").
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from tj.models import Deal

EPS = 1e-9
# A stop only seen at close is often one trailed towards entry; beyond this it can't be the original risk.
MAX_CLOSE_STOP_R = 5.0

CLOSE_REASONS = {
    "sl": "sl",
    "tp": "tp",
    "so": "stop_out",
    "client": "manual",
    "mobile": "manual",
    "web": "manual",
    "expert": "expert",
}


@dataclass
class OpenPositionInfo:
    sl: float | None
    tp: float | None
    floating_pnl: float


@dataclass
class FirstStop:
    sl: float
    time: datetime


@dataclass
class SymbolSpec:
    point: float | None = None
    tick_size: float | None = None
    tick_value: float | None = None


@dataclass
class _Leg:
    direction: str
    entries: list[tuple[float, float, datetime]] = field(default_factory=list)  # volume, price, time
    exits: list[tuple[float, float, datetime]] = field(default_factory=list)
    initial_sl: float | None = None
    initial_tp: float | None = None
    final_sl: float | None = None
    final_tp: float | None = None
    close_reason: str | None = None
    commission: float = 0.0
    swap: float = 0.0
    gross: float = 0.0

    @property
    def entry_volume(self) -> float:
        return sum(v for v, _, _ in self.entries)

    @property
    def exit_volume(self) -> float:
        return sum(v for v, _, _ in self.exits)

    @property
    def open_volume(self) -> float:
        return self.entry_volume - self.exit_volume

    @property
    def closed(self) -> bool:
        return self.entries != [] and self.open_volume <= EPS


def _nz(value: float | None) -> float | None:
    return value if value else None


def _vwap(fills: list[tuple[float, float, datetime]]) -> float | None:
    volume = sum(v for v, _, _ in fills)
    if volume <= EPS:
        return None
    return sum(v * p for v, p, _ in fills) / volume


def _direction(deal_type: str) -> str:
    return "long" if deal_type == "buy" else "short"


def build_legs(deals: list[Deal]) -> list[_Leg]:
    legs: list[_Leg] = []
    current: _Leg | None = None
    for d in sorted(deals, key=lambda d: (d.time_msc, d.ticket)):
        if d.type not in ("buy", "sell"):
            continue
        costs = (d.commission or 0.0) + (d.fee or 0.0)
        if d.entry == "in":
            if current is None or current.closed:
                current = _Leg(direction=_direction(d.type), initial_sl=_nz(d.sl), initial_tp=_nz(d.tp))
                legs.append(current)
            current.entries.append((d.volume, d.price, d.time))
            current.commission += costs
        elif d.entry in ("out", "out_by"):
            if current is None:
                continue  # history starts mid-position; nothing to attach the exit to
            current.exits.append((d.volume, d.price, d.time))
            current.commission += costs
            current.swap += d.swap or 0.0
            current.gross += d.profit or 0.0
            current.final_sl, current.final_tp = _nz(d.sl), _nz(d.tp)
            current.close_reason = CLOSE_REASONS.get(d.reason or "", d.reason)
        elif d.entry == "inout":
            closing = current.open_volume if current is not None and not current.closed else 0.0
            share = min(closing / d.volume, 1.0) if d.volume > EPS else 0.0
            if current is not None and closing > EPS:
                current.exits.append((closing, d.price, d.time))
                current.commission += costs * share
                current.swap += d.swap or 0.0
                current.gross += d.profit or 0.0
                current.final_sl, current.final_tp = _nz(d.sl), _nz(d.tp)
                current.close_reason = "reversal"
            remaining = d.volume - closing
            if remaining > EPS:
                current = _Leg(direction=_direction(d.type), initial_sl=_nz(d.sl), initial_tp=_nz(d.tp))
                current.entries.append((remaining, d.price, d.time))
                current.commission += costs * (1 - share)
                legs.append(current)
    return [leg for leg in legs if leg.entries]


def _protective(sl: float | None, entry: float, sign: int) -> bool:
    """A stop on the losing side of entry (one moved to breakeven or beyond no longer defines risk)."""
    return sl is not None and (entry - sl) * sign > EPS


def risk_stop(
    initial_sl: float | None,
    first_stop: FirstStop | None,
    final_sl: float | None,
    entry: float,
    sign: int,
    open_time: datetime,
    *,
    exit_price: float | None = None,
    close_reason: str | None = None,
    adverse: float | None = None,
    favourable: float | None = None,
) -> tuple[float | None, str | None, int | None]:
    """The stop that defines 1R, where it came from, and how long after entry it was set.

    Order stops and stops the EA saw being added are trusted. A stop seen only at
    close is used for closed trades when it plausibly sat there all along: the trade
    hit it, or price never went beyond it (adverse excursion smaller than the stop
    distance), and neither the exit nor the best price implies an outsized R
    (a stop hit after price ran far in favour was trailed, not the original risk).
    """
    if initial_sl:
        return initial_sl, "entry", 0
    if first_stop is not None and _protective(first_stop.sl, entry, sign):
        return first_stop.sl, "added", max(int((first_stop.time - open_time).total_seconds()), 0)
    if exit_price is not None and final_sl is not None and _protective(final_sl, entry, sign):
        distance = abs(entry - final_sl)
        held = close_reason == "sl" or (adverse is not None and adverse < distance)
        peak = max(abs(exit_price - entry), favourable or 0.0)
        if held and peak / distance <= MAX_CLOSE_STOP_R:
            return final_sl, "close", None
    return None, None, None


def leg_to_trade_fields(
    leg: _Leg,
    spec: SymbolSpec | None,
    excursion: tuple[float, float] | None,
    open_info: OpenPositionInfo | None,
    first_stop: FirstStop | None = None,
) -> dict[str, Any]:
    """Compute every MT5-derived column of a trade (sessions are added by the caller)."""
    entry = _vwap(leg.entries)
    assert entry is not None
    exit_ = _vwap(leg.exits)
    sign = 1 if leg.direction == "long" else -1
    open_time = leg.entries[0][2]
    closed = leg.closed
    close_time = leg.exits[-1][2] if closed else None
    point = spec.point if spec and spec.point else None

    final_sl, final_tp = leg.final_sl, leg.final_tp
    floating = None
    if not closed and open_info is not None:
        final_sl, final_tp, floating = open_info.sl, open_info.tp, open_info.floating_pnl

    adverse = favourable = None
    if excursion is not None:
        high, low = excursion
        adverse = max(entry - low if sign == 1 else high - entry, 0.0)
        favourable = max(high - entry if sign == 1 else entry - low, 0.0)
    risk_sl, sl_source, sl_delay = risk_stop(
        leg.initial_sl,
        first_stop,
        final_sl,
        entry,
        sign,
        open_time,
        exit_price=exit_ if closed else None,
        close_reason=leg.close_reason,
        adverse=adverse,
        favourable=favourable,
    )

    r_multiple = points = mfe = mae = None
    if closed and exit_ is not None:
        move = (exit_ - entry) * sign
        if point:
            points = move / point
        if risk_sl is not None and abs(entry - risk_sl) > EPS:
            r_multiple = move / abs(entry - risk_sl)
    if closed and excursion is not None and point:
        high, low = excursion
        favourable, adverse = (high - entry, entry - low) if sign == 1 else (entry - low, high - entry)
        mfe, mae = max(favourable, 0.0) / point, max(adverse, 0.0) / point

    return {
        "direction": leg.direction,
        "status": "closed" if closed else "open",
        "volume": leg.entry_volume,
        "open_time": open_time,
        "close_time": close_time,
        "entry_price": entry,
        "exit_price": exit_,
        "initial_sl": leg.initial_sl,
        "initial_tp": leg.initial_tp,
        "final_sl": final_sl,
        "final_tp": final_tp,
        "risk_sl": risk_sl,
        "sl_source": sl_source,
        "sl_delay_seconds": sl_delay,
        "close_reason": leg.close_reason if closed else None,
        "commission": round(leg.commission, 2),
        "swap": round(leg.swap, 2),
        "gross_pnl": round(leg.gross, 2),
        "net_pnl": round(leg.gross + leg.commission + leg.swap, 2),
        "floating_pnl": floating,
        "r_multiple": r_multiple,
        "points": points,
        "mfe_points": mfe,
        "mae_points": mae,
        "holding_seconds": int((close_time - open_time).total_seconds()) if close_time else None,
    }
