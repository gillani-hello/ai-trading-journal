"""Everything the trader adds: trade annotations, screenshots, day notes, tags."""

import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tj.config import get_settings
from tj.models import DayNote, Screenshot, Tag, Trade, TradeJournal

TAG_CATEGORIES = ("setup", "emotion", "mistake")
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
_UNSET: Any = object()


def _clean_tags(values: list[str] | None) -> list[str]:
    seen: dict[str, None] = {}
    for v in values or []:
        v = v.strip()
        if v:
            seen.setdefault(v, None)
    return list(seen)


def _remember_tags(session: Session, category: str, names: list[str]) -> None:
    known = {t.name.lower() for t in session.scalars(select(Tag).where(Tag.category == category))}
    for name in names:
        if name.lower() not in known:
            session.add(Tag(category=category, name=name))
            known.add(name.lower())


def update_journal(
    session: Session,
    trade: Trade,
    *,
    setup: str | None = _UNSET,
    emotions: list[str] | None = _UNSET,
    mistakes: list[str] | None = _UNSET,
    notes: str | None = _UNSET,
    rating: int | None = _UNSET,
    followed_plan: bool | None = _UNSET,
    append_notes: bool = False,
) -> TradeJournal:
    """Change only the fields passed; leave the rest as they are."""
    j = trade.journal
    if j is None:
        j = TradeJournal(trade_id=trade.id, emotions=[], mistakes=[])
        session.add(j)
        trade.journal = j
    if setup is not _UNSET:
        j.setup = (setup or "").strip() or None
        if j.setup:
            _remember_tags(session, "setup", [j.setup])
    if emotions is not _UNSET:
        j.emotions = _clean_tags(emotions)
        _remember_tags(session, "emotion", j.emotions)
    if mistakes is not _UNSET:
        j.mistakes = _clean_tags(mistakes)
        _remember_tags(session, "mistake", j.mistakes)
    if notes is not _UNSET:
        if append_notes and j.notes and notes:
            j.notes = f"{j.notes}\n\n{notes}"
        else:
            j.notes = notes or None
    if rating is not _UNSET:
        if rating is not None and not 1 <= rating <= 5:
            raise ValueError("rating must be between 1 and 5")
        j.rating = rating
    if followed_plan is not _UNSET:
        j.followed_plan = followed_plan
    session.flush()
    return j


def set_ai_feedback(session: Session, trade: Trade, feedback: str) -> None:
    j = update_journal(session, trade)
    j.ai_feedback = feedback
    j.ai_feedback_at = datetime.now(UTC)
    session.flush()


def list_tags(session: Session) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {c: [] for c in TAG_CATEGORIES}
    for t in session.scalars(select(Tag).order_by(Tag.category, Tag.id)):
        out.setdefault(t.category, []).append(t.name)
    return out


def replace_tags(session: Session, category: str, names: list[str]) -> list[str]:
    if category not in TAG_CATEGORIES:
        raise ValueError(f"category must be one of {TAG_CATEGORIES}")
    names = _clean_tags(names)
    for t in session.scalars(select(Tag).where(Tag.category == category)):
        session.delete(t)
    session.flush()
    session.add_all(Tag(category=category, name=n) for n in names)
    session.flush()
    return names


# Screenshots ---------------------------------------------------------------


def add_screenshot(session: Session, trade: Trade, content: bytes, content_type: str, caption: str | None) -> Screenshot:
    ext = IMAGE_TYPES.get(content_type)
    if ext is None:
        raise ValueError(f"Unsupported image type {content_type}; use PNG, JPEG, WebP or GIF.")
    filename = f"{trade.id}/{uuid.uuid4().hex}{ext}"
    path = get_settings().screenshots_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    shot = Screenshot(trade_id=trade.id, filename=filename, caption=caption)
    session.add(shot)
    session.flush()
    return shot


def delete_screenshot(session: Session, shot: Screenshot) -> None:
    path: Path = get_settings().screenshots_dir / shot.filename
    path.unlink(missing_ok=True)
    session.delete(shot)
    session.flush()


# Day notes -----------------------------------------------------------------


def day_note_dict(n: DayNote | None, d: date) -> dict[str, Any]:
    return {
        "date": d.isoformat(),
        "pre_session_plan": n.pre_session_plan if n else None,
        "post_session_review": n.post_session_review if n else None,
        "mood": n.mood if n else None,
        "rules_followed": n.rules_followed if n else None,
    }


def get_day_note(session: Session, d: date) -> DayNote | None:
    return session.scalar(select(DayNote).where(DayNote.date == d))


def upsert_day_note(
    session: Session,
    d: date,
    *,
    pre_session_plan: str | None = _UNSET,
    post_session_review: str | None = _UNSET,
    mood: str | None = _UNSET,
    rules_followed: bool | None = _UNSET,
    append: bool = False,
) -> DayNote:
    note = get_day_note(session, d)
    if note is None:
        note = DayNote(date=d)
        session.add(note)
    for field, value in (("pre_session_plan", pre_session_plan), ("post_session_review", post_session_review)):
        if value is _UNSET:
            continue
        current = getattr(note, field)
        setattr(note, field, f"{current}\n\n{value}" if append and current and value else (value or None))
    if mood is not _UNSET:
        note.mood = mood or None
    if rules_followed is not _UNSET:
        note.rules_followed = rules_followed
    session.flush()
    return note


def day_notes_between(session: Session, start: date, end: date) -> dict[str, DayNote]:
    rows = session.scalars(select(DayNote).where(DayNote.date >= start, DayNote.date <= end))
    return {n.date.isoformat(): n for n in rows}
