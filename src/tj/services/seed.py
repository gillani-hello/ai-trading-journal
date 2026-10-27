"""Default rows created on first start."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from tj.models import Account, Tag

DEFAULT_TAGS = {
    "setup": [
        "Breakout",
        "Pullback",
        "Reversal",
        "Range",
        "Trend continuation",
        "Support/Resistance",
        "Liquidity sweep",
        "News",
    ],
    "emotion": [
        "Calm",
        "Confident",
        "FOMO",
        "Fear",
        "Greed",
        "Revenge",
        "Impatient",
        "Bored",
        "Frustrated",
        "Overconfident",
    ],
    "mistake": [
        "No SL",
        "Moved SL",
        "Early exit",
        "Late entry",
        "Chased entry",
        "Oversized",
        "Overtrading",
        "Ignored plan",
        "Revenge trade",
        "Held loser too long",
        "Traded news",
    ],
}

MANUAL_ACCOUNT_NAME = "Manual journal"


def seed_defaults(session: Session) -> None:
    if session.scalar(select(Tag.id).limit(1)) is None:
        for category, names in DEFAULT_TAGS.items():
            session.add_all(Tag(category=category, name=n) for n in names)


def get_manual_account(session: Session) -> Account:
    """The account dictated trades go to, created on first use."""
    account = session.scalar(select(Account).where(Account.source == "manual"))
    if account is None:
        mt5 = session.scalar(select(Account).where(Account.source == "mt5").order_by(Account.id))
        account = Account(source="manual", name=MANUAL_ACCOUNT_NAME, currency=mt5.currency if mt5 else "USD")
        session.add(account)
        session.flush()
    return account
