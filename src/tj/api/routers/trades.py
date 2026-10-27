from datetime import date
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from tj.api.deps import DB, Filter
from tj.models import Screenshot, Trade
from tj.services import journal
from tj.services.analytics import rows_from_trades, summarize
from tj.services.behavior import detect
from tj.services.journal import day_note_dict
from tj.services.settings import get_all_settings
from tj.services.trades import TradeFilter, get_tz, load_rows, log_manual_trade, query_trades, trade_to_dict

router = APIRouter(prefix="/api", tags=["trades"])

MAX_SCREENSHOT_BYTES = 15 * 1024 * 1024


class JournalPatch(BaseModel):
    setup: str | None = None
    emotions: list[str] | None = None
    mistakes: list[str] | None = None
    notes: str | None = None
    rating: int | None = Field(None, ge=1, le=5)
    followed_plan: bool | None = None


class ManualTrade(BaseModel):
    symbol: str
    direction: str
    entry_price: float
    exit_price: float | None = None
    volume: float | None = None
    open_time: str | None = None
    close_time: str | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    pnl: float | None = None
    commission: float = 0.0
    setup: str | None = None
    emotions: list[str] = []
    mistakes: list[str] = []
    notes: str | None = None


class DayNoteIn(BaseModel):
    pre_session_plan: str | None = None
    post_session_review: str | None = None
    mood: str | None = None
    rules_followed: bool | None = None


def _get(session, trade_id: int) -> Trade:
    t = session.get(Trade, trade_id)
    if t is None:
        raise HTTPException(404, f"Trade {trade_id} not found")
    return t


@router.get("/trades")
def list_trades(session: DB, f: Filter, sort: str = "-time", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    trades, total = query_trades(session, f, sort=sort, limit=min(limit, 500), offset=offset)
    tz = get_tz(session)
    return {"total": total, "items": [trade_to_dict(t, tz) for t in trades]}


@router.get("/trades/{trade_id}")
def get_trade(session: DB, trade_id: int) -> dict[str, Any]:
    return _detail(session, _get(session, trade_id))


def _detail(session, t: Trade) -> dict[str, Any]:
    tz = get_tz(session)
    d = trade_to_dict(t, tz, detail=True, session=session)
    rows = load_rows(session, TradeFilter(instrument=t.instrument))
    d["flags"] = [
        {"code": f.code, "title": f.title, "severity": f.severity}
        for f in detect(rows, get_all_settings(session), tz)
        if t.id in f.trade_ids
    ]
    return d


@router.patch("/trades/{trade_id}/journal")
def patch_journal(session: DB, trade_id: int, body: JournalPatch) -> dict[str, Any]:
    t = _get(session, trade_id)
    journal.update_journal(session, t, **body.model_dump(exclude_unset=True))
    return _detail(session, t)


@router.post("/trades")
def create_trade(session: DB, body: ManualTrade) -> dict[str, Any]:
    try:
        t, warnings = log_manual_trade(
            session, **body.model_dump(exclude={"setup", "emotions", "mistakes", "notes"})
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    journal.update_journal(session, t, setup=body.setup, emotions=body.emotions, mistakes=body.mistakes, notes=body.notes)
    return {"trade": trade_to_dict(t, get_tz(session)), "warnings": warnings}


@router.delete("/trades/{trade_id}")
def delete_trade(session: DB, trade_id: int) -> dict[str, Any]:
    t = _get(session, trade_id)
    if t.source != "manual":
        raise HTTPException(400, "MT5 trades mirror your account history and can't be deleted.")
    for shot in list(t.screenshots):
        journal.delete_screenshot(session, shot)
    session.delete(t)
    return {"deleted": trade_id}


@router.post("/trades/{trade_id}/screenshots")
async def upload_screenshot(
    session: DB, trade_id: int, file: UploadFile = File(...), caption: str | None = Form(None)
) -> dict[str, Any]:
    t = _get(session, trade_id)
    content = await file.read()
    if len(content) > MAX_SCREENSHOT_BYTES:
        raise HTTPException(413, "Screenshot is larger than 15 MB")
    try:
        shot = journal.add_screenshot(session, t, content, file.content_type or "", caption)
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from exc
    return {"id": shot.id, "url": f"/screenshots/{shot.filename}", "caption": shot.caption}


@router.delete("/screenshots/{shot_id}")
def delete_screenshot(session: DB, shot_id: int) -> dict[str, Any]:
    shot = session.get(Screenshot, shot_id)
    if shot is None:
        raise HTTPException(404, "Screenshot not found")
    journal.delete_screenshot(session, shot)
    return {"deleted": shot_id}


@router.get("/day/{day}")
def day_detail(session: DB, day: date) -> dict[str, Any]:
    trades, _ = query_trades(session, TradeFilter(date_from=day, date_to=day, status=None), sort="time")
    tz = get_tz(session)
    return {
        "date": day.isoformat(),
        "summary": summarize(rows_from_trades(trades)),
        "trades": [trade_to_dict(t, tz) for t in trades],
        "note": day_note_dict(journal.get_day_note(session, day), day),
    }


@router.put("/day-notes/{day}")
def put_day_note(session: DB, day: date, body: DayNoteIn) -> dict[str, Any]:
    note = journal.upsert_day_note(session, day, **body.model_dump(exclude_unset=True))
    return day_note_dict(note, day)


@router.get("/tags")
def get_tags(session: DB) -> dict[str, list[str]]:
    return journal.list_tags(session)


@router.put("/tags/{category}")
def put_tags(session: DB, category: str, names: list[str]) -> list[str]:
    try:
        return journal.replace_tags(session, category, names)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
