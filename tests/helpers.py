"""Write files in the exact format TradeJournalSync.mq5 produces."""

import json
from datetime import UTC, datetime
from pathlib import Path

LOGIN = 5012345


def server_seconds(year, month, day, hour=0, minute=0, offset_hours=3) -> int:
    """Epoch seconds as MT5 reports them: the broker's wall clock read as UTC."""
    utc = datetime(year, month, day, hour, minute, tzinfo=UTC)
    return int(utc.timestamp()) + offset_hours * 3600


def deal(ticket, position, t, kind, entry, volume, price, *, symbol="EURUSD", profit=0.0,
         commission=0.0, swap=0.0, fee=0.0, sl=0.0, tp=0.0, reason="DEAL_REASON_CLIENT"):
    return {
        "ticket": ticket, "order": ticket + 1000, "position_id": position, "time": t,
        "time_msc": t * 1000, "type": f"DEAL_TYPE_{kind.upper()}", "entry": f"DEAL_ENTRY_{entry.upper()}",
        "symbol": symbol, "volume": volume, "price": price, "sl": sl, "tp": tp,
        "commission": commission, "fee": fee, "swap": swap, "profit": profit,
        "reason": reason, "magic": 0, "comment": "",
    }


def balance(ticket, t, amount):
    d = deal(ticket, 0, t, "balance", "in", 0, 0, symbol="", profit=amount)
    d["comment"] = "Deposit"
    return d


EURUSD = {"name": "EURUSD", "description": "Euro vs US Dollar", "path": "Forex\\Majors\\EURUSD",
          "digits": 5, "point": 0.00001, "tick_size": 0.00001, "tick_value": 1, "contract_size": 100000,
          "base": "EUR", "profit_ccy": "USD", "calc_mode": "SYMBOL_CALC_MODE_FOREX"}
XAUUSD = {"name": "XAUUSD.m", "description": "Gold", "path": "Metals\\XAUUSD.m", "digits": 2,
          "point": 0.01, "tick_size": 0.01, "tick_value": 1, "contract_size": 100, "base": "XAU",
          "profit_ccy": "USD", "calc_mode": "SYMBOL_CALC_MODE_CFD"}


def write_export(folder: Path, deals, *, symbols=(EURUSD, XAUUSD), positions=(), excursions=(),
                 offset=10800, login=LOGIN, margin_mode="hedging"):
    now = int(datetime.now(UTC).timestamp())
    account = {"ea_version": "1.0", "exported_at": now, "login": login, "name": "Test Trader",
               "server": "Broker-Demo", "company": "Test Broker", "currency": "USD", "leverage": 100,
               "trade_mode": "ACCOUNT_TRADE_MODE_DEMO", "margin_mode": margin_mode, "balance": 10000,
               "equity": 10000, "server_utc_offset": offset}
    (folder / f"account_{login}.json").write_text(json.dumps(account))
    (folder / f"symbols_{login}.json").write_text(json.dumps({"login": login, "symbols": list(symbols)}))
    (folder / f"deals_{login}.json").write_text(json.dumps({"login": login, "deals": list(deals)}))
    (folder / f"positions_{login}.json").write_text(json.dumps({"login": login, "positions": list(positions)}))
    lines = ["position_id,high,low"] + [f"{p},{h},{lo}" for p, h, lo in excursions]
    (folder / f"excursions_{login}.csv").write_text("\r\n".join(lines) + "\r\n")
