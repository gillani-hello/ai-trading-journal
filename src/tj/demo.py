"""Generate realistic demo data in the EA's file format.

The demo trader has deliberate habits so every screen has something to show:
EURUSD has an edge in London, XAUUSD leaks money in Asia and after losses
(revenge trades, widened stops), US30 is profitable but exits early,
GBPUSD is roughly breakeven and BTCUSD has too few trades to judge.
Demo data lives in its own data folder and never touches your real journal.
"""

import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from tj.models import Trade
from tj.services.journal import update_journal, upsert_day_note
from tj.services.reports import AIReportIn, InstrumentSection, save_report
from tj.services.settings import update_settings

LOGIN = 90000001
NEW_YORK = ZoneInfo("America/New_York")


@dataclass
class Spec:
    name: str
    path: str
    digits: int
    point: float
    tick_value: float
    contract: float
    price: float
    risk: float  # stop distance in price
    volume: tuple[float, float]
    commission_per_lot: float


SPECS = {
    "EURUSD": Spec("EURUSD", "Forex\\Majors\\EURUSD", 5, 0.00001, 1.0, 100000, 1.0850, 0.0018, (0.5, 1.0), 3.5),
    "GBPUSD": Spec("GBPUSD", "Forex\\Majors\\GBPUSD", 5, 0.00001, 1.0, 100000, 1.2700, 0.0022, (0.4, 0.8), 3.5),
    "XAUUSD": Spec("XAUUSD", "Metals\\XAUUSD", 2, 0.01, 1.0, 100, 2650.0, 6.0, (0.1, 0.3), 3.5),
    "US30": Spec("US30", "Indices\\US30", 1, 0.1, 0.1, 1, 42000.0, 60.0, (0.5, 1.5), 0.0),
    "BTCUSD": Spec("BTCUSD", "Crypto\\BTCUSD", 2, 0.01, 0.01, 1, 68000.0, 900.0, (0.05, 0.15), 0.0),
}

# instrument -> (weight, preferred UTC hours, win probability by session)
PROFILE = {
    "EURUSD": (30, [7, 8, 9, 10, 13, 14, 1, 2], {"Asia": 0.30, "London": 0.58, "Overlap": 0.52, "New York": 0.45}),
    "XAUUSD": (28, [1, 2, 3, 8, 13, 14, 15], {"Asia": 0.22, "London": 0.45, "Overlap": 0.50, "New York": 0.42}),
    "GBPUSD": (18, [7, 8, 9, 12, 13], {"Asia": 0.40, "London": 0.42, "Overlap": 0.44, "New York": 0.40}),
    "US30": (18, [13, 14, 15, 16, 17], {"Asia": 0.40, "London": 0.45, "Overlap": 0.58, "New York": 0.55}),
    "BTCUSD": (6, [10, 15, 20], {"Asia": 0.5, "London": 0.5, "Overlap": 0.5, "New York": 0.5}),
}


def _session(hour: int) -> str:
    return "Asia" if hour >= 21 or hour < 7 else "London" if hour < 12 else "Overlap" if hour < 16 else "New York"


def _server_ts(utc: datetime) -> int:
    """Broker wall clock (New York close: UTC+2/+3) as epoch seconds, like MT5 reports it."""
    ny = utc.astimezone(NEW_YORK)
    server = ny.replace(tzinfo=None) + timedelta(hours=7)
    return int(server.replace(tzinfo=UTC).timestamp())


