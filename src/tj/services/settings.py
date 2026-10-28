"""User-editable settings stored in the `settings` table, with defaults."""

from typing import Any

import tzlocal
from sqlalchemy.orm import Session

from tj.models import Setting


def _local_timezone() -> str:
    """The machine's timezone; minimal containers have none configured, so fall back to UTC."""
    try:
        return tzlocal.get_localzone_name() or "UTC"
    except Exception:
        return "UTC"


# Sessions are classified by the trade's open hour in UTC; ranges wrap past midnight.
DEFAULT_SESSIONS = [
    {"name": "Asia", "start": 21, "end": 7},
    {"name": "London", "start": 7, "end": 12},
    {"name": "Overlap", "start": 12, "end": 16},
    {"name": "New York", "start": 16, "end": 21},
]

DEFAULTS: dict[str, Any] = {
    "display_timezone": _local_timezone(),
    "sessions": DEFAULT_SESSIONS,
    # Minutes after a losing close within which a new trade counts as a revenge trade.
    "revenge_minutes": 30,
    # Trades in one day above which the day counts as overtrading.
    "max_trades_per_day": 6,
    # Winners that kept less than this share of their max favourable excursion count as early exits.
    "early_exit_capture": 0.4,
    "trading_rules": "",
    # "auto": brokers at UTC+2/+3 follow New York-close DST; "fixed": use the current offset for all history.
    "broker_time_mode": "auto",
}


def get_setting(session: Session, key: str) -> Any:
    row = session.get(Setting, key)
    return row.value if row is not None else DEFAULTS.get(key)


def get_all_settings(session: Session) -> dict[str, Any]:
    values = dict(DEFAULTS)
    for row in session.query(Setting).all():
        values[row.key] = row.value
    return values


def update_settings(session: Session, changes: dict[str, Any]) -> dict[str, Any]:
    for key, value in changes.items():
        if key not in DEFAULTS:
            raise ValueError(f"Unknown setting: {key}")
        row = session.get(Setting, key)
        if row is None:
            session.add(Setting(key=key, value=value))
        else:
            row.value = value
    session.flush()
    return get_all_settings(session)


def session_for_hour(hour_utc: int, sessions: list[dict[str, Any]]) -> str | None:
    for s in sessions:
        start, end = s["start"], s["end"]
        inside = start <= hour_utc < end if start < end else hour_utc >= start or hour_utc < end
        if inside:
            return s["name"]
    return None
