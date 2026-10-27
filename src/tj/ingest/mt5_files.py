"""Read the files written by TradeJournalSync.mq5 and update the database.

Every sync is idempotent: deals are keyed by ticket, trades by
(account, position, leg), and only positions touched by new data are rebuilt.
"""

import csv
import json
import sys
import logging
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tj.config import discover_mt5_dir, get_settings
from tj.ingest.instruments import asset_class, canonical_symbol, server_ms_to_utc
from tj.ingest.position_builder import FirstStop, OpenPositionInfo, SymbolSpec, build_legs, leg_to_trade_fields
from tj.models import Account, CashFlow, Deal, PositionExcursion, PositionStop, Symbol, Trade
from tj.services.settings import get_setting, session_for_hour

log = logging.getLogger(__name__)

TRADE_TYPES = ("buy", "sell")

# (db url, file path) -> (mtime_ns, size) of the version already ingested by this process.
_seen_files: dict[tuple[str, Path], tuple[int, int]] = {}


@dataclass
class AccountSync:
    login: str
    name: str
    new_deals: int = 0
    trades_rebuilt: int = 0
    ea_seen_at: datetime | None = None


@dataclass
class SyncResult:
    status: str  # ok | no_folder | error
    folder: str | None
    accounts: list[AccountSync] = field(default_factory=list)
    message: str | None = None
    finished_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "folder": self.folder,
            "message": self.message,
            "finished_at": self.finished_at.isoformat(),
            "accounts": [
                {
                    "login": a.login,
                    "name": a.name,
                    "new_deals": a.new_deals,
                    "trades_rebuilt": a.trades_rebuilt,
                    "ea_seen_at": a.ea_seen_at.isoformat() if a.ea_seen_at else None,
                }
                for a in self.accounts
            ],
        }


def _enum(value: str | None, prefix: str) -> str:
    return (value or "").removeprefix(prefix).lower()


def _num(value: Any) -> float | None:
    return float(value) if value not in (None, "") else None


@contextmanager
def _sync_lock():
    """Serialise syncs across processes (web server and MCP server)."""
    path = get_settings().data_dir / "sync.lock"
    with open(path, "a+") as fh:
        if sys.platform == "win32":
            import msvcrt

            fh.seek(0)
            while True:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)  # retries for ~10 s, then raises
                    break
                except OSError:
                    continue
            try:
                yield
            finally:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)


