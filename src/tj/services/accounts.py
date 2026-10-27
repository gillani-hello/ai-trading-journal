"""Account money: balance, equity, deposits, return, and balance over time.

Balance history is rebuilt from MT5 deals exactly the way MT5 computes it: every
deal's profit + commission + fee + swap, including deposits and withdrawals.
"""

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tj.models import Account, CashFlow, Deal, Trade

DEPOSIT_TYPES = ("balance",)


def _mt5_accounts(session: Session) -> list[Account]:
    return list(session.scalars(select(Account).where(Account.source == "mt5").order_by(Account.id)))


def _primary_currency(accounts: list[Account]) -> str | None:
    if not accounts:
        return None
    return Counter(a.currency for a in accounts).most_common(1)[0][0]


def account_overview(session: Session) -> dict[str, Any]:
    """Per MT5 account and in total (accounts in the main currency only)."""
    items = []
    for a in _mt5_accounts(session):
        flows = list(session.scalars(select(CashFlow).where(CashFlow.account_id == a.id)))
        deposits = sum(f.amount for f in flows if f.type in DEPOSIT_TYPES and f.amount > 0)
        withdrawals = -sum(f.amount for f in flows if f.type in DEPOSIT_TYPES and f.amount < 0)
        other = sum(f.amount for f in flows if f.type not in DEPOSIT_TYPES)  # credit, charges, interest…
        realised = session.scalar(select(func.coalesce(func.sum(Trade.net_pnl), 0.0)).where(Trade.account_id == a.id)) or 0.0
        floating = (
            session.scalar(
                select(func.coalesce(func.sum(Trade.floating_pnl), 0.0)).where(
                    Trade.account_id == a.id, Trade.status == "open"
                )
            )
            or 0.0
        )
        computed = deposits - withdrawals + other + realised
        balance = a.balance if a.balance is not None else computed
        equity = a.equity if a.equity is not None else balance + floating
        net_deposits = deposits - withdrawals
        trading = balance - net_deposits
        items.append(
            {
                "id": a.id,
                "name": a.name,
                "broker": a.broker,
                "login": a.login,
                "currency": a.currency,
                "trade_mode": a.trade_mode,
                "balance": round(balance, 2),
                "equity": round(equity, 2),
                "floating": round(equity - balance, 2),
                "deposits": round(deposits, 2),
                "withdrawals": round(withdrawals, 2),
                "net_deposits": round(net_deposits, 2),
                "trading_pnl": round(trading, 2),
                "return_pct": round(trading / net_deposits, 4) if net_deposits > 0 else None,
                # True when the journal's own maths lands on MT5's reported balance.
                "reconciled": a.balance is not None and abs(computed - a.balance) < 0.01,
                "as_of": a.ea_seen_at.isoformat() if a.ea_seen_at else None,
            }
        )

    currency = _primary_currency(_mt5_accounts(session))
    main = [i for i in items if i["currency"] == currency]
    total = None
    if main:
        keys = ("balance", "equity", "floating", "deposits", "withdrawals", "net_deposits", "trading_pnl")
        total = {k: round(sum(i[k] for i in main), 2) for k in keys}
        total["currency"] = currency
        total["return_pct"] = round(total["trading_pnl"] / total["net_deposits"], 4) if total["net_deposits"] > 0 else None
        total["accounts"] = len(main)
        total["reconciled"] = all(i["reconciled"] for i in main)
        total["as_of"] = max((i["as_of"] for i in main if i["as_of"]), default=None)
    return {"accounts": items, "total": total}


def balance_curve(session: Session, start: datetime | None, end: datetime | None) -> list[dict[str, Any]]:
    """Account balance after each deal in [start, end), starting from the balance at `start`."""
    accounts = _mt5_accounts(session)
    currency = _primary_currency(accounts)
    ids = [a.id for a in accounts if a.currency == currency]
    if not ids:
        return []
    amount = Deal.profit + Deal.commission + Deal.fee + Deal.swap
    opening = 0.0
    if start is not None:
        opening = (
            session.scalar(select(func.coalesce(func.sum(amount), 0.0)).where(Deal.account_id.in_(ids), Deal.time < start))
            or 0.0
        )
    stmt = select(Deal.time, amount, Deal.type).where(Deal.account_id.in_(ids)).order_by(Deal.time, Deal.ticket)
    if start is not None:
        stmt = stmt.where(Deal.time >= start)
    if end is not None:
        stmt = stmt.where(Deal.time < end)
    points: list[dict[str, Any]] = []
    balance = opening
    # An account funded inside the range starts at its first deposit, not at zero.
    if start is not None and abs(opening) > 0.005:
        points.append({"time": start.isoformat(), "balance": round(opening, 2), "change": 0.0, "kind": "open"})
    for time, value, kind in session.execute(stmt):
        if not value:
            continue
        balance += value
        points.append(
            {
                "time": time.isoformat(),
                "balance": round(balance, 2),
                "change": round(value, 2),
                "kind": "cash" if kind not in ("buy", "sell") else "trade",
            }
        )
    return points
