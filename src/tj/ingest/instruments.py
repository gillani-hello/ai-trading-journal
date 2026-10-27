"""Symbol naming, asset classes and broker time conversion."""

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

CURRENCIES = {
    "USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "SEK", "NOK", "DKK", "PLN", "CZK",
    "HUF", "TRY", "ZAR", "MXN", "SGD", "HKD", "CNH", "RUB", "ILS",
}  # fmt: skip

_SUFFIX_SPLIT = re.compile(r"[.\-_+!#$]")
_LOWER_SUFFIX = re.compile(r"^([A-Z0-9]{3,})[a-z]+$")
_NEW_YORK = ZoneInfo("America/New_York")


def canonical_symbol(symbol: str) -> str:
    """Strip broker decorations: EURUSD.m, EURUSDm, XAUUSD+, #US30, US30.cash -> bare name."""
    s = symbol.strip().lstrip("#")
    s = _SUFFIX_SPLIT.split(s, maxsplit=1)[0] or s
    if m := _LOWER_SUFFIX.match(s):
        s = m.group(1)
    return s.upper()


def asset_class(symbol: str, path: str | None = None) -> str:
    p = (path or "").lower()
    for needle, cls in (
        ("crypto", "crypto"),
        ("metal", "metals"),
        ("forex", "forex"),
        ("fx", "forex"),
        ("indic", "indices"),
        ("index", "indices"),
        ("energ", "commodities"),
        ("commod", "commodities"),
        ("stock", "stocks"),
        ("share", "stocks"),
        ("equit", "stocks"),
    ):
        if needle in p:
            return cls
    s = canonical_symbol(symbol)
    if s.startswith(("XAU", "XAG", "XPT", "XPD", "GOLD", "SILVER")):
        return "metals"
    if s.startswith(("BTC", "ETH", "LTC", "XRP", "SOL", "ADA", "DOGE", "BNB")):
        return "crypto"
    if len(s) == 6 and s[:3] in CURRENCIES and s[3:] in CURRENCIES:
        return "forex"
    if any(k in s for k in ("US30", "US100", "US500", "NAS", "SPX", "DJ", "GER", "DAX", "UK100", "JP225", "HK50")):
        return "indices"
    if any(k in s for k in ("OIL", "WTI", "BRENT", "NGAS", "USOIL", "UKOIL")):
        return "commodities"
    return "other"


def server_ms_to_utc(server_ms: int, current_offset_sec: int, mode: str = "auto") -> datetime:
    """Convert an MT5 server timestamp (server wall clock as epoch) to aware UTC.

    Most retail brokers run on "New York close" time: UTC+2 in winter, UTC+3 while
    the US is on daylight saving time. When the broker's current offset is +2 or +3
    and mode is "auto", history is converted with that rule so DST periods line up;
    otherwise the current offset is applied to every timestamp.
    """
    naive = datetime(1970, 1, 1) + timedelta(milliseconds=server_ms)
    if mode == "auto" and current_offset_sec in (7200, 10800):
        return (naive - timedelta(hours=7)).replace(tzinfo=_NEW_YORK).astimezone(UTC)
    return (naive - timedelta(seconds=current_offset_sec)).replace(tzinfo=UTC)