class _Reader:
    def __init__(self, session: Session, force: bool):
        self.db_key = str(session.get_bind().url)
        self.force = force
        self.pending: list[tuple[tuple[str, Path], tuple[int, int]]] = []

    def changed(self, path: Path) -> bool:
        if not path.is_file():
            return False
        stat = path.stat()
        key, sig = (self.db_key, path), (stat.st_mtime_ns, stat.st_size)
        if not self.force and _seen_files.get(key) == sig:
            return False
        self.pending.append((key, sig))
        return True

    def commit(self) -> None:
        _seen_files.update(self.pending)

    @staticmethod
    def json(path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Skipping unreadable %s: %s", path.name, exc)
            return None


def sync_mt5(session: Session, folder: Path | None = None, force: bool = False) -> SyncResult:
    folder = folder or discover_mt5_dir()
    if folder is None or not folder.is_dir():
        return SyncResult(
            status="no_folder",
            folder=str(folder) if folder else None,
            message="No MT5 export folder yet. Attach the TradeJournalSync EA to a chart in MT5.",
        )
    with _sync_lock():
        reader = _Reader(session, force)
        result = SyncResult(status="ok", folder=str(folder))
        for account_file in sorted(folder.glob("account_*.json")):
            data = reader.json(account_file)
            if data is None:
                continue
            result.accounts.append(_sync_account(session, folder, data, reader))
        session.flush()
        reader.commit()
        if not result.accounts:
            result.message = "Export folder found but no account files yet. Is the EA running?"
        return result


def _sync_account(session: Session, folder: Path, data: dict[str, Any], reader: _Reader) -> AccountSync:
    login = str(data["login"])
    account = _upsert_account(session, data)
    offset = int(data.get("server_utc_offset") or 0)
    mode = get_setting(session, "broker_time_mode")
    status = AccountSync(login=login, name=account.name, ea_seen_at=account.ea_seen_at)

    symbols_path = folder / f"symbols_{login}.json"
    if reader.changed(symbols_path) and (symbols := reader.json(symbols_path)):
        _upsert_symbols(session, account, symbols.get("symbols", []))

    touched: set[int] = set()
    deals_path = folder / f"deals_{login}.json"
    if reader.changed(deals_path) and (deals := reader.json(deals_path)):
        new_positions, status.new_deals = _insert_deals(session, account, deals.get("deals", []), offset, mode)
        touched |= new_positions

    exc_path = folder / f"excursions_{login}.csv"
    if reader.changed(exc_path):
        touched |= _upsert_excursions(session, account, exc_path)

    stops_path = folder / f"stops_{login}.csv"
    if reader.changed(stops_path):
        touched |= _upsert_stops(session, account, stops_path, offset, mode)

    open_infos: dict[int, OpenPositionInfo] = {}
    positions = reader.json(folder / f"positions_{login}.json") if (folder / f"positions_{login}.json").is_file() else None
    for p in (positions or {}).get("positions", []):
        open_infos[int(p["position_id"])] = OpenPositionInfo(
            sl=_num(p.get("sl")) or None,
            tp=_num(p.get("tp")) or None,
            floating_pnl=round((_num(p.get("profit")) or 0.0) + (_num(p.get("swap")) or 0.0), 2),
        )
    touched |= set(open_infos)
    # Trades still marked open whose position has since gone also need a rebuild.
    touched |= set(
        session.scalars(
            select(Trade.position_id).where(
                Trade.account_id == account.id, Trade.status == "open", Trade.position_id.is_not(None)
            )
        )
    )

    if reader.force:
        touched |= set(
            session.scalars(
                select(Deal.position_id)
                .where(Deal.account_id == account.id, Deal.type.in_(TRADE_TYPES))
                .distinct()
            )
        )
    status.trades_rebuilt = rebuild_positions(session, account, touched, open_infos)
    account.last_sync_at = datetime.now(UTC)
    return status


def _upsert_account(session: Session, data: dict[str, Any]) -> Account:
    login, server = str(data["login"]), data.get("server")
    account = session.scalar(
        select(Account).where(Account.source == "mt5", Account.login == login, Account.server == server)
    )
    if account is None:
        account = Account(source="mt5", login=login, server=server, name=f"{login}")
        session.add(account)
    account.broker = data.get("company")
    account.name = f"{data.get('company') or 'MT5'} · {login}"
    account.currency = data.get("currency") or "USD"
    account.leverage = data.get("leverage")
    account.utc_offset_sec = int(data.get("server_utc_offset") or 0)
    account.margin_mode = data.get("margin_mode")
    account.trade_mode = _enum(data.get("trade_mode"), "ACCOUNT_TRADE_MODE_") or None
    account.balance = _num(data.get("balance"))
    account.equity = _num(data.get("equity"))
    if data.get("exported_at"):
        account.ea_seen_at = datetime.fromtimestamp(int(data["exported_at"]), UTC)
    session.flush()
    return account


def _upsert_symbols(session: Session, account: Account, items: list[dict[str, Any]]) -> None:
    existing = {s.symbol: s for s in session.scalars(select(Symbol).where(Symbol.account_id == account.id))}
    for item in items:
        name = item["name"]
        sym = existing.get(name) or Symbol(account_id=account.id, symbol=name)
        sym.canonical = canonical_symbol(name)
        sym.description = item.get("description")
        sym.digits = item.get("digits")
        sym.point = _num(item.get("point"))
        sym.tick_size = _num(item.get("tick_size"))
        sym.tick_value = _num(item.get("tick_value"))
        sym.contract_size = _num(item.get("contract_size"))
        sym.base_ccy = item.get("base")
        sym.profit_ccy = item.get("profit_ccy")
        sym.asset_class = asset_class(name, item.get("path"))
        session.add(sym)


def _insert_deals(
    session: Session, account: Account, items: list[dict[str, Any]], offset: int, mode: str
) -> tuple[set[int], int]:
    known = set(session.scalars(select(Deal.ticket).where(Deal.account_id == account.id)))
    touched: set[int] = set()
    added = 0
    for item in items:
        ticket = int(item["ticket"])
        if ticket in known:
            continue
        time_msc = int(item.get("time_msc") or int(item["time"]) * 1000)
        deal = Deal(
            account_id=account.id,
            ticket=ticket,
            order=int(item.get("order") or 0) or None,
            position_id=int(item.get("position_id") or 0) or None,
            time=server_ms_to_utc(time_msc, offset, mode),
            time_msc=time_msc,
            type=_enum(item.get("type"), "DEAL_TYPE_"),
            entry=_enum(item.get("entry"), "DEAL_ENTRY_"),
            symbol=item.get("symbol") or None,
            volume=_num(item.get("volume")) or 0.0,
            price=_num(item.get("price")) or 0.0,
            sl=_num(item.get("sl")),
            tp=_num(item.get("tp")),
            commission=_num(item.get("commission")) or 0.0,
            fee=_num(item.get("fee")) or 0.0,
            swap=_num(item.get("swap")) or 0.0,
            profit=_num(item.get("profit")) or 0.0,
            reason=_enum(item.get("reason"), "DEAL_REASON_") or None,
            magic=item.get("magic"),
            comment=item.get("comment") or None,
        )
        session.add(deal)
        known.add(ticket)
        added += 1
        if deal.type in TRADE_TYPES and deal.position_id:
            touched.add(deal.position_id)
        elif deal.type not in TRADE_TYPES:
            session.add(
                CashFlow(
                    account_id=account.id,
                    ticket=ticket,
                    time=deal.time,
                    amount=round(deal.profit + deal.commission + deal.swap + deal.fee, 2),
                    type=deal.type,
                    comment=deal.comment,
                )
            )
    session.flush()
    return touched, added


def _upsert_excursions(session: Session, account: Account, path: Path) -> set[int]:
    known = set(
        session.scalars(select(PositionExcursion.position_id).where(PositionExcursion.account_id == account.id))
    )
    touched: set[int] = set()
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                pid, high, low = int(row["position_id"]), float(row["high"]), float(row["low"])
            except (KeyError, TypeError, ValueError):
                continue
            if pid in known:
                continue
            session.add(PositionExcursion(account_id=account.id, position_id=pid, high=high, low=low))
            known.add(pid)
            touched.add(pid)
    session.flush()
    return touched


def _upsert_stops(session: Session, account: Account, path: Path, offset: int, mode: str) -> set[int]:
    known = set(session.scalars(select(PositionStop.position_id).where(PositionStop.account_id == account.id)))
    touched: set[int] = set()
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                pid, sl, t = int(row["position_id"]), float(row["first_sl"]), int(row["first_sl_time"])
            except (KeyError, TypeError, ValueError):
                continue
            if pid in known:
                continue
            session.add(
                PositionStop(
                    account_id=account.id, position_id=pid, first_sl=sl, first_sl_time=server_ms_to_utc(t * 1000, offset, mode)
                )
            )
            known.add(pid)
            touched.add(pid)
    session.flush()
    return touched


def _chunks(items: list[int], size: int = 500) -> Iterable[list[int]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def rebuild_positions(
    session: Session,
    account: Account,
    position_ids: set[int],
    open_infos: dict[int, OpenPositionInfo] | None = None,
) -> int:
    """Recompute the trades of the given positions from their deals. Returns trades written."""
    if not position_ids:
        return 0
    open_infos = open_infos or {}
    sessions_cfg = get_setting(session, "sessions")
    symbols = {s.symbol: s for s in session.scalars(select(Symbol).where(Symbol.account_id == account.id))}
    written = 0
    for chunk in _chunks(sorted(position_ids)):
        deals_by_pos: dict[int, list[Deal]] = {}
        for d in session.scalars(
            select(Deal).where(
                Deal.account_id == account.id, Deal.position_id.in_(chunk), Deal.type.in_(TRADE_TYPES)
            )
        ):
            deals_by_pos.setdefault(d.position_id, []).append(d)
        excursions = {
            e.position_id: (e.high, e.low)
            for e in session.scalars(
                select(PositionExcursion).where(
                    PositionExcursion.account_id == account.id, PositionExcursion.position_id.in_(chunk)
                )
            )
        }
        first_stops = {
            p.position_id: FirstStop(p.first_sl, p.first_sl_time)
            for p in session.scalars(
                select(PositionStop).where(PositionStop.account_id == account.id, PositionStop.position_id.in_(chunk))
            )
        }
        existing = {
            (t.position_id, t.leg): t
            for t in session.scalars(
                select(Trade).where(Trade.account_id == account.id, Trade.position_id.in_(chunk))
            )
        }
        for pid in chunk:
            deals = deals_by_pos.get(pid, [])
            legs = build_legs(deals)
            symbol = deals[0].symbol if deals else None
            spec_row = symbols.get(symbol) if symbol else None
            spec = (
                SymbolSpec(point=spec_row.point, tick_size=spec_row.tick_size, tick_value=spec_row.tick_value)
                if spec_row
                else None
            )
            for idx, leg in enumerate(legs):
                fields = leg_to_trade_fields(
                    leg,
                    spec,
                    excursions.get(pid) if len(legs) == 1 else None,
                    open_infos.get(pid) if idx == len(legs) - 1 else None,
                    first_stops.get(pid) if idx == 0 else None,
                )
                fields["session"] = session_for_hour(fields["open_time"].hour, sessions_cfg)
                trade = existing.get((pid, idx))
                if trade is None:
                    trade = Trade(account_id=account.id, source="mt5", position_id=pid, leg=idx)
                    session.add(trade)
                trade.symbol = symbol or "?"
                trade.instrument = canonical_symbol(trade.symbol)
                for key, value in fields.items():
                    setattr(trade, key, value)
                written += 1
            session.execute(
                delete(Trade).where(
                    Trade.account_id == account.id, Trade.position_id == pid, Trade.leg >= len(legs)
                )
            )
    session.flush()
    return written