class _Writer:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.ticket = 1000
        self.deals: list[dict] = []
        self.excursions: list[tuple[int, float, float]] = []
        self.positions: list[dict] = []

    def _deal(self, t: datetime, kind: str, entry: str, symbol: str, volume: float, price: float, pos: int, **kw) -> int:
        self.ticket += 1
        ts = _server_ts(t)
        self.deals.append(
            {
                "ticket": self.ticket, "order": self.ticket + 500000, "position_id": pos, "time": ts,
                "time_msc": ts * 1000 + self.rng.randint(0, 999), "type": f"DEAL_TYPE_{kind}",
                "entry": f"DEAL_ENTRY_{entry}", "symbol": symbol, "volume": round(volume, 2),
                "price": price, "sl": kw.get("sl", 0), "tp": kw.get("tp", 0),
                "commission": kw.get("commission", 0), "fee": 0, "swap": kw.get("swap", 0),
                "profit": kw.get("profit", 0), "reason": kw.get("reason", "DEAL_REASON_CLIENT"),
                "magic": 0, "comment": kw.get("comment", ""),
            }
        )  # fmt: skip
        return self.ticket

    def balance(self, t: datetime, amount: float) -> None:
        self._deal(t, "BALANCE", "IN", "", 0, 0, 0, profit=amount, comment="Deposit")

    def trade(
        self, inst: str, opened: datetime, direction: str, volume: float, r_result: float | None,
        hold: timedelta, reason: str, widened: bool = False, mfe_r: float | None = None,
    ) -> None:
        s = SPECS[inst]
        sign = 1 if direction == "long" else -1
        r = self.rng
        s.price *= 1 + r.uniform(-0.004, 0.004)
        entry = round(s.price, s.digits)
        sl = round(entry - sign * s.risk, s.digits)
        tp = round(entry + sign * 2 * s.risk, s.digits)
        comm = -round(s.commission_per_lot * volume, 2)
        kind_in, kind_out = ("BUY", "SELL") if sign == 1 else ("SELL", "BUY")
        pos = self._deal(opened, kind_in, "IN", s.name, volume, entry, 0, sl=sl, tp=tp, commission=comm)
        self.deals[-1]["position_id"] = pos

        if r_result is None:  # still open
            current = round(entry + sign * s.risk * r.uniform(-0.6, 1.2), s.digits)
            profit = round((current - entry) * sign / s.point * s.tick_value * volume, 2)
            self.positions.append(
                {"position_id": pos, "symbol": s.name, "type": f"POSITION_TYPE_{kind_in}", "volume": volume,
                 "price_open": entry, "price_current": current, "sl": sl, "tp": tp, "profit": profit,
                 "swap": 0, "time_msc": _server_ts(opened) * 1000}
            )  # fmt: skip
            return

        exit_price = round(entry + sign * s.risk * r_result, s.digits)
        final_sl = round(entry - sign * s.risk * 1.6, s.digits) if widened else sl
        closed = opened + hold
        swap = -round(r.uniform(0.5, 4) * volume * 10, 2) if hold > timedelta(hours=20) else 0.0
        profit = round((exit_price - entry) * sign / s.point * s.tick_value * volume, 2)
        self._deal(
            closed, kind_out, "OUT", s.name, volume, exit_price, pos, sl=final_sl, tp=tp,
            commission=comm, swap=swap, profit=profit, reason=f"DEAL_REASON_{reason}",
        )  # fmt: skip
        mfe = max(r_result, mfe_r if mfe_r is not None else r_result + r.uniform(0, 0.8))
        mae = max(-r_result, r.uniform(0.1, 0.9)) if r_result > 0 else max(-r_result, 1.0)
        high = entry + s.risk * (mfe if sign == 1 else mae)
        low = entry - s.risk * (mae if sign == 1 else mfe)
        self.excursions.append((pos, round(high, s.digits), round(low, s.digits)))


