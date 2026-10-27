"""Shared request helpers."""

from collections.abc import Iterator
from datetime import date, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from tj.db import session_scope
from tj.services.coaching import resolve_period
from tj.services.trades import TradeFilter, get_tz


def db() -> Iterator[Session]:
    with session_scope() as session:
        yield session


DB = Annotated[Session, Depends(db)]


def trade_filter(
    session: DB,
    period: str | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    instrument: str | None = None,
    direction: str | None = None,
    status: str | None = "closed",
    outcome: str | None = None,
    setup: str | None = None,
    emotion: str | None = None,
    mistake: str | None = None,
    source: str | None = None,
    trade_session: Annotated[str | None, Query(alias="session")] = None,
    account_id: int | None = None,
    q: str | None = None,
) -> TradeFilter:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "'from' must be on or before 'to'")
    start, end = resolve_period(period, date_from, date_to, datetime.now(get_tz(session)).date())
    return TradeFilter(
        date_from=start,
        date_to=end,
        instrument=instrument or None,
        direction=direction or None,
        status=None if status in (None, "", "all") else status,
        outcome=outcome or None,
        setup=setup or None,
        emotion=emotion or None,
        mistake=mistake or None,
        source=source or None,
        session=trade_session or None,
        account_id=account_id,
        search=q or None,
    )


Filter = Annotated[TradeFilter, Depends(trade_filter)]