def generate(folder: Path, days: int = 90, seed: int = 7) -> dict[str, int]:
    rng = random.Random(seed)
    folder.mkdir(parents=True, exist_ok=True)
    w = _Writer(rng)
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    start = (now - timedelta(days=days)).replace(hour=0, minute=0)
    w.balance(start - timedelta(hours=1), 10_000)

    names = list(PROFILE)
    weights = [PROFILE[n][0] for n in names]
    trades = 0
    day = start
    while day.date() < now.date():
        day += timedelta(days=1)
        if day.weekday() >= 5:
            continue
        n_trades = rng.choice([1, 2, 2, 3, 3, 4]) if rng.random() > 0.08 else rng.randint(8, 10)
        last_close = None
        for _ in range(n_trades):
            inst = rng.choices(names, weights)[0]
            _, hours, wins = PROFILE[inst]
            hour = rng.choice(hours)
            opened = day.replace(hour=hour, minute=rng.randint(0, 59))
            if last_close and opened <= last_close:
                opened = last_close + timedelta(minutes=rng.randint(40, 180))
            if opened >= now - timedelta(hours=1):
                break
            sess = _session(opened.hour)
            vol = round(rng.uniform(*SPECS[inst].volume), 2)
            direction = rng.choice(["long", "short"])
            win = rng.random() < wins[sess]
            widened = False
            if win:
                hit_tp = rng.random() < (0.35 if inst == "US30" else 0.5)
                r_result = 2.0 if hit_tp else round(rng.uniform(0.3, 1.4), 2)
                reason = "TP" if hit_tp else "CLIENT"
                mfe_r = 2.6 if inst == "US30" and not hit_tp else None
                hold = timedelta(minutes=rng.randint(15, 240))
            else:
                widened = inst == "XAUUSD" and rng.random() < 0.3
                r_result = -1.6 if widened else round(-rng.uniform(0.9, 1.0), 2)
                reason = "SL" if rng.random() < 0.8 else "CLIENT"
                mfe_r = round(rng.uniform(0, 0.6), 2)
                hold = timedelta(minutes=rng.randint(30, 600))
            w.trade(inst, opened, direction, vol, r_result, hold, reason, widened, mfe_r)
            trades += 1
            last_close = opened + hold

            # The demo trader chases gold losses straight away, with bigger size.
            if inst == "XAUUSD" and not win and rng.random() < 0.5:
                re_open = last_close + timedelta(minutes=rng.randint(3, 20))
                if re_open < now - timedelta(hours=1):
                    rev_win = rng.random() < 0.25
                    w.trade(
                        inst, re_open, direction, round(vol * 1.8, 2), 1.0 if rev_win else -1.0,
                        timedelta(minutes=rng.randint(10, 90)), "CLIENT" if rev_win else "SL",
                    )  # fmt: skip
                    trades += 1
                    last_close = re_open + timedelta(minutes=95)

    # Two positions still open.
    w.trade("EURUSD", now - timedelta(hours=3), "long", 0.8, None, timedelta(), "CLIENT")
    w.trade("US30", now - timedelta(minutes=40), "short", 1.0, None, timedelta(), "CLIENT")

    offset = int(now.astimezone(NEW_YORK).utcoffset().total_seconds()) + 7 * 3600
    balance = round(sum(d["profit"] + d["commission"] + d["swap"] + d["fee"] for d in w.deals), 2)
    equity = round(balance + sum(p["profit"] + p["swap"] for p in w.positions), 2)
    account = {
        "ea_version": "1.0", "exported_at": int(now.timestamp()), "login": LOGIN, "name": "Demo Trader",
        "server": "DemoBroker-Server", "company": "Demo Broker Ltd", "currency": "USD", "leverage": 100,
        "trade_mode": "ACCOUNT_TRADE_MODE_DEMO", "margin_mode": "hedging", "balance": balance, "equity": equity,
        "server_utc_offset": offset,
    }  # fmt: skip
    symbols = [
        {"name": s.name, "description": s.name, "path": s.path, "digits": s.digits, "point": s.point,
         "tick_size": s.point, "tick_value": s.tick_value, "contract_size": s.contract, "base": s.name[:3],
         "profit_ccy": "USD", "calc_mode": "SYMBOL_CALC_MODE_FOREX"}
        for s in SPECS.values()
    ]  # fmt: skip
    (folder / f"account_{LOGIN}.json").write_text(json.dumps(account))
    (folder / f"symbols_{LOGIN}.json").write_text(json.dumps({"login": LOGIN, "symbols": symbols}))
    (folder / f"deals_{LOGIN}.json").write_text(json.dumps({"login": LOGIN, "deals": w.deals}))
    (folder / f"positions_{LOGIN}.json").write_text(json.dumps({"login": LOGIN, "positions": w.positions}))
    lines = ["position_id,high,low"] + [f"{p},{h},{lo}" for p, h, lo in w.excursions]
    (folder / f"excursions_{LOGIN}.csv").write_text("\r\n".join(lines) + "\r\n")
    return {"trades": trades, "deals": len(w.deals)}


def annotate(session: Session, seed: int = 7) -> None:
    """Add the kind of journal entries a real trader would write."""
    rng = random.Random(seed)
    update_settings(
        session,
        {
            "trading_rules": "1. Risk max 1% per trade.\n2. Always set a stop-loss at entry and never widen it.\n"
            "3. Max 4 trades a day.\n4. After 2 losses in a row, stop for the day.\n5. Only A+ setups during London and New York."
        },
    )
    setups = ["Breakout", "Pullback", "Reversal", "Range", "Liquidity sweep"]
    trades = list(session.scalars(select(Trade).where(Trade.status == "closed").order_by(Trade.open_time)))
    prev: Trade | None = None
    for t in trades:
        revenge = prev is not None and prev.net_pnl < 0 and t.open_time - prev.close_time < timedelta(minutes=30)
        widened = t.initial_sl is not None and t.final_sl is not None and t.final_sl != t.initial_sl
        if rng.random() < 0.75:
            emotions = ["Revenge", "Frustrated"] if revenge else rng.choice([["Calm"], ["Confident"], ["FOMO"], ["Impatient"], []])
            mistakes = (["Revenge trade"] if revenge else []) + (["Moved SL"] if widened else [])
            if t.net_pnl > 0 and t.close_reason == "manual" and rng.random() < 0.4:
                mistakes.append("Early exit")
            notes = None
            if revenge:
                notes = rng.choice(["Wanted the loss back. Should have walked away.", "Jumped straight back in, no setup."])
            elif widened:
                notes = "Moved my stop because I was sure it would turn. It didn't."
            elif rng.random() < 0.15:
                notes = rng.choice(["Clean setup, followed the plan.", "Entered a bit late after the candle closed.", "Good patience waiting for the retest."])
            update_journal(
                session, t, setup=rng.choice(setups), emotions=emotions, mistakes=mistakes, notes=notes,
                rating=2 if revenge or widened else rng.randint(3, 5), followed_plan=not (revenge or widened),
            )  # fmt: skip
        prev = t

    today = datetime.now(UTC).date()
    for i in range(1, 15):
        d = today - timedelta(days=i)
        if d.weekday() < 5:
            upsert_day_note(
                session, d,
                pre_session_plan="Watch EURUSD London open for a pullback into 1.08; no gold before London.",
                post_session_review=rng.choice(["Stuck to the plan.", "Overtraded gold again after a loss.", "Good day, patient entries."]),
                mood=rng.choice(["focused", "tired", "calm", "frustrated"]),
                rules_followed=rng.random() < 0.6,
            )  # fmt: skip

    save_report(
        session,
        AIReportIn(
            kind="weekly",
            title="Demo report (sample data)",
            summary="This is a sample report so you can see the layout. Run /weekly_review in Claude to generate a real "
            "one from your own trades.",
            period_start=today - timedelta(days=6),
            period_end=today,
            strengths=["EURUSD in London is consistently profitable.", "Stops are set on almost every trade."],
            weaknesses=["XAUUSD in the Asia session loses money.", "Re-entering gold within minutes of a loss."],
            psychology=["Losses on gold trigger immediate, bigger re-entries."],
            action_plan=["No XAUUSD trades before London open.", "After a losing trade, wait 30 minutes.", "Let US30 winners run to 2R."],
            instruments=[
                InstrumentSection(
                    symbol="XAUUSD",
                    verdict="leaking",
                    headline="Gold losses come from Asia-session entries and revenge trades.",
                    going_wrong=["Asia session win rate is low.", "Several stops were widened."],
                    improvements=["Trade gold only in London and New York."],
                    rules=["If a gold trade loses, no new gold trade for 30 minutes."],
                )
            ],
            discipline_score=6,
        ),
    )
